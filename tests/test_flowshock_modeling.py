import sys
import unittest
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

modeling = cast(Any, import_module("analysis.flowshock_modeling.run_modeling"))
quality = cast(Any, import_module("analysis.flowshock_modeling.quality_checks"))


class FlowShockModelingTests(unittest.TestCase):
    def test_time_split_is_chronological(self):
        frame = pd.DataFrame({"date": ["2025-07-01", "2025-11-10", "2025-12-01"]})
        result = modeling.add_time_split(frame, "date")
        self.assertEqual(result["split"].tolist(), ["train", "validation", "test"])

    def test_fractional_time_split_handles_event_dates(self):
        frame = pd.DataFrame({"event_date": ["2025-07-01", "2025-07-02", "2025-07-03", "2025-07-04", "2025-07-05"]})
        result = modeling.add_fractional_time_split(frame, "event_date")
        self.assertEqual(set(result["split"]), {"train", "validation", "test"})

    def test_shock_pulse_label_and_loss_uses_train_baseline(self):
        frame = pd.DataFrame(
            {
                "date": ["2025-07-01", "2025-12-02"],
                "merchant_region": ["A", "A"],
                "industry": ["food", "food"],
                "sales_dev_pct": [0.0, 0.0],
                "baseline_sales_amount": [1000, 700],
                "sales_amount": [1000, 700],
                "use_count": [10, 8],
                "daily_rain_mm": [0.0, 10.0],
                "temp_mean_c": [25.0, 25.0],
                "humidity_mean_pct": [70.0, 70.0],
                "wind_mean_ms": [2.0, 2.0],
                "max_hourly_rain_mm": [0.0, 5.0],
                "rain_hours": [0, 2],
                "weather_hourly_obs": [24, 24],
                "day_of_week": [1, 1],
                "is_weekend": [0, 0],
                "is_holiday": [0, 0],
                "month": [202507, 202512],
                "rain_bin": ["0", "5-20"],
            }
        )
        result = modeling.build_model_ready_daily(frame)
        test_row = result[result["split"] == "test"].iloc[0]
        self.assertEqual(float(test_row["model_baseline_sales_amount"]), 1000.0)
        self.assertEqual(int(test_row["shock_pulse_label"]), 1)
        self.assertEqual(float(test_row["estimated_loss_amount"]), 300.0)

    def test_history_features_are_strictly_shifted(self):
        frame = pd.DataFrame(
            {
                "date": ["2025-07-01", "2025-11-04", "2025-12-02"],
                "merchant_region": ["A", "A", "A"],
                "industry": ["food", "food", "food"],
                "sales_dev_pct": [0.0, 0.0, 0.0],
                "baseline_sales_amount": [1000, 1000, 1000],
                "sales_amount": [1000, 700, 900],
                "use_count": [10, 10, 10],
                "daily_rain_mm": [0.0, 10.0, 0.0],
                "temp_mean_c": [25.0, 25.0, 25.0],
                "humidity_mean_pct": [70.0, 70.0, 70.0],
                "wind_mean_ms": [2.0, 2.0, 2.0],
                "max_hourly_rain_mm": [0.0, 5.0, 0.0],
                "rain_hours": [0, 2, 0],
                "weather_hourly_obs": [24, 24, 24],
                "day_of_week": [1, 1, 1],
                "is_weekend": [0, 0, 0],
                "is_holiday": [0, 0, 0],
                "month": [202507, 202507, 202507],
                "rain_bin": ["0", "5-20", "0"],
            }
        )
        result = modeling.build_model_ready_daily(frame)
        self.assertTrue(pd.isna(result.loc[0, "lag1_sales_dev_pct"]))
        self.assertAlmostEqual(float(result.loc[1, "lag1_sales_dev_pct"]), 0.0)
        self.assertAlmostEqual(float(result.loc[2, "lag1_sales_dev_pct"]), -30.0)
        self.assertEqual(result["prior_shock_count"].tolist(), [0.0, 0.0, 1.0])

    def test_forbidden_same_day_features_are_rejected(self):
        result = quality.check_no_forbidden_features(["daily_rain_mm", "sales_dev_pct", "estimated_loss_amount"], "features")
        self.assertFalse(result.passed)

    def test_topk_loss_capture_prioritizes_high_loss_rows(self):
        actual = pd.Series([100.0, 0.0, 50.0, 0.0])
        score = pd.Series([0.9, 0.1, 0.8, 0.2])
        metric = modeling.topk_loss_capture(actual, score, 0.5)
        self.assertAlmostEqual(metric["loss_capture"], 1.0)
        self.assertAlmostEqual(metric["lift"], 2.0)
        self.assertEqual(metric["rows"], 2)

    def test_loss_ranking_metrics_include_regression_and_topk(self):
        frame = pd.DataFrame(
            {
                "estimated_loss_amount": [100.0, 0.0, 50.0, 0.0],
                "predicted_estimated_loss_amount": [90.0, 10.0, 40.0, 5.0],
                "predicted_support_priority_score": [0.9, 0.1, 0.8, 0.2],
            }
        )
        metric = modeling.loss_ranking_metrics(frame, "test")
        self.assertIn("mae", metric)
        self.assertIn("rmse", metric)
        self.assertAlmostEqual(metric["top20_loss_capture"], 100.0 / 150.0)
        self.assertAlmostEqual(metric["top20_lift"], (100.0 / 150.0) / 0.25)

    def test_regression_error_metrics_do_not_require_sklearn(self):
        metric = modeling.regression_error_metrics(pd.Series([10.0, 20.0]), pd.Series([8.0, 25.0]))
        self.assertAlmostEqual(metric["mae"], 3.5)
        self.assertAlmostEqual(metric["rmse"], (29.0 / 2) ** 0.5)

    def test_loss_priority_fallback_without_sklearn(self):
        previous = modeling.SKLEARN_AVAILABLE
        modeling.SKLEARN_AVAILABLE = False
        try:
            rows = []
            for date, split, loss, sales_dev in [
                ("2025-07-01", "train", 100.0, 0.0),
                ("2025-07-02", "train", 300.0, -30.0),
                ("2025-11-01", "validation", 200.0, -20.0),
                ("2025-12-01", "test", 400.0, -40.0),
            ]:
                row: dict[str, object] = {feature: 0 for feature in modeling.DAILY_FEATURES}
                row.update(
                    {
                        "date": date,
                        "split": split,
                        "merchant_region": "A",
                        "industry": "food",
                        "rain_bin": "0",
                        "rain_bin_industry": "0|food",
                        "rain_bin_region": "0|A",
                        "estimated_loss_amount": loss,
                        "model_sales_dev_pct": sales_dev,
                    }
                )
                rows.append(row)
            dataset = pd.DataFrame(rows)
            shock_predictions = pd.DataFrame(
                {
                    "date": ["2025-11-01", "2025-12-01"],
                    "merchant_region": ["A", "A"],
                    "industry": ["food", "food"],
                    "predicted_shock_pulse_label_probability": [0.5, 0.8],
                }
            )
            predictions, importance, summary, result = modeling.train_loss_priority_model(dataset, modeling.LOSS_PRIORITY_FEATURES, shock_predictions)
            self.assertFalse(predictions.empty)
            self.assertFalse(summary.empty)
            self.assertEqual(result["metrics"][0]["dependency_mode"], "fallback_group_median_loss")
            self.assertIn("predicted_support_priority_score", predictions.columns)
        finally:
            modeling.SKLEARN_AVAILABLE = previous

    def test_loss_priority_score_combines_shock_probability_and_predicted_loss(self):
        predictions = pd.DataFrame(
            {
                "merchant_region": ["A"],
                "industry": ["food"],
                "predicted_support_priority_score": [30.0],
                "estimated_loss_amount": [50.0],
                "predicted_estimated_loss_amount": [100.0],
                "predicted_shock_pulse_label_probability": [0.3],
            }
        )
        summary = modeling.build_loss_priority_summary(predictions)
        self.assertEqual(float(summary.loc[0, "predicted_total_loss_priority"]), 30.0)
        self.assertEqual(int(summary.loc[0, "priority_rank"]), 1)

    def test_loss_priority_evaluation_split_allows_validation_and_test_only(self):
        frame = pd.DataFrame(
            {
                "date": ["2025-11-01", "2025-12-01"],
                "split": ["validation", "test"],
            }
        )
        result = modeling.check_loss_priority_evaluation_split(frame)
        self.assertTrue(result.passed)

    def test_chronological_split_check(self):
        frame = pd.DataFrame(
            {
                "date": ["2025-07-01", "2025-11-01", "2025-12-01"],
                "split": ["train", "validation", "test"],
            }
        )
        result = quality.check_chronological_split(frame, "date", "split", "split")
        self.assertTrue(result.passed)

    def test_modeling_module_is_package_importable(self):
        self.assertTrue(hasattr(modeling, "run_build"))


if __name__ == "__main__":
    unittest.main()
