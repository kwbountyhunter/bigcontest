from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd


FORBIDDEN_RAW_MARKERS = ("data\\", "data/", "신한카드_데이터", "sk통신인구_데이터")
FORBIDDEN_DAILY_FEATURES = (
    "sales_amount",
    "use_count",
    "sales_idx",
    "use_count_idx",
    "sales_dev_pct",
    "use_count_dev_pct",
    "model_sales_dev_pct",
    "model_use_count_dev_pct",
    "estimated_loss_amount",
)


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


def check_no_forbidden_features(features: Iterable[str], name: str) -> CheckResult:
    feature_list = list(features)
    forbidden = [feature for feature in feature_list if feature in FORBIDDEN_DAILY_FEATURES]
    return CheckResult(name, not forbidden, f"forbidden_features={forbidden}")


def check_chronological_split(df: pd.DataFrame, date_column: str, split_column: str, name: str) -> CheckResult:
    frame = df.copy()
    frame[date_column] = pd.to_datetime(frame[date_column])
    bounds = frame.groupby(split_column)[date_column].agg(["min", "max"]).to_dict("index")
    required = {"train", "validation", "test"}
    if not required.issubset(bounds):
        return CheckResult(name, False, f"missing split={sorted(required - set(bounds))}")
    passed = bounds["train"]["max"] < bounds["validation"]["min"] <= bounds["validation"]["max"] < bounds["test"]["min"]
    return CheckResult(name, passed, f"bounds={bounds}")


def check_no_raw_paths(paths: Iterable[str], name: str) -> CheckResult:
    bad = [path for path in paths if any(marker in path for marker in FORBIDDEN_RAW_MARKERS)]
    return CheckResult(name, not bad, f"raw_like_paths={bad}")


def summarize_checks(checks: Sequence[CheckResult]) -> dict[str, object]:
    failed = [check.as_dict() for check in checks if not check.passed]
    return {
        "status": "passed" if not failed else "failed",
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "checks": [check.as_dict() for check in checks],
    }
