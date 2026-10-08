const DATA_PATHS = {
  analysis: "./public/data/flowshock_analysis_bundle.json",
  modeling: "./public/data/flowshock_modeling_bundle.json"
};

const appState = {
  analysis: null,
  modeling: null
};

const formatters = {
  integer: new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }),
  compact: new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }),
  decimal: new Intl.NumberFormat("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
  oneDecimal: new Intl.NumberFormat("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  percent: new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 })
};

function byId(id) {
  return document.getElementById(id);
}

function isValue(value) {
  return value !== null && value !== undefined && value !== "" && Number.isNaN(value) === false;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function metricValue(value, type = "decimal") {
  if (!isValue(value)) return "Not available";
  if (type === "text") return String(value);

  const number = Number(value);
  if (!Number.isFinite(number)) return "Not available";

  if (type === "percent") return formatters.percent.format(number);
  if (type === "score") return formatters.oneDecimal.format(number);
  if (type === "integer") return formatters.integer.format(number);
  if (type === "compact") return formatters.compact.format(number);
  if (type === "signedPctPoint") {
    return `${number > 0 ? "+" : ""}${formatters.oneDecimal.format(number)} pp`;
  }
  return formatters.decimal.format(number);
}

function metricCard(label, value, note = "", type = "decimal") {
  return `
    <article class="metric-card">
      <span class="metric-label">${escapeHtml(label)}</span>
      <strong class="metric-value">${escapeHtml(metricValue(value, type))}</strong>
      ${note ? `<p class="metric-note">${escapeHtml(note)}</p>` : ""}
    </article>
  `;
}

function emptyState(message) {
  return `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function statusPill(value) {
  const text = String(value ?? "unknown");
  const modifier = text === "passed" || text === "usable" ? "" : text === "review_required" ? " status-pill--warn" : " status-pill--bad";
  return `<span class="status-pill${modifier}">${escapeHtml(text)}</span>`;
}

function rankPill(value) {
  return `<span class="rank-pill">#${escapeHtml(value)}</span>`;
}

function modelsList(modeling) {
  return Object.values(modeling?.performance?.models || {});
}

function findModel(modeling, needle) {
  const lowerNeedle = needle.toLowerCase();
  return modelsList(modeling).find((model) => String(model.model_name || "").toLowerCase().includes(lowerNeedle));
}

function findMetric(model, options = {}) {
  const split = options.split || "test";
  const championOnly = options.championOnly ?? true;
  const metrics = Array.isArray(model?.metrics) ? model.metrics : [];
  return metrics.find((metric) => metric.split === split && (!championOnly || metric.is_champion === true)) ||
    metrics.find((metric) => metric.split === split) ||
    null;
}

function table(headers, rows) {
  if (!rows.length) return emptyState("The copied aggregate bundle does not include rows for this panel.");
  return `
    <table>
      <thead>
        <tr>${headers.map((header) => `<th>${escapeHtml(header.label)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.map((row, rowIndex) => `
          <tr>
            ${headers.map((header) => `<td>${header.render ? header.render(row, rowIndex) : escapeHtml(row[header.key] ?? "Not available")}</td>`).join("")}
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderHero(modeling, analysis) {
  const shock = findMetric(findModel(modeling, "Shock Pulse"));
  const loss = findMetric(findModel(modeling, "Loss Priority"), { championOnly: false });
  const modelingQuality = modeling?.quality;
  const analysisQuality = analysis?.quality;

  byId("qualityBadge").textContent = modelingQuality
    ? `${modelingQuality.passed} passed / ${modelingQuality.failed} failed`
    : "Quality unavailable";

  byId("heroReadouts").innerHTML = [
    `<div class="readout"><span>Shock Pulse F1</span><strong>${escapeHtml(metricValue(shock?.f1))}</strong></div>`,
    `<div class="readout"><span>Top10 Capture</span><strong>${escapeHtml(metricValue(loss?.top10_loss_capture, "percent"))}</strong></div>`,
    `<div class="readout"><span>Top5 Lift</span><strong>${escapeHtml(metricValue(loss?.top5_lift))}x</strong></div>`,
    `<div class="readout"><span>Analysis Checks</span><strong>${escapeHtml(analysisQuality ? `${analysisQuality.passed} OK` : "N/A")}</strong></div>`
  ].join("");
}

function renderOverview(analysis, modeling) {
  const period = analysis?.metadata?.period;
  const regions = analysis?.regional_dashboard || [];
  const totalSales = regions.reduce((sum, row) => sum + Number(row.total_sales_amount || 0), 0);
  const totalIndustries = regions.reduce((sum, row) => sum + Number(row.industries || 0), 0);

  byId("overviewMetrics").innerHTML = [
    metricCard("Analysis Period", period ? `${period.start} to ${period.end}` : null, "From analysis bundle metadata", "text"),
    metricCard("Regions", regions.length, "Aggregate dashboard regions", "integer"),
    metricCard("Industry Observations", totalIndustries, "Regional industry counts summed", "integer"),
    metricCard("Aggregate Sales", totalSales, "Total sales amount in copied bundle", "compact")
  ].join("");

  byId("regionalTable").innerHTML = table([
    { label: "Region", key: "merchant_region" },
    { label: "Days", render: (row) => metricValue(row.days, "integer") },
    { label: "Industries", render: (row) => metricValue(row.industries, "integer") },
    { label: "Rain Rows", render: (row) => metricValue(row.rain_days, "integer") },
    { label: "Heavy20 Rows", render: (row) => metricValue(row.heavy20_days, "integer") },
    { label: "Total Sales", render: (row) => metricValue(row.total_sales_amount, "compact") }
  ], regions);

  const interpretation = modeling?.metadata?.interpretation || analysis?.metadata?.interpretation;
  if (interpretation) {
    byId("overviewMetrics").insertAdjacentHTML("beforeend", metricCard("Interpretation", interpretation, "Bundle metadata statement", "text"));
  }
}

function renderShockPulse(modeling) {
  const shockModel = findModel(modeling, "Shock Pulse");
  const shock = findMetric(shockModel);
  const weatherModel = findModel(modeling, "Weather-conditioned Shock");
  const weather = findMetric(weatherModel);

  byId("shockMetrics").innerHTML = shock ? [
    metricCard("Champion", shockModel?.champion_algorithm || "Not available", "Selected on validation F1", "text"),
    metricCard("Test F1", shock.f1, "Positive-class tradeoff", "decimal"),
    metricCard("Test ROC-AUC", shock.roc_auc, "Ranking separation", "decimal"),
    metricCard("Test PR-AUC", shock.pr_auc, "Imbalanced-target view", "decimal"),
    metricCard("Recall", shock.recall, "Detected positive shock cases", "percent"),
    metricCard("Top10 Recall", shock.top10_recall, "Top decile concentration", "percent")
  ].join("") : emptyState("Shock Pulse champion/test metrics were not found in the modeling bundle.");

  byId("weatherShockSummary").innerHTML = weather ? `
    <h3>Weather-conditioned Shock summary</h3>
    <p>Champion ${escapeHtml(weatherModel?.champion_algorithm || "not available")}: F1 ${escapeHtml(metricValue(weather.f1))}, PR-AUC ${escapeHtml(metricValue(weather.pr_auc))}, precision ${escapeHtml(metricValue(weather.precision, "percent"))}, top10 recall ${escapeHtml(metricValue(weather.top10_recall, "percent"))}. This is a rare weather-filtered target, so PR-AUC and top-k recall are foregrounded before ROC-AUC.</p>
  ` : emptyState("Weather-conditioned Shock summary was not found in the modeling bundle.");
}

function renderRecoveryClock(modeling) {
  const recoveryModel = findModel(modeling, "Recovery Clock");
  const recovery = findMetric(recoveryModel);

  byId("recoveryMetrics").innerHTML = recovery ? [
    metricCard("Champion", recoveryModel?.champion_algorithm || "Not available", "Exploratory recovery signal", "text"),
    metricCard("Test F1", recovery.f1, "Compared with baseline F1", "decimal"),
    metricCard("Baseline F1", recovery.baseline_f1, "Majority/tuned baseline context", "decimal"),
    metricCard("Test PR-AUC", recovery.pr_auc, "Event-window target view", "decimal"),
    metricCard("Recall", recovery.recall, "Broad positive capture", "percent"),
    metricCard("Top20 Recall", recovery.top20_recall, "Top quintile concentration", "percent")
  ].join("") : emptyState("Recovery Clock metrics were not found in the modeling bundle.");
}

function renderClimateScar(analysis) {
  const rows = (analysis?.vulnerability_matrix || []).slice(0, 8);
  byId("scarTable").innerHTML = table([
    { label: "Rank", render: (_row, index) => rankPill(index + 1) },
    { label: "Region", key: "merchant_region" },
    { label: "Industry", key: "industry" },
    { label: "Scar Score", render: (row) => metricValue(row.support_priority_score, "score") },
    { label: "Initial Shock", render: (row) => metricValue(row.median_initial_shock_pp, "signedPctPoint") },
    { label: "Net Damage", render: (row) => metricValue(row.median_net_damage_pp, "signedPctPoint") },
    { label: "Persistent Share", render: (row) => metricValue(row.persistent_damage_share, "percent") },
    { label: "Reliability", render: (row) => statusPill(row.reliability_flag) }
  ], rows.map((row, index) => ({ ...row, _index: index })));
}

function renderLossPriority(modeling) {
  const lossModel = findModel(modeling, "Loss Priority");
  const loss = findMetric(lossModel, { championOnly: false });
  const rows = modeling?.loss_priority_top20 || [];

  byId("lossMetrics").innerHTML = loss ? [
    metricCard("Top5 Capture", loss.top5_loss_capture, "Share of modeled test loss in top 5%", "percent"),
    metricCard("Top5 Lift", loss.top5_lift, "Support attention concentration", "decimal"),
    metricCard("Top10 Capture", loss.top10_loss_capture, "Share of modeled test loss in top 10%", "percent"),
    metricCard("Top10 Lift", loss.top10_lift, "Ranking efficiency", "decimal"),
    metricCard("Top20 Capture", loss.top20_loss_capture, "Share of modeled test loss in top 20%", "percent"),
    metricCard("Top20 Lift", loss.top20_lift, "Broad support slate", "decimal")
  ].join("") : emptyState("Loss Priority top-k metrics were not found in the modeling bundle.");

  byId("lossPriorityTable").innerHTML = table([
    { label: "Rank", render: (row) => rankPill(row.priority_rank ?? "N/A") },
    { label: "Region", key: "merchant_region" },
    { label: "Industry", key: "industry" },
    { label: "Predicted Priority", render: (row) => metricValue(row.predicted_total_loss_priority, "compact") },
    { label: "Observed Est. Loss", render: (row) => metricValue(row.observed_total_estimated_loss, "compact") },
    { label: "Mean Shock Risk", render: (row) => metricValue(row.mean_predicted_shock_pulse_risk, "percent") }
  ], rows.slice(0, 8));
}

function renderTriageScore(modeling) {
  const rows = modeling?.triage_top20 || [];
  byId("triageTable").innerHTML = table([
    { label: "Rank", render: (_row, index) => rankPill(index + 1) },
    { label: "Region", key: "merchant_region" },
    { label: "Industry", key: "industry" },
    { label: "Triage", render: (row) => metricValue(row.climate_ecg_triage_score, "score") },
    { label: "Shock Risk", render: (row) => metricValue(row.predicted_shock_pulse_risk, "percent") },
    { label: "Recovery Risk", render: (row) => metricValue(row.predicted_recovery_clock_risk, "percent") },
    { label: "Climate Scar", render: (row) => metricValue(row.climate_scar_score, "score") },
    { label: "Events", render: (row) => metricValue(row.observed_event_count, "integer") }
  ], rows.slice(0, 8));
}

function performanceRows(modeling) {
  return modelsList(modeling).flatMap((model) => {
    const metrics = Array.isArray(model.metrics) ? model.metrics : [];
    return metrics
      .filter((metric) => metric.split === "test")
      .map((metric) => ({ ...metric, model_group: model.model_name, champion_algorithm: model.champion_algorithm }));
  });
}

function renderPerformance(modeling) {
  byId("performanceTable").innerHTML = table([
    { label: "Model", render: (row) => escapeHtml(row.model_name || row.model_group) },
    { label: "Target", key: "target" },
    { label: "F1", render: (row) => isValue(row.f1) ? metricValue(row.f1) : "N/A" },
    { label: "PR-AUC", render: (row) => isValue(row.pr_auc) ? metricValue(row.pr_auc) : "N/A" },
    { label: "ROC-AUC", render: (row) => isValue(row.roc_auc) ? metricValue(row.roc_auc) : "N/A" },
    { label: "Recall", render: (row) => isValue(row.recall) ? metricValue(row.recall, "percent") : "N/A" },
    { label: "Top10 Recall", render: (row) => isValue(row.top10_recall) ? metricValue(row.top10_recall, "percent") : "N/A" },
    { label: "Top5 Capture", render: (row) => isValue(row.top5_loss_capture) ? metricValue(row.top5_loss_capture, "percent") : "N/A" },
    { label: "Top10 Lift", render: (row) => isValue(row.top10_lift) ? `${metricValue(row.top10_lift)}x` : "N/A" }
  ], performanceRows(modeling));
}

function renderGuardrails(modeling, analysis) {
  const cards = [
    {
      title: "Non-causal",
      text: "The dashboard frames observed aggregate associations and predictive rankings. It does not assign causes to weather, districts, or industries."
    },
    {
      title: "Retrospective only",
      text: "Prediction artifacts are same-day/retrospective evaluation outputs and include observed outcomes in validation/test contexts."
    },
    {
      title: "Prospective boundary",
      text: "Prospective use would require forecast weather inputs, deployment-specific validation, and monitoring outside this MVP."
    },
    {
      title: "Quality status",
      text: `Modeling quality: ${modeling?.quality ? `${modeling.quality.passed} passed, ${modeling.quality.failed} failed` : "not available"}. FlowShock analysis checks: ${analysis?.quality ? `${analysis.quality.passed} passed, ${analysis.quality.failed} failed` : "not available"}.`
    },
    {
      title: "Aggregate-only data",
      text: "The app fetches only the two copied aggregate JSON bundles from web/public/data and does not read raw competition files."
    },
    {
      title: "Loss interpretation",
      text: "Loss Priority is a support-ranking layer. Estimated loss is modeled baseline-relative loss, not audited financial damage."
    },
    {
      title: "Recovery Clock caveat",
      text: "Recovery Clock is shown as an exploratory, downweighted recovery-risk signal rather than the primary model."
    },
    {
      title: "Policy boundary",
      text: "Scores are candidate prioritization aids. Final policy decisions require human review and additional context."
    }
  ];

  byId("guardrailCards").innerHTML = cards.map((card) => `
    <article class="guardrail-card">
      <h3>${escapeHtml(card.title)}</h3>
      <p>${escapeHtml(card.text)}</p>
    </article>
  `).join("");
}

function renderAll() {
  const { analysis, modeling } = appState;
  renderHero(modeling, analysis);
  renderOverview(analysis, modeling);
  renderShockPulse(modeling);
  renderRecoveryClock(modeling);
  renderClimateScar(analysis);
  renderLossPriority(modeling);
  renderTriageScore(modeling);
  renderPerformance(modeling);
  renderGuardrails(modeling, analysis);
}

function renderFatal(error) {
  byId("qualityBadge").textContent = "Load failed";
  const message = `Unable to load copied aggregate bundles from web/public/data. Run a local static server from web/ instead of opening file:// directly. Detail: ${error.message}`;
  byId("app").innerHTML = `<section class="panel panel--wide">${emptyState(message)}</section>`;
}

async function loadBundles() {
  const [analysisResponse, modelingResponse] = await Promise.all([
    fetch(DATA_PATHS.analysis),
    fetch(DATA_PATHS.modeling)
  ]);

  if (!analysisResponse.ok) throw new Error(`${DATA_PATHS.analysis} returned ${analysisResponse.status}`);
  if (!modelingResponse.ok) throw new Error(`${DATA_PATHS.modeling} returned ${modelingResponse.status}`);

  appState.analysis = await analysisResponse.json();
  appState.modeling = await modelingResponse.json();
  renderAll();
}

loadBundles().catch(renderFatal);

