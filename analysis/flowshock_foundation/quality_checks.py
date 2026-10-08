from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


TIME_BANDS = ("00_05", "06_11", "12_17", "18_23")
REGIONS = ("강원 춘천시", "서울 강남구")
MONTHS = (202507, 202508, 202509, 202510, 202511, 202512)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": bool(self.passed), "detail": self.detail}


def hour_to_time_band(hour: int) -> str:
    if not 0 <= hour <= 23:
        raise ValueError(f"hour must be between 0 and 23: {hour}")
    return TIME_BANDS[hour // 6]


def check_unique(df: pd.DataFrame, keys: Sequence[str], name: str) -> CheckResult:
    missing = [column for column in keys if column not in df.columns]
    if missing:
        return CheckResult(name, False, f"missing key columns: {missing}")
    duplicate_count = int(df.duplicated(list(keys)).sum())
    return CheckResult(name, duplicate_count == 0, f"duplicate keys: {duplicate_count}")


def check_nonnegative(
    df: pd.DataFrame, columns: Iterable[str], name: str
) -> CheckResult:
    checked = [column for column in columns if column in df.columns]
    negative_count = sum(int((pd.to_numeric(df[column], errors="coerce") < 0).sum()) for column in checked)
    return CheckResult(name, negative_count == 0, f"negative values: {negative_count}")


def check_domain(
    series: pd.Series, expected: Iterable[object], name: str, exact: bool = True
) -> CheckResult:
    actual = set(series.dropna().unique().tolist())
    expected_set = set(expected)
    passed = actual == expected_set if exact else actual.issubset(expected_set)
    return CheckResult(
        name,
        passed,
        f"actual={sorted(map(str, actual))}, expected={sorted(map(str, expected_set))}",
    )


def check_grain_safety(
    table_name: str, temporal_grain: str, columns: Iterable[str]
) -> CheckResult:
    skt_markers = ("skt_", "flow_pop", "floating_population")
    offending = [
        column
        for column in columns
        if any(marker in column.lower() for marker in skt_markers)
    ]
    passed = not (temporal_grain == "day" and offending)
    detail = "safe" if passed else f"daily table contains monthly SKT fields: {offending}"
    return CheckResult(f"grain_safety:{table_name}", passed, detail)


def summarize_checks(checks: Sequence[CheckResult]) -> dict[str, object]:
    failed = [check.as_dict() for check in checks if not check.passed]
    return {
        "status": "passed" if not failed else "failed",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": [check.as_dict() for check in checks],
    }
