import sys
import unittest
from importlib import import_module
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

analysis = import_module("analysis.flowshock_analysis.run_analysis")
quality_checks = import_module("analysis.flowshock_analysis.quality_checks")


class FlowShockAnalysisTests(unittest.TestCase):
    def test_assign_rain_bin_boundaries(self):
        bins = analysis.assign_rain_bin(pd.Series([0, 0.1, 5, 20, 50, 51])).tolist()
        self.assertEqual(bins, ["0", "0-5", "0-5", "5-20", "20-50", "50+"])

    def test_daily_baseline_uses_region_industry_weekday_median(self):
        frame = pd.DataFrame(
            {
                "date": ["2025-07-01", "2025-07-08", "2025-07-15"],
                "merchant_region": ["A", "A", "A"],
                "industry": ["food", "food", "food"],
                "sales_amount": [100, 200, 300],
                "use_count": [10, 20, 30],
                "daily_rain_mm": [0, 20, 0],
                "day_of_week": [1, 1, 1],
            }
        )
        result = analysis.add_daily_baseline(frame)
        self.assertTrue((result["baseline_sales_amount"] == 200).all())
        self.assertEqual(result.loc[0, "sales_dev_pct"], -50)

    def test_consecutive_heavy_days_share_event_group(self):
        weather = pd.DataFrame(
            {
                "date": ["2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04"],
                "merchant_region": ["A", "A", "A", "A"],
                "daily_rain_mm": [21, 22, 0, 30],
            }
        )
        events = analysis.detect_heavy_rain_events(weather)
        self.assertEqual(events["event_group_id"].tolist(), [1, 1, 2])

    def test_daily_grain_guard_rejects_skt_fields(self):
        result = quality_checks.check_daily_grain_safety("daily", ["date", "skt_flow_pop"])
        self.assertFalse(result.passed)

    def test_json_bundle_field_guard(self):
        result = quality_checks.check_json_field_safety({"ok": [{"block_id": "x"}]}, "json")
        self.assertFalse(result.passed)

    def test_build_module_is_package_importable(self):
        self.assertTrue(hasattr(analysis, "run_build"))


if __name__ == "__main__":
    unittest.main()
