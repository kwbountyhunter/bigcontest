from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

try:
    from .quality_checks import (
        CheckResult,
        check_chronological_split,
        check_no_forbidden_features,
        check_no_raw_paths,
        check_required_columns,
        check_unique,
        summarize_checks,
    )
except ImportError:
    from quality_checks import (
        CheckResult,
        check_chronological_split,
        check_no_forbidden_features,
        check_no_raw_paths,
        check_required_columns,
        check_unique,
        summarize_checks,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS = ROOT / "analysis" / "flowshock_analysis" / "out"
DEFAULT_OUT = Path(__file__).resolve().parent / "out"

SHOCK_THRESHOLD_PCT = -20.0
WEATHER_SHOCK_RAIN_MM = 5.0
RECOVERY_THRESHOLD_PCT = 0.0
RANDOM_SEED = 42

DAILY_FEATURES = [
    "daily_rain_mm",
    "max_hourly_rain_mm",
    "rain_hours",
    "temp_mean_c",
    "humidity_mean_pct",
    "wind_mean_ms",
    "weather_hourly_obs",
    "day_of_week",
    "is_weekend",
    "is_holiday",
    "month",
    "merchant_region",
    "industry",
    "rain_bin",
    "heavy_rain_flag",
    "rain_3d_sum",
    "rain_7d_sum",
    "temp_7d_mean",
    "humidity_temp_interaction",
    "wind_rain_interaction",
    "rain_bin_industry",
    "rain_bin_region",
    "lag1_sales_dev_pct",
    "rolling7_sales_dev_mean",
    "rolling7_sales_dev_std",
    "prior_shock_count",
    "days_since_prior_shock",
]
EVENT_FEATURES = [
    "event_rain_mm",
    "pre3_sales_dev_pct",
    "missing_window_days",
    "merchant_region",
    "industry",
]
LOSS_PRIORITY_FEATURES = DAILY_FEATURES
REQUIRED_INPUTS = {
    "daily": "daily_baseline_panel.csv",
    "events": "event_window_metrics_by_industry.csv",
    "shock": "shock_recovery_metrics_by_industry.csv",
    "timeband": "timeband_vulnerability_metrics.csv",
    "inflow": "broad_area_inflow_context.csv",
    "priority": "support_priority_by_industry.csv",
    "manifest": "manifest.json",
    "quality": "quality_report.json",
}


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_json(payload: object, path: Path) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, object]]:
    frame = df if limit is None else df.head(limit)
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_analysis(analysis_dir: Path) -> dict[str, object]:
    missing = [filename for filename in REQUIRED_INPUTS.values() if not (analysis_dir / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Missing analysis outputs: {missing}")
    return {
        "daily": pd.read_csv(analysis_dir / REQUIRED_INPUTS["daily"], encoding="utf-8-sig", low_memory=False),
        "events": pd.read_csv(analysis_dir / REQUIRED_INPUTS["events"], encoding="utf-8-sig", low_memory=False),
        "shock": pd.read_csv(analysis_dir / REQUIRED_INPUTS["shock"], encoding="utf-8-sig", low_memory=False),
        "timeband": pd.read_csv(analysis_dir / REQUIRED_INPUTS["timeband"], encoding="utf-8-sig", low_memory=False),
        "inflow": pd.read_csv(analysis_dir / REQUIRED_INPUTS["inflow"], encoding="utf-8-sig", low_memory=False),
        "priority": pd.read_csv(analysis_dir / REQUIRED_INPUTS["priority"], encoding="utf-8-sig", low_memory=False),
        "manifest": json.loads((analysis_dir / REQUIRED_INPUTS["manifest"]).read_text(encoding="utf-8")),
        "quality": json.loads((analysis_dir / REQUIRED_INPUTS["quality"]).read_text(encoding="utf-8")),
    }


def add_time_split(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    frame = df.copy()
    frame[date_column] = pd.to_datetime(frame[date_column])
    frame["split"] = np.select(
        [frame[date_column] <= pd.Timestamp("2025-10-31"), frame[date_column] <= pd.Timestamp("2025-11-30")],
        ["train", "validation"],
        default="test",
    )
    frame[date_column] = frame[date_column].dt.strftime("%Y-%m-%d")
    return frame


def add_fractional_time_split(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    frame = df.copy()
    frame[date_column] = pd.to_datetime(frame[date_column])
    unique_dates = sorted(frame[date_column].dropna().unique())
    if len(unique_dates) < 3:
        frame["split"] = "train"
    else:
        train_cutoff = unique_dates[max(0, int(len(unique_dates) * 0.6) - 1)]
        validation_cutoff = unique_dates[max(int(len(unique_dates) * 0.6), int(len(unique_dates) * 0.8) - 1)]
        frame["split"] = np.select(
            [frame[date_column] <= train_cutoff, frame[date_column] <= validation_cutoff],
            ["train", "validation"],
            default="test",
        )
    frame[date_column] = frame[date_column].dt.strftime("%Y-%m-%d")
    return frame


def build_model_ready_daily(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["merchant_region", "industry", "date"]).reset_index(drop=True)
    train_mask = frame["date"] <= pd.Timestamp("2025-10-31")
    train = frame[train_mask].copy()
    primary_baseline = train.groupby(["merchant_region", "industry", "day_of_week"], as_index=False).agg(
        model_baseline_sales_amount=("sales_amount", "median"),
        model_baseline_use_count=("use_count", "median"),
    )
    region_industry_baseline = train.groupby(["merchant_region", "industry"], as_index=False).agg(
        fallback_region_industry_sales=("sales_amount", "median"),
        fallback_region_industry_use=("use_count", "median"),
    )
    industry_baseline = train.groupby("industry", as_index=False).agg(
        fallback_industry_sales=("sales_amount", "median"),
        fallback_industry_use=("use_count", "median"),
    )
    global_sales = float(train["sales_amount"].median())
    global_use = float(train["use_count"].median())
    frame = frame.merge(primary_baseline, on=["merchant_region", "industry", "day_of_week"], how="left", validate="many_to_one")
    frame = frame.merge(region_industry_baseline, on=["merchant_region", "industry"], how="left", validate="many_to_one")
    frame = frame.merge(industry_baseline, on="industry", how="left", validate="many_to_one")
    frame["model_baseline_sales_amount"] = frame["model_baseline_sales_amount"].fillna(frame["fallback_region_industry_sales"]).fillna(frame["fallback_industry_sales"]).fillna(global_sales)
    frame["model_baseline_use_count"] = frame["model_baseline_use_count"].fillna(frame["fallback_region_industry_use"]).fillna(frame["fallback_industry_use"]).fillna(global_use)
    frame = frame.drop(columns=["fallback_region_industry_sales", "fallback_region_industry_use", "fallback_industry_sales", "fallback_industry_use"])
    frame["model_sales_idx"] = np.where(frame["model_baseline_sales_amount"] > 0, frame["sales_amount"] / frame["model_baseline_sales_amount"], np.nan)
    frame["model_use_count_idx"] = np.where(frame["model_baseline_use_count"] > 0, frame["use_count"] / frame["model_baseline_use_count"], np.nan)
    frame["model_sales_dev_pct"] = (frame["model_sales_idx"] - 1) * 100
    frame["model_use_count_dev_pct"] = (frame["model_use_count_idx"] - 1) * 100
    frame["baseline_source"] = "train_period_region_industry_weekday_median"
    frame["shock_pulse_label"] = (pd.to_numeric(frame["model_sales_dev_pct"], errors="coerce") <= SHOCK_THRESHOLD_PCT).astype(int)
    frame["weather_shock_label"] = ((frame["shock_pulse_label"] == 1) & (pd.to_numeric(frame["daily_rain_mm"], errors="coerce") >= WEATHER_SHOCK_RAIN_MM)).astype(int)
    frame["estimated_loss_amount"] = (frame["model_baseline_sales_amount"] - frame["sales_amount"]).clip(lower=0)
    frame["heavy_rain_flag"] = (pd.to_numeric(frame["daily_rain_mm"], errors="coerce") >= 20).astype(int)
    region_weather = frame[["date", "merchant_region", "daily_rain_mm", "temp_mean_c"]].drop_duplicates().sort_values(["merchant_region", "date"])
    region_weather["rain_3d_sum"] = region_weather.groupby("merchant_region")["daily_rain_mm"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    region_weather["rain_7d_sum"] = region_weather.groupby("merchant_region")["daily_rain_mm"].transform(lambda s: s.rolling(7, min_periods=1).sum())
    region_weather["temp_7d_mean"] = region_weather.groupby("merchant_region")["temp_mean_c"].transform(lambda s: s.rolling(7, min_periods=1).mean())
    frame = frame.merge(region_weather[["date", "merchant_region", "rain_3d_sum", "rain_7d_sum", "temp_7d_mean"]], on=["date", "merchant_region"], how="left", validate="many_to_one")
    frame["humidity_temp_interaction"] = frame["humidity_mean_pct"] * frame["temp_mean_c"]
    frame["wind_rain_interaction"] = frame["wind_mean_ms"] * frame["daily_rain_mm"]
    frame["rain_bin_industry"] = frame["rain_bin"].astype(str) + "|" + frame["industry"].astype(str)
    frame["rain_bin_region"] = frame["rain_bin"].astype(str) + "|" + frame["merchant_region"].astype(str)
    grouped = frame.groupby(["merchant_region", "industry"], sort=False)
    frame["lag1_sales_dev_pct"] = grouped["model_sales_dev_pct"].shift(1)
    frame["rolling7_sales_dev_mean"] = grouped["model_sales_dev_pct"].transform(lambda s: s.shift(1).rolling(7, min_periods=2).mean())
    frame["rolling7_sales_dev_std"] = grouped["model_sales_dev_pct"].transform(lambda s: s.shift(1).rolling(7, min_periods=2).std())
    frame["prior_shock_count"] = grouped["shock_pulse_label"].transform(lambda s: s.shift(1).fillna(0).cumsum())
    shock_dates = frame["date"].where(frame["shock_pulse_label"] == 1)
    previous_shock_date = shock_dates.groupby([frame["merchant_region"], frame["industry"]]).ffill().groupby([frame["merchant_region"], frame["industry"]]).shift(1)
    frame["days_since_prior_shock"] = (frame["date"] - previous_shock_date).dt.days
    frame["climate_ecg_component"] = "Shock Pulse"
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    return add_time_split(frame, "date")


def expected_train_baselines(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    train = frame[frame["date"] <= pd.Timestamp("2025-10-31")].copy()
    primary = train.groupby(["merchant_region", "industry", "day_of_week"], as_index=False).agg(
        expected_sales=("sales_amount", "median"),
        expected_use=("use_count", "median"),
    )
    region_industry = train.groupby(["merchant_region", "industry"], as_index=False).agg(
        fallback_region_industry_sales=("sales_amount", "median"),
        fallback_region_industry_use=("use_count", "median"),
    )
    industry = train.groupby("industry", as_index=False).agg(
        fallback_industry_sales=("sales_amount", "median"),
        fallback_industry_use=("use_count", "median"),
    )
    global_sales = float(train["sales_amount"].median())
    global_use = float(train["use_count"].median())
    expected = frame[["date", "merchant_region", "industry", "day_of_week"]].copy()
    expected = expected.merge(primary, on=["merchant_region", "industry", "day_of_week"], how="left", validate="many_to_one")
    expected = expected.merge(region_industry, on=["merchant_region", "industry"], how="left", validate="many_to_one")
    expected = expected.merge(industry, on="industry", how="left", validate="many_to_one")
    expected["expected_sales"] = expected["expected_sales"].fillna(expected["fallback_region_industry_sales"]).fillna(expected["fallback_industry_sales"]).fillna(global_sales)
    expected["expected_use"] = expected["expected_use"].fillna(expected["fallback_region_industry_use"]).fillna(expected["fallback_industry_use"]).fillna(global_use)
    expected["date"] = expected["date"].dt.strftime("%Y-%m-%d")
    return expected[["date", "merchant_region", "industry", "day_of_week", "expected_sales", "expected_use"]]


def check_train_only_baselines(analysis_dir: Path, model_ready_daily: pd.DataFrame) -> CheckResult:
    source = pd.read_csv(analysis_dir / REQUIRED_INPUTS["daily"], encoding="utf-8-sig", low_memory=False)
    expected = expected_train_baselines(source)
    actual = model_ready_daily.copy()
    actual["date"] = pd.to_datetime(actual["date"]).dt.strftime("%Y-%m-%d")
    joined = actual.merge(expected, on=["date", "merchant_region", "industry", "day_of_week"], how="left", validate="one_to_one")
    sales_diff = (joined["model_baseline_sales_amount"] - joined["expected_sales"]).abs().fillna(0)
    use_diff = (joined["model_baseline_use_count"] - joined["expected_use"]).abs().fillna(0)
    mismatches = int(((sales_diff > 1e-6) | (use_diff > 1e-6)).sum())
    source_ok = set(joined["baseline_source"].dropna().unique()) == {"train_period_region_industry_weekday_median"}
    passed = mismatches == 0 and source_ok
    return CheckResult("train_only_baseline_policy", passed, f"baseline_mismatches={mismatches}; source_ok={source_ok}")


def check_shifted_history_features(model_ready_daily: pd.DataFrame) -> CheckResult:
    frame = model_ready_daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["merchant_region", "industry", "date"]).reset_index(drop=True)
    grouped = frame.groupby(["merchant_region", "industry"], sort=False)
    expected_lag = grouped["model_sales_dev_pct"].shift(1)
    expected_prior_shock = grouped["shock_pulse_label"].transform(lambda s: s.shift(1).fillna(0).cumsum())
    lag_matches = bool(np.allclose(frame["lag1_sales_dev_pct"].fillna(-999999), expected_lag.fillna(-999999), equal_nan=True))
    shock_matches = bool(np.allclose(frame["prior_shock_count"].fillna(-999999), expected_prior_shock.fillna(-999999), equal_nan=True))
    return CheckResult("shifted_history_features", lag_matches and shock_matches, f"lag_matches={lag_matches}; prior_shock_matches={shock_matches}")


def check_loss_priority_evaluation_split(loss_priority: pd.DataFrame) -> CheckResult:
    frame = loss_priority.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    splits = set(frame["split"].dropna().unique())
    if not {"validation", "test"}.issubset(splits):
        return CheckResult("loss_priority_evaluation_split", False, f"splits={sorted(splits)}")
    unexpected = sorted(splits - {"validation", "test"})
    bounds = frame.groupby("split")["date"].agg(["min", "max"]).to_dict("index")
    passed = not unexpected and bounds["validation"]["max"] < bounds["test"]["min"]
    return CheckResult("loss_priority_evaluation_split", passed, f"bounds={bounds}; unexpected={unexpected}")


def build_model_ready_event(events: pd.DataFrame, shock: pd.DataFrame, timeband: pd.DataFrame, inflow: pd.DataFrame, priority: pd.DataFrame) -> pd.DataFrame:
    frame = events.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"])
    frame["recovery_clock_label"] = (
        (pd.to_numeric(frame["post3_sales_dev_pct"], errors="coerce") < RECOVERY_THRESHOLD_PCT)
        | (pd.to_numeric(frame["net_damage_pp"], errors="coerce") < 0)
    ).astype(int)
    frame["climate_scar_score"] = (-pd.to_numeric(frame["net_damage_pp"], errors="coerce").clip(upper=0)).fillna(0)
    shock_context = shock[["merchant_region", "industry", "median_heavy20_minus_dry_pp", "persistent_damage_share", "low_event_count_flag", "baseline_sensitivity_flag"]]
    timeband_context = timeband.groupby(["merchant_region", "industry"], as_index=False).agg(
        weakest_timeband_heavy5_minus_dry_pp=("median_heavy5_minus_dry_pp", "min"),
        negative_timeband_count=("rain_sales_spearman", lambda s: int((s < 0).sum())),
    )
    inflow_context = inflow.groupby("merchant_region", as_index=False).agg(avg_other_broad_area_sales_share=("other_broad_area_sales_share", "mean"))
    priority_context = priority[["merchant_region", "industry", "support_priority_score", "reliability_flag"]]
    frame = frame.merge(shock_context, on=["merchant_region", "industry"], how="left", validate="many_to_one")
    frame = frame.merge(timeband_context, on=["merchant_region", "industry"], how="left", validate="many_to_one")
    frame = frame.merge(inflow_context, on="merchant_region", how="left", validate="many_to_one")
    frame = frame.merge(priority_context, on=["merchant_region", "industry"], how="left", validate="many_to_one")
    frame["climate_ecg_component"] = "Recovery Clock / Climate Scar"
    return add_fractional_time_split(frame, "event_date")


def fallback_predict(train: pd.DataFrame, target: str, test: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    base_rate = float(train[target].mean()) if len(train) else 0.0
    group_rates = train.groupby(["merchant_region", "industry"])[target].mean().rename("group_rate").reset_index()
    scored = test.merge(group_rates, on=["merchant_region", "industry"], how="left")
    probabilities = scored["group_rate"].fillna(base_rate).to_numpy(dtype="float64")
    predictions = (probabilities >= 0.5).astype(int)
    importance = pd.DataFrame(
        [
            {"model_name": "fallback_group_rate", "feature": "merchant_region+industry", "importance": 1.0},
            {"model_name": "fallback_group_rate", "feature": "global_train_rate", "importance": base_rate},
        ]
    )
    return predictions, probabilities, importance


def sklearn_fit_predict(train: pd.DataFrame, test: pd.DataFrame, features: list[str], target: str, model_name: str) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, object]:
    categorical = [feature for feature in features if train[feature].dtype == "object"]
    numeric = [feature for feature in features if feature not in categorical]
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical),
        ]
    )
    model = Pipeline(
        [
            ("preprocess", preprocessor),
            ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED)),
        ]
    )
    model.fit(train[features], train[target])
    predictions = model.predict(test[features])
    probabilities = model.predict_proba(test[features])[:, 1]
    feature_names = model.named_steps["preprocess"].get_feature_names_out()
    coefficients = model.named_steps["model"].coef_[0]
    importance = pd.DataFrame(
        {
            "model_name": model_name,
            "feature": feature_names,
            "importance": np.abs(coefficients),
            "directional_coefficient": coefficients,
        }
    ).sort_values("importance", ascending=False)
    return predictions, probabilities, importance, model


def make_one_hot_encoder() -> object:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def make_model_pipeline(features: list[str], train: pd.DataFrame, algorithm: str) -> object:
    categorical = [feature for feature in features if train[feature].dtype == "object"]
    numeric = [feature for feature in features if feature not in categorical]
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]), numeric),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", make_one_hot_encoder())]), categorical),
        ]
    )
    if algorithm == "logistic_regression":
        estimator = LogisticRegression(max_iter=1000, class_weight="balanced", random_state=RANDOM_SEED)
    elif algorithm == "random_forest":
        estimator = RandomForestClassifier(n_estimators=80, max_depth=7, min_samples_leaf=10, class_weight="balanced", random_state=RANDOM_SEED, n_jobs=-1)
    elif algorithm == "ridge_regression":
        estimator = Ridge(alpha=1.0, random_state=RANDOM_SEED)
    elif algorithm == "gradient_boosting":
        estimator = GradientBoostingClassifier(n_estimators=180, learning_rate=0.04, max_depth=3, min_samples_leaf=8, random_state=RANDOM_SEED)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")
    return Pipeline([("preprocess", preprocessor), ("model", estimator)])


def extract_importance(model: object, model_name: str) -> pd.DataFrame:
    feature_names = model.named_steps["preprocess"].get_feature_names_out()
    estimator = model.named_steps["model"]
    if hasattr(estimator, "coef_"):
        values = np.ravel(estimator.coef_)
        frame = pd.DataFrame({"model_name": model_name, "feature": feature_names, "importance": np.abs(values), "directional_coefficient": values})
    elif hasattr(estimator, "feature_importances_"):
        values = estimator.feature_importances_
        frame = pd.DataFrame({"model_name": model_name, "feature": feature_names, "importance": values, "directional_coefficient": np.nan})
    else:
        frame = pd.DataFrame({"model_name": model_name, "feature": feature_names, "importance": np.nan, "directional_coefficient": np.nan})
    return frame.sort_values("importance", ascending=False)


def probabilities_from_model(model: object, frame: pd.DataFrame, features: list[str]) -> np.ndarray:
    if hasattr(model.named_steps["model"], "predict_proba"):
        return model.predict_proba(frame[features])[:, 1]
    score = model.decision_function(frame[features])
    return 1 / (1 + np.exp(-score))


def best_threshold(y_true: pd.Series, probabilities: np.ndarray) -> tuple[float, float]:
    candidates = np.linspace(0.05, 0.95, 91)
    best = (0.5, -1.0)
    for threshold in candidates:
        pred = (probabilities >= threshold).astype(int)
        score = f1_score(y_true, pred, zero_division=0)
        if score > best[1]:
            best = (float(threshold), float(score))
    return best


def topk_recall(y_true: pd.Series, probabilities: np.ndarray, k_share: float) -> float:
    if len(y_true) == 0 or int(y_true.sum()) == 0:
        return float("nan")
    k = max(1, int(np.ceil(len(y_true) * k_share)))
    order = np.argsort(probabilities)[::-1][:k]
    return float(pd.Series(y_true).iloc[order].sum() / y_true.sum())


def topk_loss_capture(actual_loss: pd.Series, priority_score: pd.Series, k_share: float) -> dict[str, object]:
    if len(actual_loss) == 0:
        return {"loss_capture": float("nan"), "lift": float("nan"), "rows": 0, "total_loss": 0.0}
    k = max(1, int(np.ceil(len(actual_loss) * k_share)))
    scored = pd.DataFrame({"actual_loss": pd.to_numeric(actual_loss, errors="coerce").fillna(0), "priority_score": pd.to_numeric(priority_score, errors="coerce").fillna(0)})
    total_loss = float(scored["actual_loss"].sum())
    if total_loss <= 0:
        return {"loss_capture": float("nan"), "lift": float("nan"), "rows": k, "total_loss": total_loss}
    selected_loss = float(scored.sort_values("priority_score", ascending=False).head(k)["actual_loss"].sum())
    capture = selected_loss / total_loss
    selected_share = k / len(scored)
    return {"loss_capture": capture, "lift": capture / selected_share, "rows": k, "total_loss": total_loss}


def regression_error_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    actual_values = pd.to_numeric(actual, errors="coerce").fillna(0).to_numpy(dtype="float64")
    predicted_values = pd.to_numeric(predicted, errors="coerce").fillna(0).to_numpy(dtype="float64")
    errors = actual_values - predicted_values
    return {
        "mae": float(np.mean(np.abs(errors))) if len(errors) else float("nan"),
        "rmse": float(np.sqrt(np.mean(errors ** 2))) if len(errors) else float("nan"),
    }


def loss_ranking_metrics(frame: pd.DataFrame, split_name: str) -> dict[str, object]:
    actual = pd.to_numeric(frame["estimated_loss_amount"], errors="coerce").fillna(0)
    predicted = pd.to_numeric(frame["predicted_estimated_loss_amount"], errors="coerce").fillna(0)
    errors = regression_error_metrics(actual, predicted)
    metric: dict[str, object] = {
        "model_name": "Loss Priority regressor - ridge_log_loss",
        "split": split_name,
        "target": "estimated_loss_amount",
        "dependency_mode": "sklearn" if SKLEARN_AVAILABLE else "fallback_group_median_loss",
        "mae": errors["mae"],
        "rmse": errors["rmse"],
        "mean_actual_loss": float(actual.mean()) if len(actual) else float("nan"),
        "mean_predicted_loss": float(predicted.mean()) if len(predicted) else float("nan"),
    }
    for share in [0.05, 0.10, 0.20]:
        topk = topk_loss_capture(actual, frame["predicted_support_priority_score"], share)
        label = int(share * 100)
        metric[f"top{label}_loss_capture"] = topk["loss_capture"]
        metric[f"top{label}_lift"] = topk["lift"]
        metric[f"top{label}_rows"] = topk["rows"]
    metric["total_loss"] = float(actual.sum())
    return metric


def classification_metrics(y_true: pd.Series, y_pred: np.ndarray, y_prob: np.ndarray | None) -> dict[str, object]:
    labels = sorted(pd.Series(y_true).dropna().unique().tolist())
    metric = {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=[0, 1]).tolist(),
    }
    if y_prob is not None and len(labels) == 2:
        metric["roc_auc"] = float(roc_auc_score(y_true, y_prob))
        metric["pr_auc"] = float(average_precision_score(y_true, y_prob))
        metric["top10_recall"] = topk_recall(y_true, y_prob, 0.10)
        metric["top20_recall"] = topk_recall(y_true, y_prob, 0.20)
    else:
        metric["roc_auc"] = None
        metric["pr_auc"] = None
        metric["top10_recall"] = None
        metric["top20_recall"] = None
    return metric


def majority_baseline(train: pd.DataFrame, test: pd.DataFrame, target: str) -> dict[str, object]:
    majority = int(train[target].mean() >= 0.5)
    pred = np.repeat(majority, len(test))
    return classification_metrics(test[target], pred, None)


def train_classifier(dataset: pd.DataFrame, features: list[str], target: str, model_name: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    train = dataset[dataset["split"] == "train"].dropna(subset=[target]).copy()
    validation = dataset[dataset["split"] == "validation"].dropna(subset=[target]).copy()
    test = dataset[dataset["split"] == "test"].dropna(subset=[target]).copy()
    eval_rows: list[dict[str, object]] = []
    prediction_frames: list[pd.DataFrame] = []
    importances: list[pd.DataFrame] = []
    dependency_mode = "sklearn_logistic_regression" if SKLEARN_AVAILABLE else "fallback_group_rate"
    if train[target].nunique() < 2:
        return pd.DataFrame(), pd.DataFrame(), {"model_name": model_name, "trained": False, "reason": "training target has fewer than two classes"}
    algorithms = ["logistic_regression", "random_forest"] if SKLEARN_AVAILABLE else ["fallback_group_rate"]
    trained_models: dict[str, object] = {}
    thresholds: dict[str, float] = {}
    validation_f1: dict[str, float] = {}
    for algorithm in algorithms:
        full_name = f"{model_name} - {algorithm}"
        if SKLEARN_AVAILABLE:
            model = make_model_pipeline(features, train, algorithm)
            model.fit(train[features], train[target])
            validation_prob = probabilities_from_model(model, validation, features) if not validation.empty else np.array([])
            threshold, threshold_f1 = best_threshold(validation[target], validation_prob) if len(validation_prob) else (0.5, -1.0)
            trained_models[algorithm] = model
            thresholds[algorithm] = threshold
            validation_f1[algorithm] = threshold_f1
            importances.append(extract_importance(model, full_name))
        else:
            thresholds[algorithm] = 0.5
            validation_f1[algorithm] = 0.0
    champion_algorithm = max(validation_f1, key=validation_f1.get)
    for algorithm in algorithms:
        full_name = f"{model_name} - {algorithm}"
        threshold = thresholds[algorithm]
        for split_name, split_frame in [("validation", validation), ("test", test)]:
            if split_frame.empty:
                continue
            if SKLEARN_AVAILABLE:
                y_prob = probabilities_from_model(trained_models[algorithm], split_frame, features)
                y_pred = (y_prob >= threshold).astype(int)
            else:
                y_pred, y_prob, importance = fallback_predict(train, target, split_frame)
                importances.append(importance)
            metrics = classification_metrics(split_frame[target], y_pred, y_prob)
            baseline = majority_baseline(train, split_frame, target)
            eval_rows.append({
                "model_name": full_name,
                "split": split_name,
                "target": target,
                "dependency_mode": "sklearn" if SKLEARN_AVAILABLE else dependency_mode,
                "threshold": threshold,
                "is_champion": algorithm == champion_algorithm,
                **metrics,
                "baseline_f1": baseline["f1"],
                "baseline_accuracy": baseline["accuracy"],
            })
            if algorithm == champion_algorithm:
                predictions = split_frame.copy()
                predictions[f"predicted_{target}"] = y_pred
                predictions[f"predicted_{target}_probability"] = y_prob
                predictions["model_name"] = full_name
                predictions["model_algorithm"] = algorithm
                predictions["model_threshold"] = threshold
                prediction_frames.append(predictions)
    return (
        pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame(),
        pd.concat(importances, ignore_index=True) if importances else pd.DataFrame(),
        {
            "model_name": model_name,
            "trained": True,
            "dependency_mode": "sklearn_model_comparison" if SKLEARN_AVAILABLE else dependency_mode,
            "champion_algorithm": champion_algorithm,
            "champion_validation_f1": validation_f1[champion_algorithm],
            "thresholds": thresholds,
            "metrics": eval_rows,
        },
    )


def train_loss_priority_model(dataset: pd.DataFrame, features: list[str], shock_predictions: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    train = dataset[dataset["split"] == "train"].dropna(subset=["estimated_loss_amount"]).copy()
    validation = dataset[dataset["split"] == "validation"].dropna(subset=["estimated_loss_amount"]).copy()
    test = dataset[dataset["split"] == "test"].dropna(subset=["estimated_loss_amount"]).copy()
    prediction_frames: list[pd.DataFrame] = []
    metric_rows: list[dict[str, object]] = []
    importance = pd.DataFrame(columns=["model_name", "feature", "importance", "directional_coefficient"])
    if train.empty:
        return pd.DataFrame(), importance, pd.DataFrame(), {"model_name": "Loss Priority regressor", "trained": False, "reason": "empty training data"}
    prediction_cap = float(pd.to_numeric(train["estimated_loss_amount"], errors="coerce").fillna(0).quantile(0.99))
    if SKLEARN_AVAILABLE:
        model = make_model_pipeline(features, train, "ridge_regression")
        train_target_log = np.log1p(pd.to_numeric(train["estimated_loss_amount"], errors="coerce").fillna(0))
        model.fit(train[features], train_target_log)
        importance = extract_importance(model, "Loss Priority regressor - ridge_log_loss")
    else:
        model = None
        group_loss = train.groupby(["merchant_region", "industry"])["estimated_loss_amount"].median().rename("fallback_loss").reset_index()
        global_loss = float(train["estimated_loss_amount"].median())
    shock_keys = ["date", "merchant_region", "industry", "predicted_shock_pulse_label_probability"]
    shock_scores = shock_predictions[shock_keys].copy() if not shock_predictions.empty else pd.DataFrame(columns=shock_keys)
    for split_name, split_frame in [("validation", validation), ("test", test)]:
        if split_frame.empty:
            continue
        predictions = split_frame.copy()
        if SKLEARN_AVAILABLE:
            predicted_loss = np.expm1(model.predict(split_frame[features]))
            predictions["predicted_estimated_loss_amount"] = np.clip(predicted_loss, 0, prediction_cap)
        else:
            predictions = predictions.merge(group_loss, on=["merchant_region", "industry"], how="left", validate="many_to_one")
            predictions["predicted_estimated_loss_amount"] = predictions["fallback_loss"].fillna(global_loss).clip(lower=0, upper=prediction_cap)
            predictions = predictions.drop(columns=["fallback_loss"])
        predictions = predictions.merge(shock_scores, on=["date", "merchant_region", "industry"], how="left", validate="one_to_one")
        predictions["predicted_shock_pulse_label_probability"] = predictions["predicted_shock_pulse_label_probability"].fillna(0)
        predictions["predicted_support_priority_score"] = predictions["predicted_estimated_loss_amount"] * predictions["predicted_shock_pulse_label_probability"]
        predictions["support_priority_rank"] = predictions["predicted_support_priority_score"].rank(method="first", ascending=False).astype(int)
        predictions["support_priority_percentile"] = predictions["predicted_support_priority_score"].rank(method="average", pct=True)
        predictions["model_name"] = "Loss Priority regressor - ridge_log_loss" if SKLEARN_AVAILABLE else "Loss Priority regressor - fallback_group_median_loss"
        metric_rows.append(loss_ranking_metrics(predictions, split_name))
        prediction_frames.append(predictions)
    all_predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    summary = build_loss_priority_summary(all_predictions)
    return all_predictions, importance, summary, {"model_name": "Loss Priority regressor", "trained": True, "target": "estimated_loss_amount", "features": features, "prediction_cap_source": "train_period_estimated_loss_amount_p99", "prediction_cap": prediction_cap, "metrics": metric_rows}


def build_loss_priority_summary(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame(columns=["merchant_region", "industry", "predicted_total_loss_priority", "observed_total_estimated_loss", "mean_predicted_support_priority_score", "mean_predicted_shock_pulse_risk", "priority_rank", "ecg_interpretation"])
    summary = predictions.groupby(["merchant_region", "industry"], as_index=False).agg(
        predicted_total_loss_priority=("predicted_support_priority_score", "sum"),
        observed_total_estimated_loss=("estimated_loss_amount", "sum"),
        mean_predicted_support_priority_score=("predicted_support_priority_score", "mean"),
        mean_predicted_shock_pulse_risk=("predicted_shock_pulse_label_probability", "mean"),
    )
    summary = summary.sort_values("predicted_total_loss_priority", ascending=False).reset_index(drop=True)
    summary["priority_rank"] = np.arange(1, len(summary) + 1)
    summary["ecg_interpretation"] = "loss_priority_predictive_ranking_not_causal_or_final_policy_decision"
    return summary


def build_triage_scores(shock_predictions: pd.DataFrame, recovery_predictions: pd.DataFrame, event_data: pd.DataFrame) -> pd.DataFrame:
    shock_summary = shock_predictions.groupby(["merchant_region", "industry"], as_index=False).agg(predicted_shock_pulse_risk=("predicted_shock_pulse_label_probability", "mean")) if not shock_predictions.empty else pd.DataFrame(columns=["merchant_region", "industry", "predicted_shock_pulse_risk"])
    recovery_summary = recovery_predictions.groupby(["merchant_region", "industry"], as_index=False).agg(predicted_recovery_clock_risk=("predicted_recovery_clock_label_probability", "mean")) if not recovery_predictions.empty else pd.DataFrame(columns=["merchant_region", "industry", "predicted_recovery_clock_risk"])
    scar_summary = event_data.groupby(["merchant_region", "industry"], as_index=False).agg(climate_scar_score=("climate_scar_score", "median"), observed_event_count=("event_date", "count"))
    triage = scar_summary.merge(shock_summary, on=["merchant_region", "industry"], how="left")
    triage = triage.merge(recovery_summary, on=["merchant_region", "industry"], how="left")
    triage[["predicted_shock_pulse_risk", "predicted_recovery_clock_risk"]] = triage[["predicted_shock_pulse_risk", "predicted_recovery_clock_risk"]].fillna(0)
    max_scar = triage["climate_scar_score"].max()
    triage["normalized_climate_scar"] = triage["climate_scar_score"] / max_scar if max_scar else 0
    triage["climate_ecg_triage_score"] = (
        triage["predicted_shock_pulse_risk"] * 55
        + triage["predicted_recovery_clock_risk"] * 15
        + triage["normalized_climate_scar"] * 30
    )
    triage["ecg_interpretation"] = "exploratory_predictive_decision_support_not_causal_or_final_policy_decision"
    return triage.sort_values("climate_ecg_triage_score", ascending=False)


def build_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for table, frame in tables.items():
        for column in frame.columns:
            rows.append({"table": table, "column": column, "dtype": str(frame[column].dtype), "description": column.replace("_", " ")})
    return pd.DataFrame(rows)


def validate_outputs(analysis_dir: Path, tables: dict[str, pd.DataFrame], model_card: dict[str, object], manifest: dict[str, object]) -> dict[str, object]:
    checks = [
        CheckResult("analysis_quality_passed", json.loads((analysis_dir / "quality_report.json").read_text(encoding="utf-8")).get("status") == "passed", "analysis quality must pass"),
        check_no_raw_paths([str(path) for path in manifest.get("analysis_inputs", {}).keys()], "no_raw_input_paths"),
        check_required_columns(tables["model_ready_daily.csv"], ["shock_pulse_label", "split", "estimated_loss_amount", "model_baseline_sales_amount", "baseline_source"], "daily_model_columns"),
        check_required_columns(tables["model_ready_event.csv"], ["recovery_clock_label", "climate_scar_score", "split"], "event_model_columns"),
        check_required_columns(tables["loss_priority_predictions.csv"], ["estimated_loss_amount", "predicted_estimated_loss_amount", "predicted_support_priority_score", "support_priority_rank", "split"], "loss_priority_prediction_columns"),
        check_required_columns(tables["topk_support_priority_metrics.csv"], ["split", "top5_loss_capture", "top10_loss_capture", "top20_loss_capture", "top10_lift", "total_loss"], "topk_support_priority_metric_columns"),
        check_chronological_split(tables["model_ready_daily.csv"], "date", "split", "daily_chronological_split"),
        check_chronological_split(tables["model_ready_event.csv"], "event_date", "split", "event_chronological_split"),
        check_loss_priority_evaluation_split(tables["loss_priority_predictions.csv"]),
        check_train_only_baselines(analysis_dir, tables["model_ready_daily.csv"]),
        check_shifted_history_features(tables["model_ready_daily.csv"]),
        check_no_forbidden_features(model_card["models"]["shock_pulse"]["features"], "shock_pulse_no_leakage_features"),
        check_no_forbidden_features(model_card["models"]["loss_priority"]["features"], "loss_priority_no_leakage_features"),
        check_unique(tables["triage_score_by_region_industry.csv"], ["merchant_region", "industry"], "triage_unique_key"),
        check_unique(tables["loss_priority_by_region_industry.csv"], ["merchant_region", "industry"], "loss_priority_unique_key"),
        CheckResult("non_causal_interpretation", "not causal" in model_card["interpretation"], model_card["interpretation"]),
    ]
    return summarize_checks(checks)


def run_build(analysis_dir: Path, out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    loaded = load_analysis(analysis_dir)
    daily_model = build_model_ready_daily(loaded["daily"])
    event_model = build_model_ready_event(loaded["events"], loaded["shock"], loaded["timeband"], loaded["inflow"], loaded["priority"])

    shock_predictions, shock_importance, shock_result = train_classifier(daily_model, DAILY_FEATURES, "shock_pulse_label", "Shock Pulse classifier")
    weather_shock_predictions, weather_shock_importance, weather_shock_result = train_classifier(daily_model, DAILY_FEATURES, "weather_shock_label", "Weather-conditioned Shock classifier")
    recovery_predictions, recovery_importance, recovery_result = train_classifier(event_model, EVENT_FEATURES, "recovery_clock_label", "Recovery Clock classifier")
    loss_predictions, loss_importance, loss_priority, loss_result = train_loss_priority_model(daily_model, LOSS_PRIORITY_FEATURES, shock_predictions)
    feature_frames = [shock_importance, weather_shock_importance, recovery_importance, loss_importance]
    feature_importance = pd.concat([frame for frame in feature_frames if not frame.empty], ignore_index=True) if any(not frame.empty for frame in feature_frames) else pd.DataFrame(columns=["model_name", "feature", "importance"])
    performance_rows = []
    for result in [shock_result, weather_shock_result, recovery_result, loss_result]:
        for metric in result.get("metrics", []):
            performance_rows.append(metric)
    performance = pd.DataFrame(performance_rows)
    topk_metrics = pd.DataFrame(loss_result.get("metrics", []))
    triage = build_triage_scores(shock_predictions, recovery_predictions, event_model)

    tables = {
        "model_ready_daily.csv": daily_model,
        "model_ready_event.csv": event_model,
        "shock_pulse_predictions.csv": shock_predictions,
        "weather_shock_predictions.csv": weather_shock_predictions,
        "recovery_clock_predictions.csv": recovery_predictions,
        "loss_priority_predictions.csv": loss_predictions,
        "loss_priority_by_region_industry.csv": loss_priority,
        "topk_support_priority_metrics.csv": topk_metrics,
        "triage_score_by_region_industry.csv": triage,
        "model_performance.csv": performance,
        "feature_importance.csv": feature_importance,
    }
    for name, frame in tables.items():
        write_csv(frame, out_dir / name)
    dictionary = build_dictionary(tables)
    write_csv(dictionary, out_dir / "data_dictionary.csv")
    model_card = {
        "project_frame": "Climate ECG",
        "components": {
            "Shock Pulse": "classifier for daily high negative sales deviation during weather stress",
            "Recovery Clock": "classifier for delayed or incomplete event-window recovery",
            "Climate Scar": "observed post-event residual damage score",
            "Triage Score": "decision-support score combining predicted shock risk, recovery risk, and scar score",
        },
        "models": {
            "shock_pulse": {"target": "shock_pulse_label", "features": DAILY_FEATURES, **shock_result},
            "weather_conditioned_shock": {"target": "weather_shock_label", "features": DAILY_FEATURES, **weather_shock_result},
            "recovery_clock": {"target": "recovery_clock_label", "features": EVENT_FEATURES, **recovery_result},
            "loss_priority": loss_result,
        },
        "split_policy": {
            "shock_pulse": "fixed chronological split: train through 2025-10-31, validation through 2025-11-30, test in 2025-12",
            "recovery_clock": "fractional chronological split over available heavy-rain event dates because events do not span all months",
        },
        "leakage_policy": "daily targets and loss estimates use train-period region-industry-weekday median baselines; same-day sales-derived columns are labels/outcomes and excluded from Shock Pulse features; lag/history features are strictly shifted before the prediction row",
        "performance_framing": {
            "primary_model": "Shock Pulse classifier",
            "weather_conditioned_note": "Weather-conditioned Shock is a rare-target weather-filtered view. Present PR-AUC, precision, base rate, and top-k recall before ROC-AUC; do not describe high ROC-AUC as near-perfect prediction.",
            "primary_metric_note": "Use ROC-AUC, F1, and recall/precision tradeoff rather than accuracy alone because the majority baseline has high accuracy but zero positive-class F1.",
            "recovery_clock_note": "Recovery Clock remains exploratory because event samples are smaller and the signal is broad; it is downweighted in triage even when tuned F1 is competitive with the majority baseline.",
            "loss_priority_note": "Loss Priority ranks rows for support triage by combining log-scale predicted baseline-relative loss with Shock Pulse risk. Judge it primarily by top-k loss capture and lift, not calibrated won-level accuracy. Treat estimated_loss_amount as modeled baseline-relative loss, not audited financial damage.",
            "prediction_file_note": "Prediction CSVs are same-day/retrospective aggregate evaluation artifacts and include observed labels/outcomes for validation, not prospective deployment outputs. Prospective use requires forecast weather inputs.",
        },
        "triage_weights": {"predicted_shock_pulse_risk": 55, "predicted_recovery_clock_risk_exploratory": 15, "normalized_climate_scar": 30},
        "interpretation": "predictive aggregate decision support, not causal estimates or final policy decisions",
    }
    manifest = {
        "status": "built",
        "analysis_dir": str(analysis_dir),
        "analysis_inputs": {str(analysis_dir / filename): {"bytes": (analysis_dir / filename).stat().st_size, "sha256": file_sha256(analysis_dir / filename)} for filename in REQUIRED_INPUTS.values()},
        "thresholds": {"shock_threshold_pct": SHOCK_THRESHOLD_PCT, "recovery_threshold_pct": RECOVERY_THRESHOLD_PCT},
        "triage_weights": {"predicted_shock_pulse_risk": 55, "predicted_recovery_clock_risk_exploratory": 15, "normalized_climate_scar": 30},
        "dependency_mode": "sklearn" if SKLEARN_AVAILABLE else "fallback_group_rate",
        "outputs": {name: {"rows": len(frame), "columns": list(frame.columns)} for name, frame in tables.items()},
    }
    performance_json = {"models": [shock_result, weather_shock_result, recovery_result, loss_result], "performance_rows": records(performance) if not performance.empty else [], "topk_support_priority_metrics": records(topk_metrics) if not topk_metrics.empty else []}
    bundle = {
        "metadata": {"schema_version": "1.0", "project_frame": "Climate ECG", "source": str(analysis_dir), "interpretation": model_card["interpretation"]},
        "model_card": model_card,
        "performance": performance_json,
        "triage_top20": records(triage, 20),
        "loss_priority_top20": records(loss_priority, 20),
        "feature_importance_top40": records(feature_importance.sort_values("importance", ascending=False), 40) if not feature_importance.empty else [],
    }
    quality = validate_outputs(analysis_dir, tables, model_card, manifest)
    bundle["quality"] = quality
    write_json(model_card, out_dir / "model_card.json")
    write_json(performance_json, out_dir / "model_performance.json")
    write_json(bundle, out_dir / "flowshock_modeling_bundle.json")
    write_json(manifest, out_dir / "manifest.json")
    write_json(quality, out_dir / "quality_report.json")
    return quality


def load_output_tables(out_dir: Path) -> dict[str, pd.DataFrame]:
    filenames = [
        "model_ready_daily.csv",
        "model_ready_event.csv",
        "shock_pulse_predictions.csv",
        "weather_shock_predictions.csv",
        "recovery_clock_predictions.csv",
        "loss_priority_predictions.csv",
        "loss_priority_by_region_industry.csv",
        "topk_support_priority_metrics.csv",
        "triage_score_by_region_industry.csv",
        "model_performance.csv",
        "feature_importance.csv",
    ]
    missing = [filename for filename in filenames if not (out_dir / filename).exists()]
    if missing:
        raise FileNotFoundError(f"Missing modeling outputs: {missing}")
    return {filename: pd.read_csv(out_dir / filename, encoding="utf-8-sig", low_memory=False) for filename in filenames}


def run_check_only(analysis_dir: Path, out_dir: Path) -> dict[str, object]:
    tables = load_output_tables(out_dir)
    model_card = json.loads((out_dir / "model_card.json").read_text(encoding="utf-8"))
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    quality = validate_outputs(analysis_dir, tables, model_card, manifest)
    write_json(quality, out_dir / "quality_report.json")
    return quality


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FlowShock Climate ECG modeling outputs")
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS, help="FlowShock analysis output directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Modeling output directory")
    parser.add_argument("--check-only", action="store_true", help="Validate existing modeling outputs without rebuilding")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    analysis_dir = resolve_path(args.analysis_dir)
    out_dir = resolve_path(args.out)
    quality = run_check_only(analysis_dir, out_dir) if args.check_only else run_build(analysis_dir, out_dir)
    print(json.dumps({"status": quality["status"], "out_dir": str(out_dir), "quality_report": str(out_dir / "quality_report.json")}, ensure_ascii=False, indent=2))
    return 0 if quality["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
