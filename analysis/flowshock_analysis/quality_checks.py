from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


FORBIDDEN_DAILY_MARKERS = ("skt_", "flow_pop", "floating_population")
FORBIDDEN_JSON_FIELDS = ("block", "coord", "x_coord", "y_coord", "store", "person", "customer_id")


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict[str, object]:
        return {"name": self.name, "passed": bool(self.passed), "detail": self.detail}


def check_required_columns(df: pd.DataFrame, columns: Sequence[str], name: str) -> CheckResult:
    missing = [column for column in columns if column not in df.columns]
    return CheckResult(name, not missing, f"missing={missing}")


def check_unique(df: pd.DataFrame, keys: Sequence[str], name: str) -> CheckResult:
    missing = [key for key in keys if key not in df.columns]
    if missing:
        return CheckResult(name, False, f"missing key columns={missing}")
    duplicates = int(df.duplicated(list(keys)).sum())
    return CheckResult(name, duplicates == 0, f"duplicate keys={duplicates}")


def check_nonnegative(df: pd.DataFrame, columns: Iterable[str], name: str) -> CheckResult:
    checked = [column for column in columns if column in df.columns]
    negative_count = sum(int((pd.to_numeric(df[column], errors="coerce") < 0).sum()) for column in checked)
    return CheckResult(name, negative_count == 0, f"negative values={negative_count}")


def check_daily_grain_safety(table_name: str, columns: Iterable[str]) -> CheckResult:
    offending = [
        column
        for column in columns
        if any(marker in column.lower() for marker in FORBIDDEN_DAILY_MARKERS)
    ]
    return CheckResult(
        f"daily_grain_safety:{table_name}",
        not offending,
        "safe" if not offending else f"forbidden daily fields={offending}",
    )


def check_json_field_safety(payload: object, name: str) -> CheckResult:
    bad_fields: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if any(marker in str(key).lower() for marker in FORBIDDEN_JSON_FIELDS):
                    bad_fields.add(str(key))
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return CheckResult(name, not bad_fields, f"forbidden_fields={sorted(bad_fields)}")


def summarize_checks(checks: Sequence[CheckResult]) -> dict[str, object]:
    failed = [check.as_dict() for check in checks if not check.passed]
    return {
        "status": "passed" if not failed else "failed",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": [check.as_dict() for check in checks],
    }
