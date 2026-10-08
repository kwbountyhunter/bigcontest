# FlowShock Analysis Layer

This layer consumes only `analysis/flowshock_foundation/out` and produces aggregate shock-recovery metrics plus web-ready JSON for the FlowShock MVP.

## Run

```powershell
python analysis\flowshock_analysis\run_analysis.py --foundation-dir analysis\flowshock_foundation\out --out analysis\flowshock_analysis\out
```

Validate existing outputs:

```powershell
python analysis\flowshock_analysis\run_analysis.py --foundation-dir analysis\flowshock_foundation\out --out analysis\flowshock_analysis\out --check-only
```

## Method

- Daily baseline: region x industry x weekday median sales and use count.
- Heavy-rain event: `daily_rain_mm >= 20`.
- Event window: D-3 to D+3 around heavy-rain dates.
- Time-band vulnerability: region x industry x six-hour band response to six-hour rain.
- Customer context: Card2 broad-area origin shares only, not district residence.
- SKT context: monthly aggregate profile only through foundation outputs; never joined into daily/event rows.

All outputs describe observed aggregate associations. They are not causal estimates and should be treated as support-priority candidates, not final policy decisions.

## Outputs

- `daily_baseline_panel.csv`
- `rain_bin_response_by_region_industry.csv`
- `event_window_metrics_by_industry.csv`
- `shock_recovery_metrics_by_industry.csv`
- `timeband_vulnerability_metrics.csv`
- `broad_area_inflow_context.csv`
- `support_priority_by_industry.csv`
- `regional_dashboard.json`
- `vulnerability_matrix.json`
- `support_priority.json`
- `policy_brief.json`
- `flowshock_analysis_bundle.json`
- `manifest.json`, `quality_report.json`, `data_dictionary.csv`

## Next Product Step

Use `flowshock_analysis_bundle.json` as the data contract for the web MVP screens: regional dashboard, shock explorer, industry vulnerability matrix, support-priority board, and policy brief.
