# RainShock Public Data Archive

This folder stores official public datasets used by RainShock. It is intentionally separate from the competition-provided Shinhan Card and SKT folders.

## Immediate credential-free sources

- KMA station metadata: downloaded from the KMA Data Open Portal station metadata CSV export.
- KMA weather warnings: downloaded through the KMA Data Open Portal warning CSV two-step export for 2025-07-01 through 2025-12-31.

## Key-dependent sources

The following scripts require `DATA_GO_KR_SERVICE_KEY` and skip cleanly when it is absent.

- `Get-KmaAsosHourly.ps1`: ASOS hourly observations for stations 108, 101, 93.
- `Get-KasiHolidays.ps1`: KASI public holidays for 2025.

AWS 400 Gangnam historical data is not fetched automatically because the public data.go.kr AWS API identified for automatic access covers recent two-day minute observations, not Jul-Dec 2025 history. Acquire station 400 historical hourly data manually from the KMA Data Open Portal AWS historical workflow and preserve it under `raw/kma/aws_hourly/stn_400`.

## Safety

Scripts write only under `data/public_rainshock`. They do not read or modify the Shinhan Card or SKT raw folders.
