#!/usr/bin/env python3
"""v0.1 YAML 계약(contract)과 로컬 CSV 파일을 검증한 뒤 codebook(코드북)을 생성한다.

이 스크립트는 데이터 파이프라인의 일부로, 다음 절차를 수행한다.

1. ``data/contract`` 디렉터리 아래의 모든 YAML 계약 파일을 읽는다.
2. 각 계약 파일의 스키마 정의를 검증한다.
3. 계약이 가리키는 실제 CSV 데이터 파일을 읽어 타입/제약 조건을 점검한다.
4. 검증 결과와 관측 통계(행 수, null 개수, 날짜 범위 등)를 하나의
   ``codebook.json`` 파일로 병합해 출력한다.

출력 파일은 JSON 직렬화가 보장되며, 검증에 실패한 항목은 stderr로 에러를
보고하고 종료 코드 1을 반환한다.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    raise SystemExit("PyYAML이 필요합니다: python3 -m pip install -r data/requirements.txt")

# 프로젝트 루트: 이 파일(data/scripts/codebook_json_file_maker.py) 기준 두 단계 위 디렉터리.
ROOT = Path(__file__).resolve().parents[2]
# 컬럼/데이터셋 이름 규칙: 소문자로 시작하는 snake_case.
NAME = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
# 계약 파일에서 허용하는 데이터 타입 집합.
TYPES = {"string", "integer", "float", "boolean", "date", "datetime"}


class ContractLoader(yaml.SafeLoader):
    """YAML 키 중복을 조용히 무시하지 않고 오류로 거부하는 로더.

    PyYAML의 기본 로더는 같은 키가 반복되면 마지막 값만 남기고 앞의 값을
    조용히 버린다. 이 클래스는 :func:`unique_mapping` 생성자를 연결해
    중복 키가 있으면 명시적으로 예외를 발생시키도록 한다.
    """


def unique_mapping(loader, node, deep=False):
    """YAML 매핑 노드를 중복 키 검사를 거쳐 dict로 변환한다.

    Args:
        loader: YAML 노드를 실제 객체로 만드는 로더 인스턴스.
        node: 현재 처리 중인 YAML 매핑 노드.
        deep: 하위 노드까지 재귀적으로 변환할지 여부.

    Returns:
        dict: 중복 없이 변환된 키-값 매핑.

    Raises:
        ValueError: 키가 문자열이 아니거나, 키가 중복된 경우.
    """
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str):
            raise ValueError("YAML mapping keys must be strings")
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


# 기본 매핑 태그에 사용자 정의 생성자를 등록해 중복 키 검사 로직을 전역으로 적용한다.
ContractLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def parse_value(value, dtype):
    """null이 아닌 CSV 값을 지정된 타입으로 파싱한다.

    문자열 식별자(예: "00123")가 의도치 않게 숫자로 강제 변환되는 것을
    막기 위해 타입별로 엄격한 정규 표현식 검사를 거친다.

    Args:
        value (str): CSV에서 읽어온 원시 문자열 값.
        dtype (str): 변환할 대상 타입. ``TYPES``에 속하는 값이어야 한다.

    Returns:
        변환된 값. 타입에 따라 ``int``, ``float``, ``bool``, ``date``,
        ``datetime`` 또는 문자열 그대로 반환된다.

    Raises:
        ValueError: 값이 해당 타입의 형식에 맞지 않는 경우.
    """
    if dtype == "string":
        return value
    if dtype == "integer":
        # 부호(+/-)를 허용하는 정수만 허용한다. "1e3", "3.0" 등은 거부.
        if not re.fullmatch(r"[+-]?[0-9]+", value):
            raise ValueError("Expected integer")
        return int(value)
    if dtype == "float":
        result = float(value)
        # NaN이나 Infinity는 JSON 직렬화가 불가능하므로 거부한다.
        if not math.isfinite(result):
            raise ValueError("Expected finite number")
        return result
    if dtype == "boolean":
        # "true"/"false" 또는 "0"/"1" (대소문자 무시)만 불리언으로 인정한다.
        if value.lower() not in {"true", "false", "0", "1"}:
            raise ValueError("Expected boolean")
        return value.lower() in {"true", "1"}
    if dtype == "date":
        # ISO 8601 날짜(YYYY-MM-DD) 형식만 허용한다.
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError("Expected YYYY-MM-DD")
        return date.fromisoformat(value)
    # 남은 타입은 datetime. ISO 8601 + 타임존 형식만 허용한다.
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})", value
    ):
        raise ValueError("Expected ISO 8601 datetime with timezone")
    # "Z"는 파서 호환을 위해 +00:00으로 치환하고, 값이 선언한 오프셋(예: KST +09:00)을 보존한다.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def contract_value(value, dtype):
    """계약 파일(제약 조건)에 명시된 값을 주어진 타입으로 검증·변환한다.

    계약의 ``allowed_values``, ``constraints`` 등에 쓰인 스칼라 값이
    올바른 타입인지 확인하고 파싱한다.

    Args:
        value: 계약 파일에서 읽은 원시 값(YAML 스칼라).
        dtype (str): 변환할 대상 타입.

    Returns:
        파싱된 제약 조건 값.

    Raises:
        ValueError: 값이 null이거나 리스트/딕셔너리이거나, 타입 형식에
            맞지 않는 경우.
    """
    # 제약 조건 값은 반드시 null이 아닌 스칼라여야 한다.
    if value is None or isinstance(value, (list, dict)):
        raise ValueError("Constraint values must be non-null scalars")
    # string 타입 제약 값은 따옴표로 감싼 문자열이어야 한다(YAML에서 숫자/불리언과 구분).
    if dtype == "string" and not isinstance(value, str):
        raise ValueError("String constraint values must be quoted strings")
    return parse_value(str(value), dtype)


def validate_contract(contract):
    """계약(contract) 딕셔너리의 구조와 스키마 정의를 검증한다.

    필수 메타데이터 존재 여부, ``schema_version``/``format`` 값, 컬럼 이름
    규칙, 데이터 타입, primary key 정의, 그리고 각 컬럼의 제약 조건을
    순서대로 점검한다.

    Args:
        contract (dict): YAML 계약 파일을 파싱한 딕셔너리.

    Returns:
        list[str]: 발견된 검증 오류 메시지 목록. 오류가 없으면 빈 리스트.
    """
    if not isinstance(contract, dict):
        return ["Contract must be a mapping"]
    errors = []
    # 1) 필수 메타데이터: 모두 비어 있지 않은 문자열이어야 한다.
    for key in ("schema_version", "dataset_id", "name", "description", "source", "path", "format", "grain"):
        if not isinstance(contract.get(key), str) or not contract[key].strip():
            errors.append(f"{key}: non-empty string required")
    # 2) 스키마 버전과 포맷 고정값 확인.
    if contract.get("schema_version") != "0.1":
        errors.append('schema_version must be "0.1"')
    if contract.get("format") != "csv":
        errors.append("Only csv format is supported")
    # 3) dataset_id는 snake_case 규칙을 따라야 한다.
    if not NAME.fullmatch(str(contract.get("dataset_id", ""))):
        errors.append("dataset_id must be snake_case")
    columns = contract.get("columns")
    if not isinstance(columns, dict) or not columns:
        return errors + ["columns must be a non-empty mapping"]
    # 4) primary_key: 컬럼 이름 리스트여야 하며 중복이 없어야 한다.
    keys = contract.get("primary_key")
    if not isinstance(keys, list) or any(not isinstance(k, str) for k in keys):
        errors.append("primary_key must be a list of column names")
        keys = []
    elif len(keys) != len(set(keys)):
        errors.append("primary_key contains duplicate column names")
    # primary_key가 비어 있다면 그 이유를 notes에 반드시 설명해야 한다.
    if not keys and (not isinstance(contract.get("notes"), str) or not contract["notes"].strip()):
        errors.append("notes must explain why primary_key is empty")
    # primary_key로 지정한 컬럼은 columns에 정의되어 있어야 한다.
    for key in keys:
        if key not in columns:
            errors.append(f"primary_key column is undefined: {key}")
    # 5) 각 컬럼 정의 검증.
    for name, spec in columns.items():
        if not NAME.fullmatch(name):
            errors.append(f"{name}: column name must be snake_case")
        if not isinstance(spec, dict):
            errors.append(f"{name}: column definition must be a mapping")
            continue
        dtype = spec.get("dtype")
        if not isinstance(dtype, str) or dtype not in TYPES:
            errors.append(f"{name}: unsupported dtype")
            continue
        # nullable은 정확히 bool 타입이어야 한다(YAML의 yes/no 등은 거부).
        if type(spec.get("nullable")) is not bool:
            errors.append(f"{name}: nullable must be a boolean")
        # primary key 컬럼은 null을 허용할 수 없다.
        if name in keys and spec.get("nullable") is not False:
            errors.append(f"{name}: primary key must have nullable: false")
        try:
            # allowed_values의 각 값이 해당 타입으로 파싱 가능한지 확인.
            if "allowed_values" in spec:
                if not isinstance(spec["allowed_values"], list):
                    raise ValueError("allowed_values must be a list")
                for value in spec["allowed_values"]:
                    contract_value(value, dtype)
            # constraints는 min/max 외의 키를 허용하지 않는다.
            constraints = spec.get("constraints", {})
            if not isinstance(constraints, dict) or set(constraints) - {"min", "max"}:
                raise ValueError("constraints supports only min and max")
            bounds = {k: contract_value(v, dtype) for k, v in constraints.items()}
            # min이 max보다 크면 모순된 제약 조건이다.
            if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
                raise ValueError("min must not exceed max")
        except (ValueError, TypeError, OverflowError) as exc:
            errors.append(f"{name}: {exc}")
    return errors


def inspect_csv(path, contract):
    """실제 CSV 데이터 파일을 읽어 계약 대비 데이터 품질을 검사한다.

    파일 크기와 SHA-256 해시를 계산하고, 헤더(컬럼 구성) 일치 여부, 각 컬럼의
    null/타입/허용값/범위 위반, 그리고 primary key 중복 여부를 점검한다.
    또한 날짜·시각 컬럼의 최소/최대 범위를 관측 통계로 기록한다.

    Args:
        path (Path): 검사할 CSV 파일 경로.
        contract (dict): 검증을 통과한 계약 딕셔너리.

    Returns:
        tuple[dict, list[str]]: ``(관측 통계 딕셔너리, 오류 메시지 목록)``.
        관측 통계에는 ``file_size_bytes``, ``sha256``, ``row_count``,
        ``null_counts``, ``date_ranges`` 등이 포함된다.
    """
    columns = contract["columns"]
    observed = {"file_size_bytes": path.stat().st_size}
    # 파일 전체를 스트리밍 방식으로 읽어 SHA-256 해시를 계산한다.
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    observed["sha256"] = digest.hexdigest()
    errors = []
    # 컬럼별 위반 횟수를 집계하기 위한 카운터.
    counts = {name: Counter() for name in columns}
    # 날짜/시각 컬럼의 관측 범위(최소, 최대)를 저장할 딕셔너리.
    ranges = {}
    # 계약의 allowed_values를 미리 파싱해 집합으로 만들어 비교를 빠르게 한다.
    allowed = {name: {contract_value(v, spec["dtype"]) for v in spec["allowed_values"]}
               for name, spec in columns.items() if "allowed_values" in spec}
    # 계약의 min/max 제약 값을 미리 파싱해 둔다.
    bounds = {name: {k: contract_value(v, spec["dtype"]) for k, v in spec.get("constraints", {}).items()}
              for name, spec in columns.items()}
    seen = set()  # primary key 중복 검출을 위한 집합.
    duplicates = malformed = row_count = 0
    # utf-8-sig: BOM이 있는 CSV 파일도 정상적으로 읽히도록 한다.
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        header = next(reader, [])
        observed.update(columns=header, column_count=len(header))
        if len(header) != len(set(header)):
            errors.append("CSV contains duplicate column names")
        # 계약과 CSV 헤더 간 누락/추가 컬럼을 비교한다.
        missing = sorted(set(columns) - set(header))
        extra = sorted(set(header) - set(columns))
        if missing:
            errors.append("Missing columns: " + ", ".join(missing))
        if extra:
            errors.append("Unexpected columns: " + ", ".join(extra))
        for row in reader:
            row_count += 1
            # 컬럼 수가 헤더와 다르면 형식이 깨진 행으로 간주한다.
            if len(row) != len(header):
                malformed += 1
                continue
            values = dict(zip(header, row))
            parsed = {}
            for name, spec in columns.items():
                if name not in values:
                    continue
                value = values[name]
                # 빈 문자열은 null로 취급한다.
                if value == "":
                    counts[name]["null_count"] += 1
                    if not spec["nullable"]:
                        counts[name]["non_nullable_violations"] += 1
                    continue
                # 타입 파싱에 실패하면 타입 위반으로 기록하고 다음 컬럼으로 넘어간다.
                try:
                    value = parse_value(value, spec["dtype"])
                except (ValueError, OverflowError):
                    counts[name]["type_violations"] += 1
                    continue
                parsed[name] = value
                # 허용값 집합에 없는 값이면 위반으로 기록.
                if name in allowed and value not in allowed[name]:
                    counts[name]["allowed_values_violations"] += 1
                # min/max 범위를 벗어나는 값이면 위반으로 기록.
                if any((k == "min" and value < v) or (k == "max" and value > v)
                       for k, v in bounds[name].items()):
                    counts[name]["range_violations"] += 1
                # 날짜/시각 컬럼은 관측 범위를 갱신한다.
                if spec["dtype"] in {"date", "datetime"}:
                    low, high = ranges.get(name, (value, value))
                    ranges[name] = (min(low, value), max(high, value))
            # primary key가 모두 정상 파싱된 경우에만 중복 검사를 수행한다.
            keys = contract["primary_key"]
            if keys and all(k in parsed for k in keys):
                key = tuple(parsed[k] for k in keys)
                if key in seen:
                    duplicates += 1
                seen.add(key)
    # null_count를 제외한 각종 위반 횟수가 0이 아니면 오류 메시지로 변환한다.
    for name, statistics in counts.items():
        for check, count in sorted(statistics.items()):
            if check != "null_count" and count:
                errors.append(f"{name}: {check}={count}")
    if malformed:
        errors.append(f"Malformed CSV rows: {malformed}")
    if duplicates:
        errors.append(f"Duplicate primary key rows: {duplicates}")
    # 관측 통계를 종합한다. 날짜 범위는 JSON 직렬화를 위해 ISO 문자열로 변환.
    observed.update(
        row_count=row_count,
        null_counts={name: counts[name]["null_count"] for name in columns if name in header},
        date_ranges={name: {"min": low.isoformat(), "max": high.isoformat()}
                     for name, (low, high) in ranges.items()},
    )
    return observed, errors


def build_codebook(root, contract_dir):
    """계약 디렉터리의 모든 YAML을 읽어 codebook(코드북)을 생성한다.

    각 계약 파일을 로드·검증하고, 검증을 통과한 파일에 대해서만 실제 CSV
    데이터 검사까지 수행한다. 최종 결과를 dataset_id 기준으로 정렬해
    하나의 codebook 딕셔너리로 반환한다.

    Args:
        root (Path): 프로젝트 루트 경로. CSV 경로 해석의 기준이 된다.
        contract_dir (Path): YAML 계약 파일이 위치한 디렉터리.

    Returns:
        dict: ``schema_version``, ``datasets``(계약별 상세), ``validation``
        (전체 상태와 오류) 키를 가진 codebook 구조.
    """
    entries = []
    # .yaml과 .yml 확장자를 모두 수집하고 정렬해 결정적 순서를 보장한다.
    paths = sorted(set(contract_dir.glob("*.yaml")) | set(contract_dir.glob("*.yml")))
    for path in paths:
        entry = {"contract_file": path.name, "contract": None, "observed": None,
                 "validation": {"status": "failed", "errors": []}}
        try:
            contract = yaml.load(path.read_text(encoding="utf-8"), Loader=ContractLoader)
            # YAML의 date/datetime 객체를 ISO 문자열로 정규화하고 JSON 직렬화 가능하게 만든다.
            contract = json.loads(json.dumps(contract, default=lambda v: v.isoformat(), allow_nan=False))
            entry["contract"] = contract
            entry["validation"]["errors"] = validate_contract(contract)
        except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError, AttributeError) as exc:
            entry["validation"]["errors"] = [f"Cannot read contract: {exc}"]
        entries.append(entry)
    # dataset_id 중복을 탐지하기 위한 카운터.
    ids = Counter(e["contract"].get("dataset_id") for e in entries
                  if isinstance(e["contract"], dict) and isinstance(e["contract"].get("dataset_id"), str))
    for entry in entries:
        contract = entry["contract"]
        errors = entry["validation"]["errors"]
        # 같은 dataset_id가 여러 계약에 쓰이면 중복 오류로 처리한다.
        if isinstance(contract, dict) and isinstance(contract.get("dataset_id"), str) and ids[contract["dataset_id"]] > 1:
            errors.append("Duplicate dataset_id: " + contract["dataset_id"])
        # 이미 계약 검증에서 오류가 있으면 데이터 검사는 건너뛴다.
        if errors:
            continue
        try:
            relative = Path(contract["path"])
            path = (root / relative).resolve()
            # 경로는 반드시 프로젝트 루트 안의 상대 경로여야 한다(디렉터리 탈출 방지).
            if relative.is_absolute() or not path.is_relative_to(root.resolve()):
                raise ValueError("path must be relative and remain within project root")
            entry["observed"], failures = inspect_csv(path, contract)
            errors.extend(failures)
        except (OSError, UnicodeError, csv.Error, ValueError, OverflowError) as exc:
            # 파서 예외에 포함된 CSV 값은 공유 codebook에 노출하지 않는다.
            errors.append(f"Cannot inspect data file ({type(exc).__name__})")
        entry["validation"]["status"] = "failed" if errors else "passed"
    # dataset_id(없으면 빈 문자열)와 파일명 순으로 정렬해 출력 순서를 고정한다.
    entries.sort(key=lambda e: (str((e["contract"] or {}).get("dataset_id", ""))
                               if isinstance(e["contract"], dict) else "", e["contract_file"]))
    return {"schema_version": "0.1", "datasets": entries,
            "validation": {"status": "passed" if entries and all(e["validation"]["status"] == "passed" for e in entries) else "failed",
                           "errors": [] if entries else ["No YAML contracts found"]}}


def main(argv=None):
    """CLI 진입점: 계약을 검증하고 codebook.json을 원자적으로 기록한다.

    Args:
        argv (list[str] | None): 명령줄 인자 목록. ``None``이면 ``sys.argv``를 사용한다.

    Returns:
        int: 검증 통과 시 ``0``, 실패 시 ``1`` (프로세스 종료 코드).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Project root (default: script's project)")
    parser.add_argument("--contract-dir", type=Path, default=Path("data/contract"))
    parser.add_argument("--output", type=Path, default=Path("data/codebook/codebook.json"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    codebook = build_codebook(root, root / args.contract_dir)
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # 임시 파일에 먼저 쓰고 rename으로 교체해 부분 기록(손상 파일)을 방지한다.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(codebook, stream, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        temporary.replace(output)
    finally:
        # 예외 발생 시 임시 파일을 정리한다.
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print(f"{codebook['validation']['status']}: {output}")
    # 개별 계약의 검증 오류는 stderr로 보고한다.
    for entry in codebook["datasets"]:
        for error in entry["validation"]["errors"]:
            print(f"{entry['contract_file']}: {error}", file=sys.stderr)
    # 계약 파일이 하나도 없는 경우 등 전역 오류도 stderr로 보고한다.
    for error in codebook["validation"]["errors"]:
        print(error, file=sys.stderr)
    return 0 if codebook["validation"]["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
