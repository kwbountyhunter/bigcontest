# 데이터 관리 가이드

`data/` 폴더는 우리 프로젝트의 데이터를 다루는 모든 것을 담는 곳입니다.

핵심 원칙은 딱 하나입니다.

> **데이터 파일 자체는 Git에 올리지 않습니다. 대신 "데이터의 모양(계약)"과 "데이터를 만드는 방법(스크립트)"만 공유합니다.**

이렇게 하면 각자 로컬에 데이터를 내려받아 같은 방법으로 정제하고, 그 결과가
서로 맞는지 자동으로 검증할 수 있습니다.

## 데이터 흐름 한눈에 보기

```text
raw/ ──전처리 스크립트──▶ preprocessed/
(받은 그대로)               (정제된 CSV)
                                │
contract/*.yaml ──코드북 생성기──▶ codebook/codebook.json
(데이터 모양의 약속)                  (검사 결과 보고서)
```

1. **`raw/`**: 외부에서 내려받은 원본 데이터를 그대로 보관합니다.
2. **`preprocessed/`**: 분석 코드가 실제로 사용하는 정제된 CSV를 보관합니다.
3. **`contract/*.yaml`**: 각 데이터가 "이렇게 생겼어야 한다"는 약속을 적어둔 파일입니다.
4. **`codebook/codebook.json`**: 실제 데이터가 약속대로인지 검사한 결과 보고서입니다. 스크립트가 자동 생성합니다.

---

## 기억할 것 4가지

| 폴더/파일 | 한 줄 설명 | 누가 만들까 |
| --- | --- | --- |
| `raw/` | 받은 그대로의 원본 데이터 | 사람(다운로드) |
| `preprocessed/` | 분석에 쓰는 정제된 CSV | 전처리 스크립트 |
| `contract/*.yaml` | "이 데이터는 이렇게 생겼어야 해" 약속 | 사람(직접 작성) |
| `codebook/codebook.json` | 약속대로인지 검사한 보고서 | 코드북 생성기(자동) |

- **원본(raw)**은 절대 직접 수정하지 않습니다. 정제는 전처리 스크립트가 합니다.
- **계약(contract)**은 사람이 쓰는 "기대 사항"이고, **코드북(codebook)**은 기계가 만드는 "실제 검사 결과"입니다.

---

## 5분 따라하기: `weather_example`

예시 데이터셋(서울 시간별 기상 관측)을 그대로 실행해 보면 전체 흐름이 한 번에 이해됩니다.

### 1. 준비

Python 3.9 이상이 필요합니다. 필요한 라이브러리는 하나뿐입니다.

```bash
python3 -m pip install -r data/requirements.txt
```

### 2. 예시 데이터 확인

`data/raw/weather_example.csv`는 기상청 지점 108(서울)의 시간별 관측 원본입니다.
참고용으로 Git에 포함되어 있으니 바로 사용할 수 있습니다.

원본을 열어보면 컬럼명이 한글이고(`지점`, `일시`, `기온(°C)`...), 각 수치 옆에
`QC플래그` 컬럼이 붙어 있습니다. 이 플래그는 값의 품질을 나타냅니다:

- 빈값 → 정상(0)
- `1` → 오류
- `9` → 결측

### 3. 전처리 실행

```bash
python3 data/scripts/preprocessing/weather_example.py
```

이 스크립트는 원본(CP949 인코딩)을 읽어 다음을 수행합니다:

- 컬럼명을 영문 `snake_case`로 변경 (`기온(°C)` → `temperature_c`)
- QC플래그가 오류·결측인 수치를 비워서(null) 처리
- 강수량은 "정상인데 비어 있는 값"이면 0.0mm로 채움
- 일시를 ISO 8601 + KST(`+09:00`) 형식으로 변환

결과는 `data/preprocessed/weather_example.csv`(UTF-8 CSV)로 저장됩니다.

### 4. 코드북 생성

```bash
python3 data/scripts/codebook_json_file_maker.py
```

약속(계약)과 실제 정제 결과를 비교한 뒤 `data/codebook/codebook.json`을 다시 만듭니다.

```text
passed: data/codebook/codebook.json
```

`passed`는 "실제 데이터가 계약대로다"라는 뜻입니다.

### 5. 결과 확인

`codebook.json`에서 아래 세 부분을 보면 됩니다.

| 영역 | 의미 | 예시 |
| --- | --- | --- |
| `contract` | 우리가 기대한 데이터 구조 | 컬럼, 타입, 제약조건 |
| `observed` | 실제 데이터에서 관측한 값 | `row_count: 4416`, 날짜 범위, `sha256` |
| `validation` | 검사 결과 | `status: passed`, 실패 시 `errors` |

특히 `observed.date_ranges`의 `datetime`을 보면 `2025-07-01T00:00:00+09:00`처럼
**KST(+09:00)가 그대로 보존**되어 있는 걸 확인할 수 있습니다.

---

## 내 데이터를 추가하는 4단계

새 데이터를 이 구조에 맞게 추가할 때는 아래 순서대로 진행합니다.

### 1단계. 원본 데이터 받기

팀이 공유한 원본 데이터 모음 링크에서 파일을 내려받아 `raw/`에 넣습니다.
자세한 규칙은 [아래](#협업에서-원본-데이터를-다루는-규칙)를 참고하세요.

### 2단계. 계약 작성

`contract/<table>.yaml` 파일을 만들고 이 데이터가 갖춰야 할 모양을 적습니다.
구체적인 작성법은 [참고: 계약 작성법](#참고-계약contract-작성법)을 보세요.

### 3단계. 전처리 스크립트 작성

`scripts/preprocessing/<table>.py`에 `raw/ → preprocessed/` 변환을 작성합니다.
`weather_example.py`를 복사해서 시작하면 가장 빠릅니다.

- `raw/`에서 읽어서 컬럼명·타입·날짜 형식을 계약대로 맞춥니다.
- 결과를 UTF-8 CSV로 `preprocessed/`에 저장합니다.
- 변환이 필요 없어도 스크립트를 통해 `preprocessed/`로 CSV를 만듭니다.
  (모든 테이블이 같은 파이프라인을 따르도록 하기 위함)

### 4단계. 검증하고 커밋하기

```bash
python3 data/scripts/codebook_json_file_maker.py
```

- `passed`면 계약·스크립트·코드북을 함께 커밋합니다.
- 실패하면 원인을 확인합니다. 데이터 처리가 잘못됐으면 **전처리 코드**를,
  기대 구조를 잘못 적었으면 **계약**을 고칩니다.

커밋에 포함하는 것은 **계약, 전처리 스크립트, 재생성된 코드북**입니다. 데이터 CSV는 제외합니다.

---

## 협업에서 원본 데이터를 다루는 규칙

원본 데이터는 Git이 아니라 **클라우드 링크**로 공유합니다.

1. 데이터 수집이 끝나면, 원본 데이터를 모아둔 **클라우드 폴더 링크**를 팀에 공유합니다.
2. 각자 그 링크에서 파일을 내려받아 **로컬 `raw/`** 에 넣고, 전처리 스크립트를 실행합니다.
3. `raw/`의 파일은 **절대 수정하지 않습니다.** 폴더 구조와 파일명도 그대로 유지합니다.
   (전처리 스크립트가 특정 경로와 이름을 기준으로 읽기 때문)
4. 원본 데이터는 **Git에 올리지 않습니다.** `.gitignore`가 `raw/`와 `preprocessed/`의
   데이터 파일을 자동으로 제외합니다.
   - 예외: `weather_example.csv`(원본·정제 결과)는 예시용으로만 Git에 포함되어 있습니다.
5. 출처와 수집 시각은 계약의 `source`에 기록해 두면 팀원 누구나 원본을 추적할 수 있습니다.

> 데이터가 어디서 왔는지(출처)는 가능한 한 남겨 두세요. 나중에 재현하거나 문제가
> 생겼을 때 원본으로 돌아갈 수 있습니다.

---

## 참고: 계약(contract) 작성법

계약은 테이블마다 YAML 파일 하나입니다. 파일명은 `weather_example.yaml`처럼
테이블을 알아볼 수 있게 짓고, `dataset_id`는 모든 계약에서 중복되지 않게 씁니다.

### 테이블 수준 키

| 키 | 필수 | 작성 방법 |
| --- | --- | --- |
| `schema_version` | 필수 | 계약 형식 버전. v0.1은 문자열 `"0.1"` |
| `dataset_id` | 필수 | `seoul_hourly_weather`처럼 고유한 `snake_case` 식별자 |
| `name` | 필수 | 사람이 읽기 쉬운 데이터 이름 |
| `description` | 필수 | 데이터의 내용과 용도 |
| `source` | 필수 | 제공 기관과 원본 URL 또는 입수 경로 |
| `path` | 필수 | 프로젝트 루트 기준 전처리 파일 경로. 예: `data/preprocessed/weather_example.csv` |
| `format` | 필수 | 전처리 결과 형식. 항상 `csv` |
| `grain` | 필수 | 한 행이 무엇을 의미하는지. "관측소 한 곳의 특정 1시간 관측값 한 건"처럼 구체적으로 |
| `primary_key` | 필수 | 한 행을 식별하는 컬럼 목록. 키가 없다면 `[]`로 쓰고 `notes`에 이유 기록 |
| `temporal_resolution` | 해당 시 | 시간 단위. 예: `day`, `hour` |
| `spatial_resolution` | 해당 시 | 공간 단위. 예: `station`, `district` |
| `columns` | 필수 | 정제 결과의 모든 컬럼을 이름별로 정의 |
| `notes` | 선택 | 사용 시 주의점, 예외, 한계 |

`grain`은 데이터 자체의 의미로 씁니다. "일별 기상 데이터"보다
"관측소 한 곳의 특정 날짜에 대한 기상 관측값 한 건"이 명확합니다.
이 경우 `primary_key`는 `[date, station_id]`가 됩니다.

### 컬럼 수준 키

`columns`의 키는 프로젝트에서 쓰는 최종 컬럼명입니다.

| 키 | 필수 | 작성 방법 |
| --- | --- | --- |
| `dtype` | 필수 | `string`, `integer`, `float`, `boolean`, `date`, `datetime` 중 하나 |
| `nullable` | 필수 | 결측 허용 여부 (`true`/`false`) |
| `description` | 권장 | 컬럼이 나타내는 값의 의미 |
| `unit` | 해당 시 | 수치 단위. 예: `Celsius`, `mm`, `m/s` |
| `source_column` | 해당 시 | 대응하는 원본 컬럼명 |
| `transformation` | 해당 시 | 원본에서 최종 값으로 변환하는 방법 설명 |
| `allowed_values` | 선택 | 허용 값 목록. 예: `["M", "F", "unknown"]` |
| `constraints` | 선택 | `min`/`max`로 허용 범위 정의. 경계값 포함 |
| `notes` | 선택 | 컬럼별 예외나 해석 시 주의점 |

작성 시 다음을 지킵니다.

- 컬럼명은 `snake_case`를 쓰고, 같은 의미에는 같은 이름을 씁니다.
  (`date`, `region_code`, `station_id`, `temperature_c` 등)
- 이름을 바꿀 때 의미도 확인합니다. 관측소 코드(`station_id`)와 행정구역 코드(`region_code`)는 구분합니다.
- 앞자리 0을 보존해야 하는 코드는 `string`으로 정의합니다.
- `date` 값은 `YYYY-MM-DD`, `datetime`은 `YYYY-MM-DDTHH:MM:SS±HH:MM` 형식을 사용합니다.
- 기본키 컬럼은 모두 `columns`에 정의하고 `nullable: false`로 지정합니다.
- `source_column`과 `transformation`은 설명용입니다. 실제 변환은 전처리 스크립트가 합니다.

### 완성 예시

`data/contract/weather_example.yaml`이 실제 동작하는 완성 예시입니다.

```yaml
schema_version: "0.1"
dataset_id: seoul_hourly_weather
name: 서울 시간별 기상 관측
description: 기상청 지점 108(서울)의 1시간 간격 기온·강수량·풍속·습도 관측값
source: 기상청 기상자료개방포털 (지점 108 서울)
path: data/preprocessed/weather_example.csv
format: csv
grain: 관측소 한 곳(서울 108)의 특정 1시간에 대한 기상 관측값 한 건
primary_key: [datetime, station_id]
temporal_resolution: hour
spatial_resolution: station
columns:
  station_id:
    dtype: string
    nullable: false
    source_column: 지점
  station_name:
    dtype: string
    nullable: false
    source_column: 지점명
  datetime:
    dtype: datetime
    nullable: false
    source_column: 일시
    transformation: "YYYY-MM-DD HH:MM -> ISO 8601 (KST +09:00)"
  temperature_c:
    dtype: float
    nullable: true
    unit: Celsius
    source_column: 기온(°C)
    constraints: {min: -50, max: 50}
  precipitation_mm:
    dtype: float
    nullable: true
    unit: mm
    source_column: 강수량(mm)
    constraints: {min: 0, max: 1000}
  wind_speed_ms:
    dtype: float
    nullable: true
    unit: m/s
    source_column: 풍속(m/s)
    constraints: {min: 0, max: 60}
  humidity_pct:
    dtype: float
    nullable: true
    unit: percent
    source_column: 습도(%)
    constraints: {min: 0, max: 100}
notes: QC플래그(0 정상/1 오류/9 결측)는 전처리에서 수치 정제에만 사용하고 결과 컬럼에서 제거
```

---

## 참고: 검증 규칙과 명령어

### 코드북 생성기 명령어

```bash
python3 data/scripts/codebook_json_file_maker.py
```

스크립트는 프로젝트 루트를 스스로 찾으므로 어느 위치에서 실행해도 됩니다.
다음 옵션으로 기본 경로를 바꿀 수 있습니다.

| 옵션 | 기본값 | 설명 |
| --- | --- | --- |
| `--root` | 스크립트의 프로젝트 루트 | 프로젝트 루트 경로 |
| `--contract-dir` | `data/contract` | 계약 YAML 폴더 |
| `--output` | `data/codebook/codebook.json` | 출력 JSON 경로 |

### 검증 규칙 요약

- CSV는 **UTF-8(선택적 BOM), 쉼표 구분, 첫 행 헤더**를 지원합니다.
- **빈 필드만 결측값**으로 취급합니다. `NA`, `null` 등은 문자열이며 공백을 자동 제거하지 않습니다.
- 정수는 부호가 선택적인 정수 문자열, 실수는 유한한 숫자, 불리언은 대소문자 구분 없는
  `true`/`false` 또는 `1`/`0`을 허용합니다.
- 날짜·시간 범위는 타입 검증에 성공한 값으로 계산합니다.
  **datetime은 원본이 선언한 오프셋(예: KST `+09:00`)을 그대로 보존합니다.**
- 컬럼 순서는 검증 대상이 아니지만, 누락·추가·중복 컬럼은 실패입니다.
- 기본키는 타입 해석 후 조합의 중복을 검사합니다. 문자열 코드의 앞자리 0은 보존합니다.
- 종료 코드 `0`은 전체 통과, `1`은 검증 실패입니다. 계약이나 데이터가 없을 때도 실패로 기록합니다.
- 데이터셋마다 `validation.errors`에 실패 이유를 기록합니다. 실제 행과 값은 저장하지 않습니다.
- 출력은 정렬된 JSON이며 실행 시각을 포함하지 않습니다. 같은 계약·파일은 같은 결과를 만듭니다.

### 코드북의 해시(`sha256`) 확인

`observed.sha256`은 그 데이터 파일의 바이트가 같은지 확인하는 지문입니다.
값이 같아도 행 순서나 인코딩이 다르면 해시가 달라질 수 있습니다.

공유된 코드북은 생성에 사용한 파일의 검증 기록일 뿐, 다른 팀원의 로컬 파일까지
검증된 것으로 보면 안 됩니다. 자신의 파일 해시를 비교하고 필요하면 다시 검증하세요.

### 테스트 실행

```bash
python3 -m unittest discover -s data/scripts/tests
```

테스트는 임시 데이터로 실행하며 실제 전처리 파일을 변경하지 않습니다.
검증을 통과시키기 위해 코드북을 직접 수정하지 않습니다.

---

## 디렉터리 구조 정리

```text
data/
├── README.md
├── raw/                              # 원본 데이터 (Git 제외)
│   └── weather_example.csv           #   예시용으로만 Git 포함
├── preprocessed/                     # 정제 결과 (Git 제외)
│   └── weather_example.csv           #   예시용으로만 Git 포함
├── contract/
│   └── weather_example.yaml          # 사람이 작성하는 계약
├── codebook/
│   └── codebook.json                 # 자동 생성된 검사 보고서
└── scripts/
    ├── preprocessing/
    │   └── weather_example.py        # 테이블별 전처리 스크립트
    ├── codebook_json_file_maker.py   # 코드북 생성기
    └── tests/
        └── test_codebook_json_file_maker.py
```

| 경로 | 역할 | Git 추적 |
| --- | --- | --- |
| `raw/` | 받은 그대로의 원본 파일 | 데이터 제외 (예시 CSV만 예외) |
| `preprocessed/` | 분석에 쓰는 정제된 CSV | 데이터 제외 (예시 CSV만 예외) |
| `contract/` | 데이터 모양의 약속 (YAML) | 추적 |
| `codebook/` | 자동 생성된 검사 보고서 | 추적 |
| `scripts/` | 전처리·검증 스크립트 | 추적 |

빈 디렉터리는 `.gitkeep`으로 Git에 유지합니다.

### 아직 정하지 않은 것들

아래 항목은 지금은 자동화하지 않고 수동으로 진행합니다. 필요해지면 추가할 예정입니다.

- **데이터 접근 계층**: `load_dataset(dataset_id)` 형태로 데이터를 불러오는 공통 함수
- **수집 이력(provenance) 자동 기록**: `downloaded_at`, 파일 크기 등 자동 수집
- **검증 자동화(CI)**: 커밋 시 자동 검증
