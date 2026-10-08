# FlowShock Data Foundation

This phase creates compact, analysis-ready aggregate tables for FlowShock. It never modifies raw data and does not produce individual- or store-level outputs.

## Run

```powershell
python analysis\flowshock_foundation\build_foundation.py --out analysis\flowshock_foundation\out
```

Validate existing outputs without rebuilding:

```powershell
python analysis\flowshock_foundation\build_foundation.py --out analysis\flowshock_foundation\out --check-only
```

Run unit tests:

```powershell
python -m unittest discover -s tests -p "test*.py" -v
```

## Source Grains

| Source | Grain | Notes |
| --- | --- | --- |
| Card1 | date x 6-hour band x merchant region x industry x sex x age | Daily and time-band sales facts |
| Card2 | date x merchant region x industry x customer broad area x sex x age | Customer geography is broad-area, not district residence |
| SKT time | month x block-coordinate cell with 24 hourly columns | Monthly structural profile |
| SKT age | month x block-coordinate cell with sex-age columns | Monthly structural profile |
| SKT weekday | month x block-coordinate cell with weekday columns | Monthly structural profile |
| Weather | hourly station observation | Aggregated to regional daily and 6-hour facts |
| Holidays | holiday date | Joined to daily facts |

## Allowed Joins

- Card1 daily to weather daily and calendar on `date, merchant_region`.
- Card1 time-band to weather time-band and calendar on `date, time_band, merchant_region`.
- Card2 may be aggregated upward to a monthly broad-area inflow profile.
- Card and SKT may be compared only at the aggregate `month, time_band` profile grain in phase 1.

## Forbidden Joins

- Monthly SKT metrics must not be repeated onto daily or event rows.
- Card and SKT data must not be interpreted as person-level movement-to-purchase conversion.
- `서울` must not be interpreted as Gangnam residence, and `강원` must not be interpreted as Chuncheon residence.

The unit-tested grain guard fails a daily table containing SKT monthly fields.

## Outputs

The `out` directory contains:

- Calendar, weather, Card1, Card2, and SKT aggregate profiles.
- Daily and time-band card-weather-calendar marts.
- A month-time-band aggregate card/SKT comparison table.
- `data_dictionary.csv` with the grain and key status of every output column.
- `manifest.json` with source and output statistics, including SKT exact-duplicate counts.
- `quality_report.json` with key, domain, reconciliation, join-cardinality, and grain-safety checks.

CSV files use UTF-8 with BOM. JSON files use UTF-8.

## Privacy and Security

- Raw competition data remains local and read-only.
- Only aggregates are written under `analysis/flowshock_foundation/out`.
- Outputs must not be uploaded externally unless competition disclosure rules explicitly permit it.
- Foundation outputs support retrospective analysis; they are not real-time predictions or causal estimates.

## Next Analysis Step

Use `mart_daily_region_industry_weather.csv` and `mart_timeband_region_industry_weather.csv` to build the FlowShock baseline and shock-recovery layer:

- Estimate region x industry x weekday median baselines.
- Compute shock, rebound, net damage, and persistence metrics.
- Add structural context from `card2_month_region_customer_inflow.csv` and monthly SKT profile tables only at monthly/profile grain.
- Export web-ready aggregate JSON for the regional dashboard, industry vulnerability matrix, support-priority board, and policy brief.
