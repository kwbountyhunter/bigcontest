from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from .quality_checks import (
        CheckResult,
        check_daily_grain_safety,
        check_json_field_safety,
        check_nonnegative,
        check_required_columns,
        check_unique,
        summarize_checks,
    )
except ImportError:
    from quality_checks import (
        CheckResult,
        check_daily_grain_safety,
        check_json_field_safety,
        check_nonnegative,
        check_required_columns,
        check_unique,
        summarize_checks,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOUNDATION = ROOT / "analysis" / "flowshock_foundation" / "out"
DEFAULT_OUT = Path(__file__).resolve().parent / "out"

HEAVY_RAIN_MM = 20.0
TIMEBAND_HEAVY_RAIN_MM = 5.0
MIN_EVENT_COUNT = 5

REQUIRED_INPUTS = {
    "daily": "mart_daily_region_industry_weather.csv",
    "timeband": "mart_timeband_region_industry_weather.csv",
    "inflow": "card2_month_region_customer_inflow.csv",
    "month_timeband": "mart_month_timeband_profile.csv",
    "foundation_manifest": "manifest.json",
    "foundation_quality": "quality_report.json",
}

OUTPUT_TABLES = {
    "daily_baseline_panel.csv": ["date", "merchant_region", "industry"],
    "rain_bin_response_by_region_industry.csv": ["merchant_region", "industry", "rain_bin"],
    "event_window_metrics_by_industry.csv": ["merchant_region", "industry", "event_group_id", "event_date"],
    "shock_recovery_metrics_by_industry.csv": ["merchant_region", "industry"],
    "timeband_vulnerability_metrics.csv": ["merchant_region", "industry", "time_band"],
    "broad_area_inflow_context.csv": ["month", "merchant_region"],
    "support_priority_by_industry.csv": ["merchant_region", "industry"],
}


def safe_div(numerator: object, denominator: object) -> object:
    num = pd.Series(numerator) if not isinstance(numerator, pd.Series) else numerator
    den = pd.Series(denominator) if not isinstance(denominator, pd.Series) else denominator
    result = np.where((den != 0) & (~pd.isna(den)), num / den, np.nan)
    if np.ndim(result) == 0:
        return float(result)
    return result


def records(df: pd.DataFrame, limit: int | None = None) -> list[dict[str, object]]:
    frame = df if limit is None else df.head(limit)
    return json.loads(frame.replace({np.nan: None}).to_json(orient="records", force_ascii=False))


def assign_rain_bin(series: pd.Series) -> pd.Series:
    return pd.cut(
        series.fillna(0),
        [-0.001, 0, 5, 20, 50, float("inf")],
        labels=["0", "0-5", "5-20", "20-50", "50+"],
    ).astype(str)


def add_daily_baseline(daily: pd.DataFrame) -> pd.DataFrame:
    frame = daily.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    baseline = frame.groupby(["merchant_region", "industry", "day_of_week"], as_index=False).agg(
        baseline_sales_amount=("sales_amount", "median"),
        baseline_use_count=("use_count", "median"),
    )
    frame = frame.merge(baseline, on=["merchant_region", "industry", "day_of_week"], how="left", validate="many_to_one")
    frame["sales_idx"] = safe_div(frame["sales_amount"], frame["baseline_sales_amount"])
    frame["use_count_idx"] = safe_div(frame["use_count"], frame["baseline_use_count"])
    frame["sales_dev_pct"] = (frame["sales_idx"] - 1) * 100
    frame["use_count_dev_pct"] = (frame["use_count_idx"] - 1) * 100
    frame["rain_bin"] = assign_rain_bin(frame["daily_rain_mm"])
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    return frame


def detect_heavy_rain_events(weather_daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    weather = weather_daily.copy()
    weather["date"] = pd.to_datetime(weather["date"])
    for region, group in weather.sort_values("date").groupby("merchant_region"):
        group_id = 0
        previous_heavy = False
        for row in group.itertuples(index=False):
            is_heavy = float(row.daily_rain_mm) >= HEAVY_RAIN_MM
            if is_heavy and not previous_heavy:
                group_id += 1
            if is_heavy:
                rows.append(
                    {
                        "merchant_region": region,
                        "event_group_id": group_id,
                        "event_date": row.date.strftime("%Y-%m-%d"),
                        "event_rain_mm": float(row.daily_rain_mm),
                    }
                )
            previous_heavy = is_heavy
    return pd.DataFrame(rows)


def mean_or_nan(values: list[float]) -> float:
    arr = np.array(values, dtype="float64")
    arr = arr[~np.isnan(arr)]
    return float(arr.mean()) if len(arr) else np.nan


def build_event_windows(daily_panel: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return pd.DataFrame(
            columns=[
                "merchant_region",
                "industry",
                "event_group_id",
                "event_date",
                "event_rain_mm",
                "pre3_sales_dev_pct",
                "d0_sales_dev_pct",
                "post3_sales_dev_pct",
                "rebound_pp",
                "net_damage_pp",
                "missing_window_days",
            ]
        )
    frame = daily_panel.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    rows: list[dict[str, object]] = []
    for event in events.itertuples(index=False):
        event_date = pd.to_datetime(event.event_date)
        region_panel = frame[frame["merchant_region"] == event.merchant_region]
        for industry, group in region_panel.groupby("industry"):
            window = group[(group["date"] >= event_date - pd.Timedelta(days=3)) & (group["date"] <= event_date + pd.Timedelta(days=3))]
            by_offset = {int((row.date - event_date).days): row.sales_dev_pct for row in window.itertuples(index=False)}
            pre3 = mean_or_nan([by_offset.get(-3, np.nan), by_offset.get(-2, np.nan), by_offset.get(-1, np.nan)])
            d0 = by_offset.get(0, np.nan)
            post3 = mean_or_nan([by_offset.get(1, np.nan), by_offset.get(2, np.nan), by_offset.get(3, np.nan)])
            rows.append(
                {
                    "merchant_region": event.merchant_region,
                    "industry": industry,
                    "event_group_id": int(event.event_group_id),
                    "event_date": event.event_date,
                    "event_rain_mm": float(event.event_rain_mm),
                    "pre3_sales_dev_pct": pre3,
                    "d0_sales_dev_pct": d0,
                    "post3_sales_dev_pct": post3,
                    "rebound_pp": post3 - d0 if pd.notna(post3) and pd.notna(d0) else np.nan,
                    "net_damage_pp": post3 - pre3 if pd.notna(post3) and pd.notna(pre3) else np.nan,
                    "missing_window_days": 7 - len(by_offset),
                }
            )
    return pd.DataFrame(rows)


def build_shock_metrics(daily_panel: pd.DataFrame, event_windows: pd.DataFrame) -> pd.DataFrame:
    daily_rows: list[dict[str, object]] = []
    for (region, industry), group in daily_panel.groupby(["merchant_region", "industry"]):
        valid = group.dropna(subset=["daily_rain_mm", "sales_dev_pct"])
        dry = valid[valid["daily_rain_mm"] == 0]
        heavy = valid[valid["daily_rain_mm"] >= HEAVY_RAIN_MM]
        spearman = np.nan
        if len(valid) >= 30 and valid["daily_rain_mm"].nunique() > 1:
            spearman = valid["daily_rain_mm"].corr(valid["sales_dev_pct"], method="spearman")
        daily_rows.append(
            {
                "merchant_region": region,
                "industry": industry,
                "n_days": int(len(valid)),
                "rain_days": int((valid["daily_rain_mm"] > 0).sum()),
                "heavy20_days": int(len(heavy)),
                "rain_sales_spearman": spearman,
                "median_sales_dev_dry": dry["sales_dev_pct"].median() if len(dry) else np.nan,
                "median_sales_dev_heavy20": heavy["sales_dev_pct"].median() if len(heavy) else np.nan,
                "median_heavy20_minus_dry_pp": (heavy["sales_dev_pct"].median() - dry["sales_dev_pct"].median()) if len(heavy) and len(dry) else np.nan,
            }
        )
    metrics = pd.DataFrame(daily_rows)
    if not event_windows.empty:
        event_summary = event_windows.groupby(["merchant_region", "industry"], as_index=False).agg(
            event_count=("event_date", "count"),
            median_event_rain_mm=("event_rain_mm", "median"),
            median_pre3_sales_dev_pct=("pre3_sales_dev_pct", "median"),
            median_initial_shock_pp=("d0_sales_dev_pct", "median"),
            median_post3_sales_dev_pct=("post3_sales_dev_pct", "median"),
            median_rebound_pp=("rebound_pp", "median"),
            median_net_damage_pp=("net_damage_pp", "median"),
            negative_shock_share=("d0_sales_dev_pct", lambda s: float((s.dropna() < 0).mean()) if len(s.dropna()) else np.nan),
            persistent_damage_share=("post3_sales_dev_pct", lambda s: float((s.dropna() < 0).mean()) if len(s.dropna()) else np.nan),
            missing_d0_share=("d0_sales_dev_pct", lambda s: float(s.isna().mean())),
            avg_missing_window_days=("missing_window_days", "mean"),
        )
        metrics = metrics.merge(event_summary, on=["merchant_region", "industry"], how="left")
    for column in [
        "event_count",
        "median_event_rain_mm",
        "median_pre3_sales_dev_pct",
        "median_initial_shock_pp",
        "median_post3_sales_dev_pct",
        "median_rebound_pp",
        "median_net_damage_pp",
        "negative_shock_share",
        "persistent_damage_share",
        "missing_d0_share",
        "avg_missing_window_days",
    ]:
        if column not in metrics.columns:
            metrics[column] = np.nan
    metrics["event_count"] = metrics["event_count"].fillna(0).astype(int)
    metrics["low_event_count_flag"] = metrics["event_count"] < MIN_EVENT_COUNT
    metrics["baseline_sensitivity_flag"] = metrics["heavy20_days"] < 3
    return metrics


def build_rain_bin_response(daily_panel: pd.DataFrame) -> pd.DataFrame:
    return daily_panel.groupby(["merchant_region", "industry", "rain_bin"], as_index=False, observed=False).agg(
        rows=("sales_dev_pct", "count"),
        median_sales_dev_pct=("sales_dev_pct", "median"),
        mean_sales_dev_pct=("sales_dev_pct", "mean"),
        median_use_count_dev_pct=("use_count_dev_pct", "median"),
    )


def build_timeband_metrics(timeband: pd.DataFrame) -> pd.DataFrame:
    frame = timeband.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    baseline = frame.groupby(["merchant_region", "industry", "time_band", "day_of_week"], as_index=False).agg(
        baseline_sales_amount=("sales_amount", "median")
    )
    frame = frame.merge(baseline, on=["merchant_region", "industry", "time_band", "day_of_week"], how="left", validate="many_to_one")
    frame["sales_dev_pct"] = (safe_div(frame["sales_amount"], frame["baseline_sales_amount"]) - 1) * 100
    rows: list[dict[str, object]] = []
    for (region, industry, time_band), group in frame.groupby(["merchant_region", "industry", "time_band"]):
        valid = group.dropna(subset=["rain_timeband_mm", "sales_dev_pct"])
        dry = valid[valid["rain_timeband_mm"] == 0]
        heavy = valid[valid["rain_timeband_mm"] >= TIMEBAND_HEAVY_RAIN_MM]
        spearman = np.nan
        if len(valid) >= 30 and valid["rain_timeband_mm"].nunique() > 1:
            spearman = valid["rain_timeband_mm"].corr(valid["sales_dev_pct"], method="spearman")
        rows.append(
            {
                "merchant_region": region,
                "industry": industry,
                "time_band": time_band,
                "rows": int(len(valid)),
                "rain_band_rows": int((valid["rain_timeband_mm"] > 0).sum()),
                "heavy5_rows": int(len(heavy)),
                "rain_sales_spearman": spearman,
                "median_sales_dev_dry": dry["sales_dev_pct"].median() if len(dry) else np.nan,
                "median_sales_dev_heavy5": heavy["sales_dev_pct"].median() if len(heavy) else np.nan,
                "median_heavy5_minus_dry_pp": (heavy["sales_dev_pct"].median() - dry["sales_dev_pct"].median()) if len(heavy) and len(dry) else np.nan,
                "weather_missing_rows": int(frame.loc[group.index, "weather_timeband_missing"].sum()) if "weather_timeband_missing" in frame.columns else 0,
            }
        )
    return pd.DataFrame(rows)


def merchant_home_area(region: str) -> str:
    if region.startswith("서울"):
        return "서울"
    if region.startswith("강원"):
        return "강원"
    return region.split()[0]


def build_broad_area_context(inflow: pd.DataFrame) -> pd.DataFrame:
    frame = inflow.copy()
    frame["merchant_home_broad_area"] = frame["merchant_region"].map(merchant_home_area)
    frame["is_same_broad_area"] = frame["customer_broad_area"] == frame["merchant_home_broad_area"]
    summary = frame.groupby(["month", "merchant_region"], as_index=False).agg(
        same_broad_area_sales_amount=("sales_amount", lambda s: float(s[frame.loc[s.index, "is_same_broad_area"]].sum())),
        total_sales_amount=("sales_amount", "sum"),
        customer_broad_area_count=("customer_broad_area", "nunique"),
    )
    summary["same_broad_area_sales_share"] = safe_div(summary["same_broad_area_sales_amount"], summary["total_sales_amount"])
    summary["other_broad_area_sales_share"] = 1 - summary["same_broad_area_sales_share"]
    summary["customer_origin_scope"] = "broad_area_not_district"
    return summary


def normalize_positive(series: pd.Series) -> pd.Series:
    clean = pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=0)
    max_value = clean.max()
    if pd.isna(max_value) or max_value == 0:
        return clean * 0
    return clean / max_value


def build_support_priority(shock: pd.DataFrame, timeband_metrics: pd.DataFrame, inflow_context: pd.DataFrame) -> pd.DataFrame:
    timeband_summary = timeband_metrics.groupby(["merchant_region", "industry"], as_index=False).agg(
        strongest_negative_timeband_corr=("rain_sales_spearman", "min"),
        weakest_timeband_heavy5_minus_dry_pp=("median_heavy5_minus_dry_pp", "min"),
        negative_timeband_count=("rain_sales_spearman", lambda s: int((s < 0).sum())),
    )
    inflow_summary = inflow_context.groupby("merchant_region", as_index=False).agg(
        avg_other_broad_area_sales_share=("other_broad_area_sales_share", "mean"),
        avg_same_broad_area_sales_share=("same_broad_area_sales_share", "mean"),
    )
    priority = shock.merge(timeband_summary, on=["merchant_region", "industry"], how="left")
    priority = priority.merge(inflow_summary, on="merchant_region", how="left")
    priority["shock_sensitivity_component"] = normalize_positive(-priority["median_heavy20_minus_dry_pp"].clip(upper=0))
    priority["initial_shock_component"] = normalize_positive(-priority["median_initial_shock_pp"].clip(upper=0))
    priority["net_damage_component"] = normalize_positive(-priority["median_net_damage_pp"].clip(upper=0))
    priority["persistence_component"] = priority["persistent_damage_share"].fillna(0).clip(0, 1)
    priority["timeband_component"] = normalize_positive(-priority["weakest_timeband_heavy5_minus_dry_pp"].clip(upper=0))
    priority["external_inflow_component"] = priority["avg_other_broad_area_sales_share"].fillna(0).clip(0, 1)
    priority["support_priority_score"] = (
        priority["shock_sensitivity_component"] * 30
        + priority["initial_shock_component"] * 20
        + priority["net_damage_component"] * 15
        + priority["persistence_component"] * 15
        + priority["timeband_component"] * 10
        + priority["external_inflow_component"] * 10
    )
    priority["reliability_flag"] = np.where(
        priority["low_event_count_flag"] | priority["baseline_sensitivity_flag"],
        "review_required",
        "usable",
    )
    priority.loc[priority["reliability_flag"] == "review_required", "support_priority_score"] *= 0.8
    priority["interpretation"] = "observed_aggregate_association_not_causal_estimate"
    return priority.sort_values("support_priority_score", ascending=False)


def build_web_payloads(
    foundation_dir: Path,
    daily_panel: pd.DataFrame,
    shock: pd.DataFrame,
    priority: pd.DataFrame,
    timeband_metrics: pd.DataFrame,
    inflow_context: pd.DataFrame,
    month_timeband: pd.DataFrame,
    quality: dict[str, object],
    foundation_manifest: dict[str, object],
) -> dict[str, object]:
    regional_dashboard = daily_panel.groupby("merchant_region", as_index=False).agg(
        days=("date", "nunique"),
        industries=("industry", "nunique"),
        total_sales_amount=("sales_amount", "sum"),
        rain_days=("daily_rain_mm", lambda s: int((s > 0).sum())),
        heavy20_days=("daily_rain_mm", lambda s: int((s >= HEAVY_RAIN_MM).sum())),
        median_sales_dev_pct=("sales_dev_pct", "median"),
    )
    vulnerability_matrix = priority[[
        "merchant_region",
        "industry",
        "support_priority_score",
        "median_heavy20_minus_dry_pp",
        "median_initial_shock_pp",
        "median_net_damage_pp",
        "persistent_damage_share",
        "avg_other_broad_area_sales_share",
        "reliability_flag",
    ]].copy()
    policy_brief = {
        "interpretation": "Observed aggregate associations only; not causal estimates.",
        "top_priority_candidates": records(priority.head(10)),
        "regional_summary": records(regional_dashboard),
        "method_notes": [
            "Daily baseline is region x industry x weekday median sales.",
            "Heavy-rain event threshold is daily_rain_mm >= 20.",
            "SKT profiles remain monthly aggregate context and are not joined to daily rows.",
            "Customer origin uses broad-area/province categories, not district residence.",
        ],
    }
    return {
        "metadata": {
            "schema_version": "1.0",
            "source": str(foundation_dir),
            "period": foundation_manifest.get("period", {}),
            "interpretation": "observed aggregate associations, not causal estimates",
        },
        "quality": quality,
        "regional_dashboard": records(regional_dashboard),
        "vulnerability_matrix": records(vulnerability_matrix.head(60)),
        "support_priority": records(priority.head(40)),
        "policy_brief": policy_brief,
        "context": {
            "broad_area_inflow": records(inflow_context),
            "month_timeband_profile": records(month_timeband),
            "timeband_vulnerability": records(timeband_metrics.head(80)),
        },
    }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_json(payload: object, path: Path) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_foundation(foundation_dir: Path) -> dict[str, object]:
    missing = [name for name in REQUIRED_INPUTS.values() if not (foundation_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing foundation inputs: {missing}")
    return {
        "daily": pd.read_csv(foundation_dir / REQUIRED_INPUTS["daily"], encoding="utf-8-sig", low_memory=False),
        "timeband": pd.read_csv(foundation_dir / REQUIRED_INPUTS["timeband"], encoding="utf-8-sig", low_memory=False),
        "inflow": pd.read_csv(foundation_dir / REQUIRED_INPUTS["inflow"], encoding="utf-8-sig", low_memory=False),
        "month_timeband": pd.read_csv(foundation_dir / REQUIRED_INPUTS["month_timeband"], encoding="utf-8-sig", low_memory=False),
        "foundation_manifest": json.loads((foundation_dir / REQUIRED_INPUTS["foundation_manifest"]).read_text(encoding="utf-8")),
        "foundation_quality": json.loads((foundation_dir / REQUIRED_INPUTS["foundation_quality"]).read_text(encoding="utf-8")),
    }


def build_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    descriptions = {
        "merchant_region": "Merchant analysis region",
        "industry": "Merchant industry category",
        "support_priority_score": "Candidate support-priority score from aggregate association metrics",
        "customer_origin_scope": "Broad-area origin semantics, not district residence",
        "interpretation": "Interpretation guardrail for non-causal aggregate metrics",
    }
    rows: list[dict[str, object]] = []
    for table_name, frame in tables.items():
        keys = OUTPUT_TABLES.get(table_name, [])
        for column in frame.columns:
            rows.append(
                {
                    "table": table_name,
                    "column": column,
                    "dtype": str(frame[column].dtype),
                    "is_key": int(column in keys),
                    "description": descriptions.get(column, column.replace("_", " ")),
                }
            )
    return pd.DataFrame(rows)


def validate_outputs(
    foundation_dir: Path,
    tables: dict[str, pd.DataFrame],
    payloads: dict[str, object],
    manifest: dict[str, object],
) -> dict[str, object]:
    checks: list[CheckResult] = []
    foundation_quality = json.loads((foundation_dir / "quality_report.json").read_text(encoding="utf-8"))
    checks.append(CheckResult("foundation_quality_passed", foundation_quality.get("status") == "passed", f"status={foundation_quality.get('status')}"))
    for table_name, keys in OUTPUT_TABLES.items():
        frame = tables[table_name]
        checks.append(check_unique(frame, keys, f"unique_key:{table_name}"))
        checks.append(check_nonnegative(frame, ["sales_amount", "use_count", "daily_rain_mm", "support_priority_score"], f"nonnegative:{table_name}"))
    checks.append(check_daily_grain_safety("daily_baseline_panel.csv", tables["daily_baseline_panel.csv"].columns))
    checks.append(check_daily_grain_safety("event_window_metrics_by_industry.csv", tables["event_window_metrics_by_industry.csv"].columns))
    checks.append(check_daily_grain_safety("shock_recovery_metrics_by_industry.csv", tables["shock_recovery_metrics_by_industry.csv"].columns))
    checks.append(check_required_columns(tables["support_priority_by_industry.csv"], ["reliability_flag", "interpretation"], "support_priority_required_flags"))
    checks.append(check_required_columns(tables["broad_area_inflow_context.csv"], ["customer_origin_scope"], "inflow_scope_column"))
    for name, payload in payloads.items():
        checks.append(check_json_field_safety(payload, f"json_field_safety:{name}"))
    output_rows = manifest.get("outputs", {})
    checks.append(CheckResult("manifest_output_rows", bool(output_rows), f"outputs={len(output_rows)}"))
    return summarize_checks(checks)


def run_build(foundation_dir: Path, out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    loaded = load_foundation(foundation_dir)
    daily = loaded["daily"]
    timeband = loaded["timeband"]
    inflow = loaded["inflow"]
    month_timeband = loaded["month_timeband"]
    foundation_manifest = loaded["foundation_manifest"]

    daily_panel = add_daily_baseline(daily)
    weather_daily = daily[["date", "merchant_region", "daily_rain_mm"]].drop_duplicates()
    events = detect_heavy_rain_events(weather_daily)
    event_windows = build_event_windows(daily_panel, events)
    shock_metrics = build_shock_metrics(daily_panel, event_windows)
    rain_bin_response = build_rain_bin_response(daily_panel)
    timeband_metrics = build_timeband_metrics(timeband)
    inflow_context = build_broad_area_context(inflow)
    priority = build_support_priority(shock_metrics, timeband_metrics, inflow_context)

    tables = {
        "daily_baseline_panel.csv": daily_panel,
        "rain_bin_response_by_region_industry.csv": rain_bin_response,
        "event_window_metrics_by_industry.csv": event_windows,
        "shock_recovery_metrics_by_industry.csv": shock_metrics,
        "timeband_vulnerability_metrics.csv": timeband_metrics,
        "broad_area_inflow_context.csv": inflow_context,
        "support_priority_by_industry.csv": priority,
    }
    for name, frame in tables.items():
        write_csv(frame, out_dir / name)

    dictionary = build_dictionary(tables)
    write_csv(dictionary, out_dir / "data_dictionary.csv")

    manifest = {
        "status": "built",
        "foundation_dir": str(foundation_dir),
        "foundation_inputs": {
            filename: {
                "bytes": (foundation_dir / filename).stat().st_size,
                "sha256": file_sha256(foundation_dir / filename),
            }
            for filename in REQUIRED_INPUTS.values()
            if filename.endswith(".csv") or filename.endswith(".json")
        },
        "thresholds": {"heavy_rain_mm": HEAVY_RAIN_MM, "timeband_heavy_rain_mm": TIMEBAND_HEAVY_RAIN_MM, "min_event_count": MIN_EVENT_COUNT},
        "score_weights": {
            "shock_sensitivity": 30,
            "initial_shock": 20,
            "net_damage": 15,
            "persistence": 15,
            "timeband": 10,
            "external_inflow": 10,
        },
        "outputs": {name: {"rows": len(frame), "columns": list(frame.columns)} for name, frame in tables.items()},
        "interpretation": "observed aggregate associations, not causal estimates",
        "grain_policy": {
            "daily_skt_join_allowed": False,
            "customer_origin_scope": "broad_area_not_district",
        },
    }
    quality_stub = {"status": "pending"}
    bundle = build_web_payloads(foundation_dir, daily_panel, shock_metrics, priority, timeband_metrics, inflow_context, month_timeband, quality_stub, foundation_manifest)
    payloads = {
        "regional_dashboard.json": bundle["regional_dashboard"],
        "vulnerability_matrix.json": bundle["vulnerability_matrix"],
        "support_priority.json": bundle["support_priority"],
        "policy_brief.json": bundle["policy_brief"],
        "flowshock_analysis_bundle.json": bundle,
    }
    quality = validate_outputs(foundation_dir, tables, payloads, manifest)
    bundle["quality"] = quality
    payloads["flowshock_analysis_bundle.json"] = bundle

    for name, payload in payloads.items():
        write_json(payload, out_dir / name)
    write_json(manifest, out_dir / "manifest.json")
    write_json(quality, out_dir / "quality_report.json")
    return quality


def load_output_tables(out_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [name for name in OUTPUT_TABLES if not (out_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing analysis outputs: {missing}")
    return {name: pd.read_csv(out_dir / name, encoding="utf-8-sig", low_memory=False) for name in OUTPUT_TABLES}


def run_check_only(foundation_dir: Path, out_dir: Path) -> dict[str, object]:
    tables = load_output_tables(out_dir)
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    payloads = {
        name: json.loads((out_dir / name).read_text(encoding="utf-8"))
        for name in [
            "regional_dashboard.json",
            "vulnerability_matrix.json",
            "support_priority.json",
            "policy_brief.json",
            "flowshock_analysis_bundle.json",
        ]
    }
    quality = validate_outputs(foundation_dir, tables, payloads, manifest)
    write_json(quality, out_dir / "quality_report.json")
    return quality


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FlowShock shock-recovery analysis outputs")
    parser.add_argument("--foundation-dir", type=Path, default=DEFAULT_FOUNDATION, help="FlowShock foundation output directory")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Analysis output directory")
    parser.add_argument("--check-only", action="store_true", help="Validate existing analysis outputs without rebuilding")
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def main() -> int:
    args = parse_args()
    foundation_dir = resolve_path(args.foundation_dir)
    out_dir = resolve_path(args.out)
    quality = run_check_only(foundation_dir, out_dir) if args.check_only else run_build(foundation_dir, out_dir)
    print(json.dumps({"status": quality["status"], "out_dir": str(out_dir), "quality_report": str(out_dir / "quality_report.json")}, ensure_ascii=False, indent=2))
    return 0 if quality["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
