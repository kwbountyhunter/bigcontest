# FlowShock Climate ECG Modeling Layer

This layer turns the FlowShock analysis outputs into competition-ready predictive/classification artifacts under the **Climate ECG** framing.

## Run

```powershell
python analysis\flowshock_modeling\run_modeling.py --analysis-dir analysis\flowshock_analysis\out --out analysis\flowshock_modeling\out
```

Validate existing outputs:

```powershell
python analysis\flowshock_modeling\run_modeling.py --analysis-dir analysis\flowshock_analysis\out --out analysis\flowshock_modeling\out --check-only
```

## Climate ECG Components

- **Shock Pulse**: daily classifier for large negative sales deviation.
- **Recovery Clock**: event-window classifier for delayed or incomplete recovery.
- **Climate Scar**: observed residual post-event damage score.
- **Triage Score**: decision-support score combining predicted shock risk, predicted recovery risk, and scar score.
- **Loss Priority**: support-priority ranking layer for concentrating attention on rows that account for larger modeled baseline-relative losses.

## Guardrails

- Uses only prepared aggregate outputs from `analysis/flowshock_analysis/out`.
- Does not read raw competition data.
- Uses chronological train/validation/test splits.
- Recomputes daily model baselines from train-period region-industry-weekday medians before deriving labels/losses for validation and test rows.
- Excludes same-day sales-derived fields from Shock Pulse prediction features.
- Keeps lag/history sales features strictly shifted before the prediction row.
- Outputs are predictive decision-support artifacts, not causal estimates or final policy decisions.
- Prediction CSVs are same-day/retrospective aggregate evaluation artifacts. They include observed labels/outcomes for validation and should not be described as live deployment predictions; prospective use requires forecast weather inputs.

## Performance Framing

Shock Pulse is the primary predictive model for the competition modeling requirement. Interpret it with ROC-AUC, PR-AUC, F1, recall, and precision rather than accuracy alone because the majority baseline can have high accuracy while failing to identify positive shock cases.

Weather-conditioned Shock is a rarer weather-filtered target. Present its PR-AUC, precision, positive base rate, and top-k recall before ROC-AUC so the model is not overclaimed as near-perfect.

Recovery Clock is currently exploratory. Event samples are smaller and the signal is broad, so it is downweighted in the triage score and should be presented as an early recovery-risk signal rather than the main predictive model.

Loss Priority is a policy-ranking layer, not a calibrated won-level damage forecast. Use top-k loss capture and lift to explain whether the model concentrates support attention on high-loss rows. `estimated_loss_amount` is modeled baseline-relative loss, not audited financial damage.

## Current Results

| Component | Test result | How to present it |
| --- | ---: | --- |
| Shock Pulse RF | F1 0.501, ROC-AUC 0.784, PR-AUC 0.497, recall 0.743 | Primary binary model for detecting large negative sales shocks. |
| Weather-conditioned Shock | F1 0.449, PR-AUC 0.324, top10 recall 0.929 | Rare weather-filtered target; lead with PR-AUC and top-k recall. |
| Recovery Clock | F1 0.756 vs baseline F1 0.740 | Exploratory recovery-risk signal, downweighted in triage. |
| Loss Priority | top5 capture 26.6% / lift 5.30x; top10 capture 36.6% / lift 3.65x; top20 capture 44.3% / lift 2.21x | Support-priority ranking model; present as top-k efficiency, not won-level forecasting. |

Quality status: `quality_report.json` passes 16 checks with 0 failures. Full FlowShock tests pass 26 cases.

## Outputs

- `model_ready_daily.csv`
- `model_ready_event.csv`
- `shock_pulse_predictions.csv`
- `weather_shock_predictions.csv`
- `recovery_clock_predictions.csv`
- `loss_priority_predictions.csv`
- `loss_priority_by_region_industry.csv`
- `topk_support_priority_metrics.csv`
- `triage_score_by_region_industry.csv`
- `model_performance.csv` / `model_performance.json`
- `feature_importance.csv`
- `model_card.json`
- `flowshock_modeling_bundle.json`
- `manifest.json`, `quality_report.json`, `data_dictionary.csv`
