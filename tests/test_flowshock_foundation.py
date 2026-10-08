import sys
import unittest
from importlib import import_module
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_DIR = ROOT / "analysis" / "flowshock_foundation"
sys.path.insert(0, str(MODULE_DIR))

quality_checks = import_module("quality_checks")
check_grain_safety = quality_checks.check_grain_safety
check_nonnegative = quality_checks.check_nonnegative
check_unique = quality_checks.check_unique
hour_to_time_band = quality_checks.hour_to_time_band


class FlowShockFoundationTests(unittest.TestCase):
    def test_hour_to_time_band_boundaries(self):
        expected = {
            0: "00_05",
            5: "00_05",
            6: "06_11",
            11: "06_11",
            12: "12_17",
            17: "12_17",
            18: "18_23",
            23: "18_23",
        }
        for hour, time_band in expected.items():
            with self.subTest(hour=hour):
                self.assertEqual(hour_to_time_band(hour), time_band)

    def test_hour_to_time_band_rejects_invalid_hour(self):
        with self.assertRaises(ValueError):
            hour_to_time_band(24)

    def test_unique_key_check_detects_duplicates(self):
        frame = pd.DataFrame({"date": ["2025-07-01", "2025-07-01"], "region": ["A", "A"]})
        result = check_unique(frame, ["date", "region"], "daily_key")
        self.assertFalse(result.passed)

    def test_nonnegative_check(self):
        frame = pd.DataFrame({"sales_amount": [10, 0, -1]})
        result = check_nonnegative(frame, ["sales_amount"], "sales_nonnegative")
        self.assertFalse(result.passed)

    def test_grain_guard_rejects_monthly_skt_fields_in_daily_table(self):
        result = check_grain_safety(
            "invalid_daily_mart",
            "day",
            ["date", "merchant_region", "skt_flow_pop"],
        )
        self.assertFalse(result.passed)

    def test_grain_guard_allows_monthly_skt_profile(self):
        result = check_grain_safety(
            "monthly_profile",
            "month",
            ["month", "time_band", "skt_flow_pop"],
        )
        self.assertTrue(result.passed)

    def test_build_module_is_package_importable(self):
        sys.path.insert(0, str(ROOT))
        module = import_module("analysis.flowshock_foundation.build_foundation")
        self.assertTrue(hasattr(module, "run_build"))


if __name__ == "__main__":
    unittest.main()
