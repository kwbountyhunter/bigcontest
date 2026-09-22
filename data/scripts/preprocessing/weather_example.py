#!/usr/bin/env python3
"""raw(CP949) 기상 CSV → preprocessed(UTF-8) 정제 CSV 변환.

기상청 지점 108(서울)의 시간별 기온·강수량·풍속·습도 관측 데이터를 읽어
data/contract/weather_example.yaml 계약에 맞는 정제 결과를 만든다.

- QC플래그: 빈값=0(정상), 1(오류), 9(결측). 1·9면 해당 수치를 null 처리.
- 강수량: 정상 QC에서 빈값은 0.0mm(비 없음)로 변환.
- 일시: "YYYY-MM-DD HH:MM" → ISO 8601 KST("+09:00") datetime 문자열로 변환.
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "raw" / "weather_example.csv"
OUT = ROOT / "data" / "preprocessed" / "weather_example.csv"

COLUMNS = ["station_id", "station_name", "datetime",
           "temperature_c", "precipitation_mm", "wind_speed_ms", "humidity_pct"]


def parse_qc(raw):
    raw = (raw or "").strip()
    return 0 if raw == "" else int(raw)


def clean(value, qc):
    """QC 정상(0)이면 값 그대로, 오류·결측(1·9)이면 빈값(null) 반환."""
    return "" if qc in (1, 9) else value.strip()


def to_datetime(raw):
    date_part, time_part = raw.split(" ")
    return f"{date_part}T{time_part}:00+09:00"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with RAW.open(encoding="cp949", newline="") as src, \
         OUT.open("w", encoding="utf-8-sig", newline="") as dst:
        reader = csv.reader(src)
        next(reader)
        writer = csv.writer(dst)
        writer.writerow(COLUMNS)
        for row in reader:
            station_id, station_name, dt, ta, ta_qc, rn, rn_qc, ws, ws_qc, hm, hm_qc = row
            ta_qc, rn_qc, ws_qc, hm_qc = map(parse_qc, (ta_qc, rn_qc, ws_qc, hm_qc))
            if rn_qc in (1, 9):
                precipitation = ""
            elif rn.strip() == "":
                precipitation = "0.0"
            else:
                precipitation = rn.strip()
            writer.writerow([station_id, station_name, to_datetime(dt),
                             clean(ta, ta_qc), precipitation,
                             clean(ws, ws_qc), clean(hm, hm_qc)])


if __name__ == "__main__":
    main()
