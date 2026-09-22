"""Run with: python -m unittest discover -s data/scripts/tests"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

MODULE = Path(__file__).resolve().parents[1] / "codebook_json_file_maker.py"
SPEC = importlib.util.spec_from_file_location("codebook", MODULE)
codebook = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(codebook)

CONTRACT = {
    "schema_version": "0.1", "dataset_id": "weather_daily", "name": "기상",
    "description": "일별 관측", "source": "test", "path": "data/preprocessed/weather.csv",
    "format": "csv", "grain": "관측소별 하루", "primary_key": ["date", "station_id"],
    "columns": {
        "date": {"dtype": "date", "nullable": False},
        "station_id": {"dtype": "string", "nullable": False, "allowed_values": ["001", "002"]},
        "temperature": {"dtype": "float", "nullable": True, "constraints": {"min": -50, "max": 50}},
    },
}


class CodebookTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.contract_dir = self.root / "data/contract"
        self.contract_dir.mkdir(parents=True)
        self.data = self.root / CONTRACT["path"]
        self.data.parent.mkdir(parents=True)
        self.write_contract(CONTRACT)

    def write_contract(self, contract, name="weather.yaml"):
        (self.contract_dir / name).write_text(yaml.safe_dump(contract, allow_unicode=True), encoding="utf-8")

    def build(self, csv_text=None):
        if csv_text is not None:
            self.data.write_text(csv_text, encoding="utf-8")
        return codebook.build_codebook(self.root, self.contract_dir)

    def test_valid_data_and_deterministic_json(self):
        result = self.build("date,station_id,temperature\n2026-01-01,001,20\n2026-01-01,002,\n")
        self.assertEqual(result["validation"]["status"], "passed")
        observed = result["datasets"][0]["observed"]
        self.assertEqual(observed["row_count"], 2)
        self.assertEqual(observed["null_counts"]["temperature"], 1)
        self.assertEqual(observed["date_ranges"]["date"]["min"], "2026-01-01")
        self.assertEqual(len(observed["sha256"]), 64)
        self.assertEqual(json.dumps(result), json.dumps(self.build()))

    def test_data_failures_and_no_raw_values(self):
        result = self.build("date,station_id,temperature\n2026-01-01,001,51\n2026-01-01,001,NaN\n2026-02-30,SECRET,10\n,002,5\nwrong,width\n")
        errors = " ".join(result["datasets"][0]["validation"]["errors"])
        for expected in ("range_violations=1", "type_violations=1", "allowed_values_violations=1",
                         "non_nullable_violations=1", "Duplicate primary key rows: 1", "Malformed CSV rows: 1"):
            self.assertIn(expected, errors)
        self.assertNotIn("SECRET", json.dumps(result))
        self.assertEqual(result["validation"]["status"], "failed")

    def test_missing_file_and_duplicate_ids(self):
        result = self.build()
        self.assertIn("FileNotFoundError", str(result["datasets"][0]["validation"]["errors"]))
        self.write_contract(CONTRACT, "duplicate.yml")
        result = self.build()
        self.assertEqual(len(result["datasets"]), 2)
        for entry in result["datasets"]:
            self.assertIn("Duplicate dataset_id", str(entry["validation"]["errors"]))

    def test_schema_mismatch(self):
        for header in ("date,station_id,station_id", "date,station_id,extra"):
            result = self.build(header + "\n")
            self.assertEqual(result["validation"]["status"], "failed")
            self.assertIn("Missing columns", str(result))

    def test_invalid_contracts(self):
        for text in ("name: one\nname: two", "[]", "dataset_id: []", "columns: {a: {dtype: []}}"):
            with self.subTest(text=text):
                (self.contract_dir / "weather.yaml").write_text(text)
                self.assertEqual(self.build()["validation"]["status"], "failed")
        contract = copy.deepcopy(CONTRACT)
        contract["columns"]["date"]["nullable"] = True
        contract["columns"]["temperature"]["constraints"] = {"min": 5, "max": 1}
        self.write_contract(contract)
        errors = str(self.build()["datasets"][0]["validation"]["errors"])
        self.assertIn("primary key", errors)
        self.assertIn("min must not exceed max", errors)

    def test_scalar_parsers(self):
        self.assertEqual(codebook.parse_value("001", "string"), "001")
        self.assertEqual(codebook.parse_value("01", "integer"), 1)
        self.assertIs(codebook.parse_value("FALSE", "boolean"), False)
        self.assertEqual(codebook.parse_value("2026-01-01T09:00:00+09:00", "datetime").isoformat(), "2026-01-01T09:00:00+09:00")
        for value, dtype in (("1.0", "integer"), ("inf", "float"), ("yes", "boolean"),
                             ("2026-1-1", "date"), ("2026-01-01T00:00:00", "datetime")):
            with self.assertRaises(ValueError):
                codebook.parse_value(value, dtype)

    def test_empty_contract_dir_and_cli_exit(self):
        (self.contract_dir / "weather.yaml").unlink()
        self.assertEqual(self.build()["validation"]["errors"], ["No YAML contracts found"])
        self.assertEqual(codebook.main(["--root", str(self.root)]), 1)
        output = self.root / "data/codebook/codebook.json"
        self.assertTrue(output.exists())
        self.write_contract(CONTRACT)
        self.build("date,station_id,temperature\n2026-01-01,001,1\n")
        self.assertEqual(codebook.main(["--root", str(self.root)]), 0)
        self.assertEqual(json.loads(output.read_text())["validation"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
