# FlowShock Climate ECG Web MVP

Static dashboard for the FlowShock Climate ECG aggregate analysis and modeling artifacts. It has no runtime package dependencies and does not require `npm install` for basic viewing.

## Run

From this directory:

```powershell
npm start
```

Then open:

```text
http://localhost:4173
```

Alternative static servers also work, for example:

```powershell
python -m http.server 4173
```

Open `http://localhost:4173` after starting the server. Opening `index.html` directly with `file://` is not recommended because browsers block `fetch()` for local JSON in many configurations.

## Data Used

The dashboard fetches only copied aggregate bundles from `web/public/data/`:

```text
web/public/data/flowshock_analysis_bundle.json
web/public/data/flowshock_modeling_bundle.json
```

These files were copied from:

```text
analysis/flowshock_analysis/out/flowshock_analysis_bundle.json
analysis/flowshock_modeling/out/flowshock_modeling_bundle.json
```

The public copies sanitize local absolute `metadata.source` paths so published dashboard files do not expose workstation/user directory names. Model and analysis metrics are otherwise copied from the aggregate outputs.

It does not read raw competition data, files under `data/`, or any analysis/modeling pipeline files at runtime.

## Sections

- Overview
- Shock Pulse
- Recovery Clock
- Climate Scar
- Loss Priority
- Triage Score
- Model Performance
- Guardrails

## Framing

This is predictive aggregate decision support, not causal estimation and not a final policy decision tool. It is a same-day/retrospective evaluation artifact. Prospective use would require forecast weather inputs, separate validation, and additional governance.
