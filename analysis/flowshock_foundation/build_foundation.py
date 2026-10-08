from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

try:
    from .quality_checks import (
        MONTHS,
        REGIONS,
        TIME_BANDS,
        CheckResult,
        check_domain,
        check_grain_safety,
        check_nonnegative,
        check_unique,
        hour_to_time_band,
        summarize_checks,
    )
except ImportError:
    from quality_checks import (
        MONTHS,
        REGIONS,
        TIME_BANDS,
        CheckResult,
        check_domain,
        check_grain_safety,
        check_nonnegative,
        check_unique,
        hour_to_time_band,
        summarize_checks,
    )


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path(__file__).resolve().parent / "out"

CARD_DIR = ROOT / "data" / "신한카드_데이터"
CARD1 = CARD_DIR / "신한카드_빅콘테스트2026_데이터1.txt"
CARD2 = CARD_DIR / "신한카드_빅콘테스트2026_데이터2.txt"
SKT_DIR = ROOT / "data" / "sk통신인구_데이터"
AWS400 = ROOT / "data" / "public_rainshock" / "raw" / "kma" / "aws_hourly" / "stn_400" / "OBS_AWS_TIM_20261005094738.csv"
ASOS_BASE = ROOT / "data" / "public_rainshock" / "raw" / "kma" / "asos_hourly"
HOLIDAY = ROOT / "data" / "public_rainshock" / "raw" / "kasi" / "holidays" / "2025" / "20261005T002238Z" / "kasi_holidays_2025.raw.json"

EXPECTED_RAW_ROWS = {
    "card1": 1_044_710,
    "card2": 1_806_800,
    "skt_time": 663_350,
}

TABLE_GRAINS = {
    "calendar_daily.csv": ("day", ["date"]),
    "weather_region_daily.csv": ("day", ["date", "merchant_region"]),
    "weather_region_timeband.csv": ("day", ["date", "time_band", "merchant_region"]),
    "card1_day_region_industry.csv": ("day", ["date", "merchant_region", "industry"]),
    "card1_timeband_region_industry.csv": ("day", ["date", "time_band", "merchant_region", "industry"]),
    "card2_month_region_customer_inflow.csv": ("month", ["month", "merchant_region", "customer_broad_area"]),
    "skt_month_timeband_profile.csv": ("month", ["month", "time_band"]),
    "skt_month_age_sex_profile.csv": ("month", ["month", "sex", "age_band"]),
    "skt_month_weekday_profile.csv": ("month", ["month", "weekday"]),
    "mart_daily_region_industry_weather.csv": ("day", ["date", "merchant_region", "industry"]),
    "mart_timeband_region_industry_weather.csv": ("day", ["date", "time_band", "merchant_region", "industry"]),
    "mart_month_timeband_profile.csv": ("month", ["month", "time_band"]),
}

MEASURE_COLUMNS = {
    "sales_amount",
    "use_count",
    "daily_rain_mm",
    "max_hourly_rain_mm",
    "rain_hours",
    "rain_timeband_mm",
    "max_hourly_rain_timeband_mm",
    "rain_hours_timeband",
    "flow_pop",
}

WEATHER_DATES = pd.date_range("2025-07-01", "2025-12-31").strftime("%Y-%m-%d").tolist()


def write_csv(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False, encoding="utf-8-sig")


def parse_asos_station(station_id: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    pattern = "*/asos_hourly_stn_*_2025*.raw.json"
    for path in sorted((ASOS_BASE / f"stn_{station_id}").glob(pattern)):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["response"]["header"].get("resultCode") != "00":
            continue
        items = payload["response"]["body"]["items"]["item"]
        rows.extend([items] if isinstance(items, dict) else items)
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError(f"No valid ASOS rows for station {station_id}")
    frame["tm"] = pd.to_datetime(frame["tm"])
    for column in ("rn", "ta", "hm", "ws"):
        frame[column] = pd.to_numeric(frame[column].replace("", np.nan), errors="coerce")
    return frame


def aggregate_weather(hourly: pd.DataFrame, merchant_region: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    frame = hourly.copy()
    frame["date"] = frame["tm"].dt.strftime("%Y-%m-%d")
    frame["hour"] = frame["tm"].dt.hour
    frame["rain_mm"] = frame["rn"].fillna(0)
    frame["rain_positive"] = (frame["rain_mm"] > 0).astype(int)
    frame["time_band"] = frame["hour"].map(hour_to_time_band)

    daily = frame.groupby("date", as_index=False).agg(
        daily_rain_mm=("rain_mm", "sum"),
        max_hourly_rain_mm=("rain_mm", "max"),
        rain_hours=("rain_positive", "sum"),
        temp_mean_c=("ta", "mean"),
        humidity_mean_pct=("hm", "mean"),
        wind_mean_ms=("ws", "mean"),
        weather_hourly_obs=("tm", "count"),
    )
    daily["merchant_region"] = merchant_region

    timeband = frame.groupby(["date", "time_band"], as_index=False).agg(
        rain_timeband_mm=("rain_mm", "sum"),
        max_hourly_rain_timeband_mm=("rain_mm", "max"),
        rain_hours_timeband=("rain_positive", "sum"),
        weather_timeband_obs=("tm", "count"),
    )
    full_index = pd.MultiIndex.from_product(
        [WEATHER_DATES, TIME_BANDS], names=["date", "time_band"]
    )
    timeband = timeband.set_index(["date", "time_band"]).reindex(full_index).reset_index()
    timeband["weather_timeband_missing"] = timeband["weather_timeband_obs"].isna().astype(int)
    timeband[[
        "rain_timeband_mm",
        "max_hourly_rain_timeband_mm",
        "rain_hours_timeband",
        "weather_timeband_obs",
    ]] = timeband[[
        "rain_timeband_mm",
        "max_hourly_rain_timeband_mm",
        "rain_hours_timeband",
        "weather_timeband_obs",
    ]].fillna(0)
    timeband["merchant_region"] = merchant_region
    return daily, timeband


def build_calendar() -> pd.DataFrame:
    payload = json.loads(HOLIDAY.read_text(encoding="utf-8"))
    items = payload["response"]["body"]["items"]["item"]
    items = [items] if isinstance(items, dict) else items
    holidays = pd.DataFrame(items)
    holidays["date"] = pd.to_datetime(holidays["locdate"].astype(str)).dt.strftime("%Y-%m-%d")
    holidays = holidays.loc[holidays["isHoliday"] == "Y", ["date", "dateName"]]
    holiday_names = holidays.groupby("date")["dateName"].agg("; ".join)

    calendar = pd.DataFrame({"date": pd.date_range("2025-07-01", "2025-12-31")})
    calendar["month"] = calendar["date"].dt.strftime("%Y%m").astype(int)
    calendar["day_of_week"] = calendar["date"].dt.dayofweek
    calendar["is_weekend"] = calendar["day_of_week"].isin([5, 6]).astype(int)
    calendar["date"] = calendar["date"].dt.strftime("%Y-%m-%d")
    calendar["holiday_name"] = calendar["date"].map(holiday_names).fillna("")
    calendar["is_holiday"] = (calendar["holiday_name"] != "").astype(int)
    return calendar


def build_weather() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    aws = pd.read_csv(AWS400, encoding="cp949")
    aws = aws.rename(
        columns={"일시": "tm", "강수량(mm)": "rn", "기온(°C)": "ta", "습도(%)": "hm", "풍속(m/s)": "ws"}
    )
    aws["tm"] = pd.to_datetime(aws["tm"])
    for column in ("rn", "ta", "hm", "ws"):
        aws[column] = pd.to_numeric(aws[column], errors="coerce")
    asos101 = parse_asos_station("101")

    gangnam_daily, gangnam_timeband = aggregate_weather(aws, "서울 강남구")
    chuncheon_daily, chuncheon_timeband = aggregate_weather(asos101, "강원 춘천시")
    daily = pd.concat([gangnam_daily, chuncheon_daily], ignore_index=True)
    timeband = pd.concat([gangnam_timeband, chuncheon_timeband], ignore_index=True)
    return daily, timeband, {"aws400": len(aws), "asos101": len(asos101)}


def consolidate(parts: list[pd.DataFrame], keys: list[str]) -> pd.DataFrame:
    combined = pd.concat(parts, ignore_index=True)
    measures = [column for column in combined.columns if column not in keys]
    return combined.groupby(keys, as_index=False, observed=False)[measures].sum()


def build_card1() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    columns = ["TA_YMD", "TIME_GB", "MCT_SGG_CD", "MCT_RY_CD", "TS_AT", "USE_CNT"]
    daily_parts: list[pd.DataFrame] = []
    timeband_parts: list[pd.DataFrame] = []
    raw_rows = 0
    raw_sales = 0.0
    raw_use_count = 0.0
    industries: set[str] = set()

    for chunk in pd.read_csv(CARD1, sep="\t", encoding="cp949", usecols=columns, chunksize=250_000):
        raw_rows += len(chunk)
        chunk["TS_AT"] = pd.to_numeric(chunk["TS_AT"], errors="coerce")
        chunk["USE_CNT"] = pd.to_numeric(chunk["USE_CNT"], errors="coerce")
        raw_sales += float(chunk["TS_AT"].sum())
        raw_use_count += float(chunk["USE_CNT"].sum())
        industries.update(chunk["MCT_RY_CD"].dropna().astype(str).unique())
        chunk["date"] = pd.to_datetime(chunk["TA_YMD"].astype(str)).dt.strftime("%Y-%m-%d")
        chunk = chunk.rename(
            columns={
                "TIME_GB": "time_band",
                "MCT_SGG_CD": "merchant_region",
                "MCT_RY_CD": "industry",
                "TS_AT": "sales_amount",
                "USE_CNT": "use_count",
            }
        )
        daily_parts.append(
            chunk.groupby(["date", "merchant_region", "industry"], as_index=False).agg(
                sales_amount=("sales_amount", "sum"), use_count=("use_count", "sum")
            )
        )
        timeband_parts.append(
            chunk.groupby(["date", "time_band", "merchant_region", "industry"], as_index=False).agg(
                sales_amount=("sales_amount", "sum"), use_count=("use_count", "sum")
            )
        )

    daily = consolidate(daily_parts, ["date", "merchant_region", "industry"])
    timeband = consolidate(timeband_parts, ["date", "time_band", "merchant_region", "industry"])
    stats = {
        "raw_rows": raw_rows,
        "raw_sales_amount": raw_sales,
        "raw_use_count": raw_use_count,
        "industry_count": len(industries),
    }
    return daily, timeband, stats


def build_card2() -> tuple[pd.DataFrame, dict[str, object]]:
    columns = ["TA_YMD", "MCT_SGG_CD", "CLN_SGG_CD", "TS_AT", "USE_CNT"]
    parts: list[pd.DataFrame] = []
    raw_rows = 0
    raw_sales = 0.0
    raw_use_count = 0.0

    for chunk in pd.read_csv(CARD2, sep="\t", encoding="cp949", usecols=columns, chunksize=250_000):
        raw_rows += len(chunk)
        chunk["TS_AT"] = pd.to_numeric(chunk["TS_AT"], errors="coerce")
        chunk["USE_CNT"] = pd.to_numeric(chunk["USE_CNT"], errors="coerce")
        raw_sales += float(chunk["TS_AT"].sum())
        raw_use_count += float(chunk["USE_CNT"].sum())
        chunk["month"] = (chunk["TA_YMD"] // 100).astype(int)
        chunk = chunk.rename(
            columns={
                "MCT_SGG_CD": "merchant_region",
                "CLN_SGG_CD": "customer_broad_area",
                "TS_AT": "sales_amount",
                "USE_CNT": "use_count",
            }
        )
        parts.append(
            chunk.groupby(["month", "merchant_region", "customer_broad_area"], as_index=False).agg(
                sales_amount=("sales_amount", "sum"), use_count=("use_count", "sum")
            )
        )
    monthly = consolidate(parts, ["month", "merchant_region", "customer_broad_area"])
    totals = monthly.groupby(["month", "merchant_region"])["sales_amount"].transform("sum")
    monthly["sales_share_within_region_month"] = np.where(totals > 0, monthly["sales_amount"] / totals, np.nan)
    return monthly, {"raw_rows": raw_rows, "raw_sales_amount": raw_sales, "raw_use_count": raw_use_count}


def read_skt_file(path: Path) -> tuple[pd.DataFrame, int]:
    frame = pd.read_csv(path, sep="|", encoding="utf-8-sig", dtype={"BLOCK_CD": str}, low_memory=False)
    duplicate_count = int(frame.duplicated().sum())
    return frame.drop_duplicates().copy(), duplicate_count


def build_skt_profiles() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    time_rows: list[dict[str, object]] = []
    age_rows: list[dict[str, object]] = []
    weekday_rows: list[dict[str, object]] = []
    stats: dict[str, object] = {
        "time_raw_rows": 0,
        "age_raw_rows": 0,
        "weekday_raw_rows": 0,
        "exact_duplicates": {"time": {}, "age": {}, "weekday": {}},
        "time_blocks": set(),
    }

    for path in sorted(SKT_DIR.glob("flow_time_pop_*.csv")):
        raw_count = sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1
        frame, duplicates = read_skt_file(path)
        month = int(frame["STD_YM"].iloc[0])
        stats["time_raw_rows"] += raw_count
        stats["exact_duplicates"]["time"][str(month)] = duplicates
        stats["time_blocks"].update(frame["BLOCK_CD"].dropna().astype(str).unique())
        for time_band in TIME_BANDS:
            start = int(time_band[:2])
            columns = [f"TMST_{hour:02d}" for hour in range(start, start + 6)]
            flow = frame[columns].apply(pd.to_numeric, errors="coerce").sum().sum()
            time_rows.append({"month": month, "time_band": time_band, "flow_pop": float(flow)})

    for path in sorted(SKT_DIR.glob("flow_age_pop_*.csv")):
        raw_count = sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1
        frame, duplicates = read_skt_file(path)
        month = int(frame["STD_YM"].iloc[0])
        stats["age_raw_rows"] += raw_count
        stats["exact_duplicates"]["age"][str(month)] = duplicates
        profile_columns = [column for column in frame.columns if "FLOW_POP_CNT" in column]
        for column in profile_columns:
            sex = "female" if column.startswith("WMAN_") else "male"
            age_band = column.rsplit("_", 1)[-1].replace("G", "")
            value = pd.to_numeric(frame[column], errors="coerce").sum()
            age_rows.append({"month": month, "sex": sex, "age_band": age_band, "flow_pop": float(value)})

    weekday_map = {"MON": "mon", "TUS": "tue", "WED": "wed", "THU": "thu", "FRI": "fri", "SAT": "sat", "SUN": "sun"}
    for path in sorted(SKT_DIR.glob("flow_wkdy_pop_*.csv")):
        raw_count = sum(1 for _ in path.open("r", encoding="utf-8-sig")) - 1
        frame, duplicates = read_skt_file(path)
        month = int(frame["STD_YM"].iloc[0])
        stats["weekday_raw_rows"] += raw_count
        stats["exact_duplicates"]["weekday"][str(month)] = duplicates
        for suffix, weekday in weekday_map.items():
            column = f"FLOW_POP_CNT_{suffix}"
            value = pd.to_numeric(frame[column], errors="coerce").sum()
            weekday_rows.append({"month": month, "weekday": weekday, "flow_pop": float(value)})

    stats["time_blocks"] = len(stats["time_blocks"])
    return pd.DataFrame(time_rows), pd.DataFrame(age_rows), pd.DataFrame(weekday_rows), stats


def add_month_and_shares(card_timeband: pd.DataFrame, skt_timeband: pd.DataFrame) -> pd.DataFrame:
    card = card_timeband.copy()
    card["month"] = card["date"].str[:7].str.replace("-", "").astype(int)
    card = card.groupby(["month", "time_band"], as_index=False)["sales_amount"].sum()
    card["card_sales_share"] = card["sales_amount"] / card.groupby("month")["sales_amount"].transform("sum")
    card = card.drop(columns="sales_amount")

    skt = skt_timeband.copy()
    skt["skt_flow_share"] = skt["flow_pop"] / skt.groupby("month")["flow_pop"].transform("sum")
    skt = skt.drop(columns="flow_pop")
    comparison = card.merge(skt, on=["month", "time_band"], how="inner", validate="one_to_one")
    comparison["aggregate_flow_to_sales_ratio"] = np.where(
        comparison["skt_flow_share"] > 0,
        comparison["card_sales_share"] / comparison["skt_flow_share"],
        np.nan,
    )
    comparison["interpretation_scope"] = "aggregate_month_timeband_profile_not_individual_conversion"
    return comparison


def build_dictionary(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    descriptions = {
        "date": "Calendar date in YYYY-MM-DD format",
        "month": "Calendar month in YYYYMM format",
        "merchant_region": "Merchant analysis region",
        "industry": "Merchant industry category",
        "time_band": "Canonical six-hour time band",
        "customer_broad_area": "Customer broad-area/province category; not district residence",
        "sales_amount": "Aggregated card sales amount",
        "use_count": "Aggregated card use count",
        "flow_pop": "Aggregated SKT floating-population measure",
    }
    rows: list[dict[str, object]] = []
    for table_name, frame in tables.items():
        temporal_grain, keys = TABLE_GRAINS[table_name]
        for column in frame.columns:
            rows.append(
                {
                    "table": table_name,
                    "column": column,
                    "dtype": str(frame[column].dtype),
                    "temporal_grain": temporal_grain,
                    "is_key": int(column in keys),
                    "description": descriptions.get(column, column.replace("_", " ")),
                }
            )
    return pd.DataFrame(rows)


def validate_tables(
    tables: dict[str, pd.DataFrame], manifest: dict[str, object], dictionary: pd.DataFrame
) -> dict[str, object]:
    checks: list[CheckResult] = []
    raw = manifest["raw_sources"]
    for name, expected in EXPECTED_RAW_ROWS.items():
        key = "raw_rows" if name.startswith("card") else "time_raw_rows"
        actual = int(raw[name][key])
        checks.append(CheckResult(f"raw_row_count:{name}", actual == expected, f"actual={actual}, expected={expected}"))

    for table_name, frame in tables.items():
        temporal_grain, keys = TABLE_GRAINS[table_name]
        checks.append(check_unique(frame, keys, f"unique_key:{table_name}"))
        checks.append(check_nonnegative(frame, MEASURE_COLUMNS, f"nonnegative:{table_name}"))
        checks.append(check_grain_safety(table_name, temporal_grain, frame.columns))

    checks.extend(
        [
            check_domain(tables["card1_day_region_industry.csv"]["merchant_region"], REGIONS, "region_domain:card1_daily"),
            check_domain(tables["card1_timeband_region_industry.csv"]["time_band"], TIME_BANDS, "timeband_domain:card1"),
            check_domain(tables["skt_month_timeband_profile.csv"]["month"], MONTHS, "month_domain:skt"),
            check_domain(tables["skt_month_timeband_profile.csv"]["time_band"], TIME_BANDS, "timeband_domain:skt"),
        ]
    )

    card1_stats = raw["card1"]
    daily = tables["card1_day_region_industry.csv"]
    timeband = tables["card1_timeband_region_industry.csv"]
    card2_stats = raw["card2"]
    inflow = tables["card2_month_region_customer_inflow.csv"]
    reconciliations = [
        ("card1_daily_sales", float(daily["sales_amount"].sum()), float(card1_stats["raw_sales_amount"])),
        ("card1_timeband_sales", float(timeband["sales_amount"].sum()), float(card1_stats["raw_sales_amount"])),
        ("card1_daily_use_count", float(daily["use_count"].sum()), float(card1_stats["raw_use_count"])),
        ("card2_monthly_sales", float(inflow["sales_amount"].sum()), float(card2_stats["raw_sales_amount"])),
        ("card2_monthly_use_count", float(inflow["use_count"].sum()), float(card2_stats["raw_use_count"])),
    ]
    for name, actual, expected in reconciliations:
        checks.append(CheckResult(f"reconciliation:{name}", np.isclose(actual, expected), f"actual={actual}, expected={expected}"))

    daily_weather = tables["weather_region_daily.csv"]
    coverage = daily_weather.groupby("merchant_region")["date"].nunique().to_dict()
    checks.append(CheckResult("weather_daily_coverage", coverage == {region: 184 for region in REGIONS}, f"coverage={coverage}"))
    timeband_weather = tables["weather_region_timeband.csv"]
    expected_timeband_rows = 184 * len(REGIONS) * len(TIME_BANDS)
    checks.append(
        CheckResult(
            "weather_timeband_coverage",
            len(timeband_weather) == expected_timeband_rows,
            f"rows={len(timeband_weather)}, expected={expected_timeband_rows}",
        )
    )

    checks.append(
        CheckResult(
            "daily_join_cardinality",
            len(tables["mart_daily_region_industry_weather.csv"]) == len(daily),
            f"mart={len(tables['mart_daily_region_industry_weather.csv'])}, card={len(daily)}",
        )
    )
    checks.append(
        CheckResult(
            "timeband_join_cardinality",
            len(tables["mart_timeband_region_industry_weather.csv"]) == len(timeband),
            f"mart={len(tables['mart_timeband_region_industry_weather.csv'])}, card={len(timeband)}",
        )
    )
    timeband_weather_columns = [
        "rain_timeband_mm",
        "max_hourly_rain_timeband_mm",
        "rain_hours_timeband",
        "weather_timeband_obs",
        "weather_timeband_missing",
    ]
    mart_timeband = tables["mart_timeband_region_industry_weather.csv"]
    missing_join_values = int(mart_timeband[timeband_weather_columns].isna().sum().sum())
    checks.append(
        CheckResult(
            "mart_timeband_weather_not_null",
            missing_join_values == 0,
            f"null joined weather values={missing_join_values}",
        )
    )

    dictionary_pairs = set(zip(dictionary["table"], dictionary["column"]))
    expected_pairs = {(table_name, column) for table_name, frame in tables.items() for column in frame.columns}
    checks.append(CheckResult("dictionary_coverage", dictionary_pairs == expected_pairs, f"covered={len(dictionary_pairs)}, expected={len(expected_pairs)}"))
    return summarize_checks(checks)


def load_existing_tables(out_dir: Path) -> dict[str, pd.DataFrame]:
    missing = [name for name in TABLE_GRAINS if not (out_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing foundation outputs: {missing}")
    return {name: pd.read_csv(out_dir / name, encoding="utf-8-sig", low_memory=False) for name in TABLE_GRAINS}


def run_build(out_dir: Path) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    required = [CARD1, CARD2, AWS400, HOLIDAY]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required raw files: {missing}")

    calendar = build_calendar()
    weather_daily, weather_timeband, weather_stats = build_weather()
    card1_daily, card1_timeband, card1_stats = build_card1()
    card2_inflow, card2_stats = build_card2()
    skt_timeband, skt_age_sex, skt_weekday, skt_stats = build_skt_profiles()

    daily_mart = card1_daily.merge(
        weather_daily,
        on=["date", "merchant_region"],
        how="left",
        validate="many_to_one",
    ).merge(calendar, on="date", how="left", validate="many_to_one")
    timeband_mart = card1_timeband.merge(
        weather_timeband,
        on=["date", "time_band", "merchant_region"],
        how="left",
        validate="many_to_one",
    ).merge(calendar, on="date", how="left", validate="many_to_one")
    month_timeband = add_month_and_shares(card1_timeband, skt_timeband)

    tables = {
        "calendar_daily.csv": calendar,
        "weather_region_daily.csv": weather_daily,
        "weather_region_timeband.csv": weather_timeband,
        "card1_day_region_industry.csv": card1_daily,
        "card1_timeband_region_industry.csv": card1_timeband,
        "card2_month_region_customer_inflow.csv": card2_inflow,
        "skt_month_timeband_profile.csv": skt_timeband,
        "skt_month_age_sex_profile.csv": skt_age_sex,
        "skt_month_weekday_profile.csv": skt_weekday,
        "mart_daily_region_industry_weather.csv": daily_mart,
        "mart_timeband_region_industry_weather.csv": timeband_mart,
        "mart_month_timeband_profile.csv": month_timeband,
    }
    for name, frame in tables.items():
        write_csv(frame, out_dir / name)

    manifest = {
        "status": "built",
        "period": {"start": "2025-07-01", "end": "2025-12-31"},
        "raw_sources": {
            "card1": card1_stats,
            "card2": card2_stats,
            "skt_time": skt_stats,
            "weather": weather_stats,
        },
        "outputs": {name: {"rows": len(frame), "columns": list(frame.columns)} for name, frame in tables.items()},
        "grain_policy": {
            "daily_skt_join_allowed": False,
            "monthly_timeband_profile_comparison_allowed": True,
            "customer_origin_scope": "broad_area_not_district",
        },
    }
    dictionary = build_dictionary(tables)
    write_csv(dictionary, out_dir / "data_dictionary.csv")
    report = validate_tables(tables, manifest, dictionary)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_check_only(out_dir: Path) -> dict[str, object]:
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    tables = load_existing_tables(out_dir)
    dictionary = pd.read_csv(out_dir / "data_dictionary.csv", encoding="utf-8-sig")
    report = validate_tables(tables, manifest, dictionary)
    (out_dir / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build FlowShock canonical aggregate data foundation")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory")
    parser.add_argument("--check-only", action="store_true", help="Validate existing outputs without rebuilding")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out if args.out.is_absolute() else ROOT / args.out
    report = run_check_only(out_dir) if args.check_only else run_build(out_dir)
    result = {"status": report["status"], "quality_report": str(out_dir / "quality_report.json"), "out_dir": str(out_dir)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
