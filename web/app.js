const DATA_PATHS = {
  analysis: "./public/data/flowshock_analysis_bundle.json",
  modeling: "./public/data/flowshock_modeling_bundle.json"
};

const state = {
  analysis: null,
  modeling: null,
  boardMode: "triage",
  selectedId: null
};

const formatters = {
  integer: new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 }),
  compact: new Intl.NumberFormat("ko-KR", { notation: "compact", maximumFractionDigits: 1 }),
  decimal: new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
  oneDecimal: new Intl.NumberFormat("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  percent: new Intl.NumberFormat("ko-KR", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  krw: new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW", maximumFractionDigits: 0 })
};

const signalExamples = {
  stable: {
    title: "안정 신호",
    icon: "✓",
    copy: "기준선 주변에서 반응이 유지되는 상황의 시각화 예시입니다.",
    path: "M0 100H75Q85 100 90 94Q96 87 104 100H132L144 109L158 60L173 132L187 100H227Q241 80 255 100H390Q400 100 405 94Q412 88 419 100H446L459 109L473 60L488 132L502 100H542Q556 80 570 100H706L718 110L732 60L747 132L761 100H801Q816 80 830 100H900"
  },
  watch: {
    title: "주의 신호",
    icon: "!",
    copy: "편차가 커지거나 회복이 늦어지는 상황의 시각화 예시입니다.",
    path: "M0 100H68Q81 100 90 90Q100 80 110 100H136L148 116L162 39L181 145L196 103H228Q246 75 263 107H365Q381 96 394 103H431L446 119L462 39L481 145L496 103H528Q546 75 563 107H670Q686 96 699 103H736L750 119L766 39L785 145L800 103H832Q850 75 866 100H900"
  },
  risk: {
    title: "위험 신호",
    icon: "!",
    copy: "큰 충격과 회복 지연이 함께 나타나는 상황의 시각화 예시입니다.",
    path: "M0 100H63Q77 100 88 88Q99 76 110 100H136L148 122L164 15L186 178L201 112L216 100H251Q270 67 289 110H360L375 99L390 108H431L446 122L462 15L484 178L499 112L514 100H549Q568 67 587 110H660L675 99L690 108H731L746 122L762 15L784 178L799 112L814 100H849Q868 67 887 100H900"
  }
};

const stageBlueprints = [
  {
    key: "shock",
    tag: "CORE PREDICTION",
    title: "상권은 얼마나 크게 흔들렸을까?",
    description: "기상·캘린더·상권 조건에서 큰 음의 매출 편차가 발생했는지 감지하는 핵심 예측 모델입니다.",
    statLabel: "Shock Pulse · Test F1",
    caution: "기후가 매출 감소의 원인이라고 단정하지 않습니다.",
    caption: "충격의 크기를 읽는 신호",
    label: "충격 감지 구간",
    x: 113,
    width: 87,
    point: [157, 182],
    path: "M0 78L35 73L70 82L100 75L120 93L137 37L157 182L181 126L205 148L235 124L265 116L295 102L325 99L355 88L385 91L420 78L450 82L480 75"
  },
  {
    key: "recovery",
    tag: "EXPLORATORY SIGNAL",
    title: "회복까지 얼마나 오래 걸릴까?",
    description: "충격 이후 회복 지연 가능성을 살펴봅니다. 즉시 나타난 매출 편차만으로는 보이지 않는 취약성을 탐색적 보조 모델로 해석합니다.",
    statLabel: "Recovery Clock · Test F1",
    caution: "탐색적, 보조적 회복-risk 신호입니다. 정책 결정을 자동화하지 않습니다.",
    caption: "충격 이후의 회복 지연",
    label: "회복 지연 가능성",
    x: 170,
    width: 225,
    point: [295, 133],
    path: "M0 78L35 73L70 82L100 75L120 93L137 37L157 182L181 163L205 172L235 157L265 153L295 133L325 139L355 119L385 106L420 95L450 82L480 75"
  },
  {
    key: "scar",
    tag: "CUMULATIVE VULNERABILITY",
    title: "취약한 신호가 반복해서 남을까?",
    description: "지역·업종별로 반복적으로 나타나는 취약성을 읽습니다. 단일 이벤트를 넘어 누적되는 기후 스트레스 반응을 해석하는 관측 신호입니다.",
    statLabel: "Climate Scar 후보 수",
    caution: "누적 취약성 신호이며, 영구적 피해를 입증하는 지표는 아닙니다.",
    caption: "반복되는 취약 반응의 흔적",
    label: "누적 취약성 해석",
    x: 90,
    width: 340,
    point: [340, 162],
    path: "M0 78L35 73L70 82L95 75L115 160L140 110L165 89L190 86L215 177L240 143L265 100L290 92L315 96L340 162L365 137L395 99L425 108L450 91L480 85"
  },
  {
    key: "loss",
    tag: "RANKING LAYER",
    title: "어디를 먼저 살펴보면 좋을까?",
    description: "기준선 대비 모델링 손실을 바탕으로 지원 검토의 우선순위를 정합니다. 정확한 피해액 예측보다 상위 후보군의 손실 포착 비중과 집중도가 중요합니다.",
    statLabel: "Top10 modeled loss capture",
    caution: "손실은 감사된 실제 피해액이 아닌 baseline-relative modeled loss입니다.",
    caption: "진단 신호에서 검토 우선순위로",
    label: "손실 우선순위 해석",
    x: 0,
    width: 125,
    point: [80, 53],
    path: "M0 30L40 41L80 53L120 69L160 80L200 101L240 114L280 133L320 145L360 162L400 170L440 182L480 188"
  },
  {
    key: "triage",
    tag: "FINAL REVIEW SIGNAL",
    title: "여러 신호를 하나의 후보군으로.",
    description: "Shock risk, Recovery risk, Climate Scar를 결합해 최종 후보군을 요약합니다. Triage Score는 현장 검토를 돕는 진단 신호입니다.",
    statLabel: "Triage 후보 수",
    caution: "최종 정책 결정은 현장 맥락과 사람의 검토가 필요합니다.",
    caption: "여러 신호를 함께 읽는 진단",
    label: "최종 후보군 요약",
    x: 80,
    width: 340,
    point: [260, 142],
    path: "M0 78L40 72L80 88L120 65L160 166L200 108L240 124L260 142L300 106L340 119L380 95L420 101L460 86L480 80"
  }
];

function byId(id) {
  return document.getElementById(id);
}

function all(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function hasValue(value) {
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

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatValue(value, type = "decimal") {
  if (!hasValue(value)) return "N/A";
  if (type === "text") return String(value);
  const number = numberOrNull(value);
  if (number === null) return "N/A";
  if (type === "percent") return formatters.percent.format(number);
  if (type === "percentPoint") return `${number > 0 ? "+" : ""}${formatters.oneDecimal.format(number)}pp`;
  if (type === "percentNumber") return formatters.oneDecimal.format(number * 100);
  if (type === "score") return formatters.oneDecimal.format(number);
  if (type === "integer") return formatters.integer.format(number);
  if (type === "compact") return formatters.compact.format(number);
  if (type === "krw") return formatters.krw.format(number);
  return formatters.decimal.format(number);
}

function modelList() {
  return Object.values(state.modeling?.performance?.models || {});
}

function findModel(needle) {
  const lowerNeedle = needle.toLowerCase();
  return modelList().find((model) => String(model.model_name || "").toLowerCase().includes(lowerNeedle));
}

function findMetric(model, options = {}) {
  const split = options.split || "test";
  const championOnly = options.championOnly ?? true;
  const metrics = Array.isArray(model?.metrics) ? model.metrics : [];
  return metrics.find((metric) => metric.split === split && (!championOnly || metric.is_champion === true)) ||
    metrics.find((metric) => metric.split === split) ||
    null;
}

function shockMetric() {
  return findMetric(findModel("Shock Pulse"));
}

function recoveryMetric() {
  return findMetric(findModel("Recovery Clock"));
}

function weatherMetric() {
  return findMetric(findModel("Weather-conditioned Shock"));
}

function lossMetric() {
  return findMetric(findModel("Loss Priority"), { championOnly: false });
}

function metricTextForStage(key) {
  if (key === "shock") return formatValue(shockMetric()?.f1);
  if (key === "recovery") return formatValue(recoveryMetric()?.f1);
  if (key === "scar") return formatValue((state.analysis?.vulnerability_matrix || []).length, "integer");
  if (key === "loss") return formatValue(lossMetric()?.top10_loss_capture, "percent");
  if (key === "triage") return formatValue((state.modeling?.triage_top20 || []).length, "integer");
  return "N/A";
}

function statusPill(value) {
  const text = String(value ?? "unknown");
  const className = text === "passed" || text === "usable" ? "status-pill" : text === "review_required" ? "status-pill warn" : "status-pill bad";
  return `<span class="${className}">${escapeHtml(text)}</span>`;
}

function rankPill(value) {
  return `<span class="rank-pill">${escapeHtml(value)}</span>`;
}

function emptyState(title, text) {
  return `<div class="empty-state"><span>⊕</span><h4>${escapeHtml(title)}</h4><p>${escapeHtml(text)}</p></div>`;
}

function table(headers, rows) {
  if (!rows.length) return emptyState("표시할 행이 없습니다", "현재 aggregate bundle 또는 필터 조건에 해당하는 행이 없습니다.");
  return `
    <table class="data-table">
      <thead><tr>${headers.map((header) => `<th>${escapeHtml(header.label)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows.map((row, index) => `<tr>${headers.map((header) => `<td>${header.render ? header.render(row, index) : escapeHtml(row[header.key] ?? "N/A")}</td>`).join("")}</tr>`).join("")}
      </tbody>
    </table>
  `;
}

function setText(id, value) {
  const element = byId(id);
  if (element) element.textContent = value;
}

function setSignalExample(signal) {
  const example = signalExamples[signal];
  if (!example) return;
  const hero = document.querySelector(".vitals-hero");
  hero.dataset.signal = signal;
  setText("signalStateTitle", example.title);
  setText("signalStateCopy", example.copy);
  setText("signalStateIcon", example.icon);
  all(".ecg-overlay .ecg-main, .ecg-overlay .ecg-glow").forEach((path) => path.setAttribute("d", example.path));
  all("[data-signal-state]").forEach((button) => {
    const active = button.dataset.signalState === signal;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function setMotionPaused(paused) {
  const hero = document.querySelector(".vitals-hero");
  const button = byId("motionToggle");
  hero.classList.toggle("is-paused", paused);
  button.setAttribute("aria-pressed", String(paused));
  button.setAttribute("aria-label", paused ? "심장과 심전도 움직임 재생하기" : "심장과 심전도 움직임 멈추기");
  button.replaceChildren(document.createTextNode(paused ? "▶ " : "Ⅱ "), Object.assign(document.createElement("span"), { textContent: paused ? "재생하기" : "멈추기" }));
}

function setupChrome() {
  all("[data-signal-state]").forEach((button) => button.addEventListener("click", () => setSignalExample(button.dataset.signalState)));
  const motionButton = byId("motionToggle");
  motionButton.addEventListener("click", () => setMotionPaused(motionButton.getAttribute("aria-pressed") !== "true"));
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    setMotionPaused(true);
    motionButton.disabled = true;
    motionButton.setAttribute("aria-label", "기기 설정에 따라 움직임이 꺼져 있습니다");
  }
  const menuButton = byId("menuToggle");
  menuButton.addEventListener("click", () => {
    const open = menuButton.getAttribute("aria-expanded") !== "true";
    menuButton.setAttribute("aria-expanded", String(open));
    menuButton.setAttribute("aria-label", open ? "메뉴 닫기" : "메뉴 열기");
    byId("mainNav").classList.toggle("open", open);
  });
  all(".main-nav a").forEach((link) => link.addEventListener("click", () => {
    byId("mainNav").classList.remove("open");
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "메뉴 열기");
  }));
}

function renderHeroMetrics() {
  const shock = shockMetric();
  const loss = lossMetric();
  const quality = state.modeling?.quality;
  const captureNumber = numberOrNull(loss?.top10_loss_capture);
  const capturePct = captureNumber === null ? "N/A" : formatValue(captureNumber, "percentNumber");
  const qualityText = quality ? `${formatValue(quality.passed, "integer")} passed / ${formatValue(quality.failed, "integer")} failed` : "N/A";
  setText("heroShockF1", formatValue(shock?.f1));
  setText("heroCapture10", captureNumber === null ? "N/A" : `${capturePct}%`);
  setText("heroQuality", qualityText);
  setText("bandShockF1", formatValue(shock?.f1));
  setText("bandCapture10", capturePct);
  setText("bandQualityPassed", quality ? formatValue(quality.passed, "integer") : "N/A");
  setText("bandQualityFailed", quality ? formatValue(quality.failed, "integer") : "N/A");
}

function renderStages() {
  const tabs = byId("stageTabs");
  tabs.innerHTML = stageBlueprints.map((stage, index) => `
    <button id="stage-${index}" class="stage${index === 0 ? " active" : ""}" role="tab" aria-selected="${index === 0}" aria-controls="stagePanel" tabindex="${index === 0 ? "0" : "-1"}" data-stage="${index}" type="button">
      <span>${String(index + 1).padStart(2, "0")} <i aria-hidden="true">${["↘", "◷", "≋", "↗", "⊕"][index]}</i></span>
      <strong>${escapeHtml(["Shock Pulse", "Recovery Clock", "Climate Scar", "Loss Priority", "Triage Score"][index])}</strong>
      <small>${escapeHtml(["기후 충격 맥박", "회복 시계", "기후 흉터", "손실 우선순위", "지원 진단 점수"][index])}</small>
    </button>
  `).join("");
  all(".stage").forEach((button, index) => {
    button.addEventListener("click", () => showStage(index));
    button.addEventListener("keydown", (event) => {
      let next = index;
      if (event.key === "ArrowRight") next = (index + 1) % stageBlueprints.length;
      else if (event.key === "ArrowLeft") next = (index + stageBlueprints.length - 1) % stageBlueprints.length;
      else if (event.key === "Home") next = 0;
      else if (event.key === "End") next = stageBlueprints.length - 1;
      else return;
      event.preventDefault();
      showStage(next, true);
    });
  });
  showStage(0);
}

function showStage(index, focus = false) {
  const stage = stageBlueprints[index];
  all(".stage").forEach((button, buttonIndex) => {
    const active = buttonIndex === index;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  byId("stagePanel").setAttribute("aria-labelledby", `stage-${index}`);
  setText("stageTag", stage.tag);
  setText("stageTitle", stage.title);
  setText("stageDescription", stage.description);
  setText("stageStatLabel", stage.statLabel);
  setText("stageStat", metricTextForStage(stage.key));
  setText("stageCaution", stage.caution);
  setText("diagramCaption", stage.caption);
  setText("diagramLabel", stage.label);
  byId("stagePath").setAttribute("d", stage.path);
  byId("diagramHighlight").setAttribute("x", stage.x);
  byId("diagramHighlight").setAttribute("width", stage.width);
  byId("diagramPoint").setAttribute("cx", stage.point[0]);
  byId("diagramPoint").setAttribute("cy", stage.point[1]);
  if (focus) byId(`stage-${index}`).focus();
}

function renderEvidence() {
  const shockModel = findModel("Shock Pulse");
  const shock = shockMetric();
  const loss = lossMetric();
  const weatherModel = findModel("Weather-conditioned Shock");
  const weather = weatherMetric();
  const recoveryModel = findModel("Recovery Clock");
  const recovery = recoveryMetric();
  const f1Width = Math.max(0, Math.min(100, (numberOrNull(shock?.f1) || 0) * 100));
  const captureWidth = Math.max(0, Math.min(100, (numberOrNull(loss?.top10_loss_capture) || 0) * 100));

  byId("shockCard").innerHTML = `
    <div class="card-heading"><h3>Shock Pulse</h3><span class="tag">핵심 모델</span></div>
    <p>큰 음의 매출 편차를 감지하는 모델입니다. Champion: ${escapeHtml(shockModel?.champion_algorithm || "N/A")}</p>
    <div class="f1-display"><span>TEST F1</span><strong>${escapeHtml(formatValue(shock?.f1))}</strong><div class="scale"><span style="width:${f1Width}%"></span></div><div class="scale-labels"><span>0.0</span><span>1.0</span></div></div>
    <dl class="model-stats"><div><dt>ROC-AUC</dt><dd>${escapeHtml(formatValue(shock?.roc_auc))}</dd></div><div><dt>PR-AUC</dt><dd>${escapeHtml(formatValue(shock?.pr_auc))}</dd></div><div><dt>Recall</dt><dd>${escapeHtml(formatValue(shock?.recall, "percent"))}</dd></div></dl>
    <details><summary>지표를 어떻게 읽나요?</summary><p>F1은 정밀도와 재현율의 균형을, ROC-AUC는 양·음성 구분 순위 성능을 나타냅니다. 불균형 타깃에서는 PR-AUC도 함께 봐야 합니다.</p></details>
  `;

  byId("lossCard").innerHTML = `
    <div class="card-heading"><h3>Loss Priority</h3><span class="tag">순위화 계층</span></div>
    <p>검토 범위를 줄여도 주요 modeled loss 신호가 먼저 모이도록 설계된 ranking layer입니다.</p>
    <div class="capture-controls"><span>상위 10% 후보군</span><div class="segmented" aria-label="고정 평가 비율"><button type="button" class="active" aria-pressed="true">10%</button></div></div>
    <div class="capture-numbers"><div><span>모델링 손실 포착 비중</span><strong>${escapeHtml(formatValue(loss?.top10_loss_capture, "percent"))}</strong></div><div><span>무작위 대비 집중도</span><strong>${escapeHtml(formatValue(loss?.top10_lift))}<small>×</small></strong></div></div>
    <div class="comparison-chart" role="img" aria-label="상위 10% 후보군 손실 포착 비중"><div><span>FlowShock</span><div class="bar-track"><i style="width:${captureWidth}%"></i></div><strong>${escapeHtml(formatValue(loss?.top10_loss_capture, "percent"))}</strong></div><div><span>무작위 기준</span><div class="bar-track"><i class="random" style="width:10%"></i></div><strong>10.0%</strong></div></div>
    <p class="chart-note">무작위 기준은 선택 비율에 해당하는 기대값입니다. 손실은 감사된 실제 피해액이 아닌 baseline-relative modeled loss입니다.</p>
  `;

  byId("weatherStrip").innerHTML = `
    <div><span class="tiny">WEATHER-CONDITIONED SHOCK</span><h3>기상 조건부 충격 모델</h3></div>
    <div><span>F1</span><strong>${escapeHtml(formatValue(weather?.f1))}</strong></div>
    <div><span>Top10 Recall</span><strong>${escapeHtml(formatValue(weather?.top10_recall, "percent"))}</strong></div>
    <p>${escapeHtml(weatherModel?.champion_algorithm || "N/A")} champion · Recovery Clock F1 ${escapeHtml(formatValue(recovery?.f1))} (${escapeHtml(recoveryModel?.champion_algorithm || "N/A")})</p>
  `;

  const rows = modelList().flatMap((model) => (Array.isArray(model.metrics) ? model.metrics : [])
    .filter((metric) => metric.split === "test")
    .map((metric) => ({ ...metric, model_group: model.model_name, champion_algorithm: model.champion_algorithm })));
  byId("performanceTable").innerHTML = `<h3>Model performance panel</h3><p>현재 modeling bundle의 test split 지표입니다.</p>${table([
    { label: "Model", render: (row) => escapeHtml(row.model_name || row.model_group) },
    { label: "Target", key: "target" },
    { label: "F1", render: (row) => escapeHtml(formatValue(row.f1)) },
    { label: "PR-AUC", render: (row) => escapeHtml(formatValue(row.pr_auc)) },
    { label: "ROC-AUC", render: (row) => escapeHtml(formatValue(row.roc_auc)) },
    { label: "Recall", render: (row) => escapeHtml(formatValue(row.recall, "percent")) },
    { label: "Top10 Recall", render: (row) => escapeHtml(formatValue(row.top10_recall, "percent")) },
    { label: "Top10 Lift", render: (row) => escapeHtml(hasValue(row.top10_lift) ? `${formatValue(row.top10_lift)}x` : "N/A") }
  ], rows)}`;
}

function boardRows() {
  if (state.boardMode === "loss") {
    return (state.modeling?.loss_priority_top20 || []).map((row, index) => ({
      id: `loss-${index}`,
      rank: row.priority_rank ?? index + 1,
      merchant_region: row.merchant_region,
      industry: row.industry,
      primary: row.predicted_total_loss_priority,
      secondary: row.observed_total_estimated_loss,
      shock: row.mean_predicted_shock_pulse_risk,
      recovery: null,
      scar: null,
      interpretation: row.ecg_interpretation,
      mode: "loss"
    }));
  }
  return (state.modeling?.triage_top20 || []).map((row, index) => ({
    id: `triage-${index}`,
    rank: index + 1,
    merchant_region: row.merchant_region,
    industry: row.industry,
    primary: row.climate_ecg_triage_score,
    secondary: row.observed_event_count,
    shock: row.predicted_shock_pulse_risk,
    recovery: row.predicted_recovery_clock_risk,
    scar: row.climate_scar_score,
    interpretation: row.ecg_interpretation,
    mode: "triage"
  }));
}

function filteredBoardRows() {
  const term = byId("candidateSearch").value.trim().toLocaleLowerCase("ko-KR");
  const industry = byId("industryFilter").value;
  return boardRows().filter((row) => {
    const industryMatch = industry === "all" || row.industry === industry;
    const termMatch = `${row.merchant_region || ""} ${row.industry || ""}`.toLocaleLowerCase("ko-KR").includes(term);
    return industryMatch && termMatch;
  });
}

function updateIndustryFilter() {
  const select = byId("industryFilter");
  const current = select.value;
  const industries = [...new Set(boardRows().map((row) => row.industry).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "ko-KR"));
  select.innerHTML = `<option value="all">전체 업종</option>${industries.map((industry) => `<option value="${escapeHtml(industry)}">${escapeHtml(industry)}</option>`).join("")}`;
  select.value = industries.includes(current) ? current : "all";
}

function renderBoard() {
  updateIndustryFilter();
  const rows = filteredBoardRows();
  const visible = rows.slice(0, 10);
  if (!visible.some((row) => row.id === state.selectedId)) state.selectedId = visible[0]?.id || null;
  const lossMode = state.boardMode === "loss";
  byId("candidateHead").innerHTML = `<tr><th scope="col">순위 / 지역 · 업종</th><th scope="col">${lossMode ? "Predicted Priority" : "Triage Score"}</th><th scope="col">${lossMode ? "Observed Est. Loss" : "Event Count"}</th><th scope="col">Shock Risk</th></tr>`;
  byId("candidateRows").innerHTML = visible.map((row) => {
    const active = row.id === state.selectedId;
    const primaryValue = lossMode ? formatValue(row.primary, "compact") : formatValue(row.primary, "score");
    const barValue = Math.max(0, Math.min(100, lossMode ? (visible[0]?.primary ? (Number(row.primary) / Number(visible[0].primary)) * 100 : 0) : Number(row.primary) || 0));
    const secondary = lossMode ? formatValue(row.secondary, "compact") : formatValue(row.secondary, "integer");
    return `
      <tr class="${active ? "selected" : ""}">
        <td><button class="candidate-select" type="button" data-candidate-id="${escapeHtml(row.id)}" aria-pressed="${active}" aria-label="${escapeHtml(row.rank)}위 ${escapeHtml(row.merchant_region)} ${escapeHtml(row.industry)} 상세 보기"><span class="candidate-rank">${escapeHtml(String(row.rank).padStart(2, "0"))}</span><span><strong>${escapeHtml(row.merchant_region || "N/A")}</strong><small>${escapeHtml(row.industry || "N/A")}</small></span></button></td>
        <td>${escapeHtml(primaryValue)}<span class="mini-bar"><i style="width:${barValue}%"></i></span></td>
        <td>${escapeHtml(secondary)}</td>
        <td>${escapeHtml(formatValue(row.shock, "percent"))}</td>
      </tr>
    `;
  }).join("");
  byId("candidateCount").textContent = `${formatValue(rows.length, "integer")}개 후보${rows.length > 10 ? " · 상위 10개 표시" : ""}`;
  const empty = byId("emptyState");
  empty.hidden = visible.length > 0;
  document.querySelector(".candidate-table").hidden = visible.length === 0;
  all(".candidate-select").forEach((button) => button.addEventListener("click", () => {
    state.selectedId = button.dataset.candidateId;
    renderBoard();
  }));
  renderCandidateDetail(visible.find((row) => row.id === state.selectedId));
}

function renderCandidateDetail(row) {
  const detail = byId("candidateDetail");
  if (!row) {
    detail.innerHTML = emptyState("선택된 후보가 없습니다", "검색 조건을 조정하거나 다른 보드 모드를 선택하세요.");
    return;
  }
  const lossMode = row.mode === "loss";
  detail.innerHTML = `
    <div class="detail-head"><span class="tiny">CANDIDATE PROFILE</span><span class="example-badge">실제 aggregate 결과</span></div>
    <h4>${escapeHtml(row.merchant_region || "N/A")}</h4>
    <p>${escapeHtml(row.industry || "N/A")}</p>
    <div class="triage-number"><span>${lossMode ? "Predicted Priority" : "Triage Score"}</span><strong>${escapeHtml(lossMode ? formatValue(row.primary, "compact") : formatValue(row.primary, "score"))}</strong></div>
    <div class="detail-signals">
      <div class="detail-signal"><span>Shock risk</span><strong>${escapeHtml(formatValue(row.shock, "percent"))}</strong></div>
      <div class="detail-signal"><span>Recovery risk</span><strong>${escapeHtml(lossMode ? "N/A" : formatValue(row.recovery, "percent"))}</strong></div>
      <div class="detail-signal"><span>Climate Scar</span><strong>${escapeHtml(lossMode ? "N/A" : formatValue(row.scar, "score"))}</strong></div>
    </div>
    <p class="chart-note">${escapeHtml(row.interpretation || "predictive aggregate decision support, not causal or final policy decision")}</p>
  `;
}

function setBoardMode(mode) {
  state.boardMode = mode;
  state.selectedId = null;
  byId("candidateSearch").value = "";
  const lossMode = mode === "loss";
  byId("modeTriage").classList.toggle("active", !lossMode);
  byId("modeLoss").classList.toggle("active", lossMode);
  byId("modeTriage").setAttribute("aria-pressed", String(!lossMode));
  byId("modeLoss").setAttribute("aria-pressed", String(lossMode));
  setText("dataBadge", lossMode ? "loss_priority_top20" : "triage_top20");
  setText("boardNotice", lossMode ? "Loss Priority는 baseline-relative modeled loss 기준의 지원 검토 순위입니다. 감사된 피해액이나 자동 지급 대상이 아닙니다." : "Triage는 Shock risk, Recovery risk, Climate Scar를 결합한 검토 보조 신호입니다. 실제 지원 결정은 사람이 현장 맥락과 함께 검토해야 합니다.");
  renderBoard();
}

function renderScarAndRegional() {
  const regions = state.analysis?.regional_dashboard || [];
  const scars = state.analysis?.vulnerability_matrix || [];
  byId("regionalTable").innerHTML = `<h3>Regional dashboard</h3><p>analysis.regional_dashboard 집계입니다.</p>${table([
    { label: "Region", key: "merchant_region" },
    { label: "Days", render: (row) => escapeHtml(formatValue(row.days, "integer")) },
    { label: "Industries", render: (row) => escapeHtml(formatValue(row.industries, "integer")) },
    { label: "Rain Rows", render: (row) => escapeHtml(formatValue(row.rain_days, "integer")) },
    { label: "Heavy20 Rows", render: (row) => escapeHtml(formatValue(row.heavy20_days, "integer")) },
    { label: "Total Sales", render: (row) => escapeHtml(formatValue(row.total_sales_amount, "compact")) }
  ], regions.slice(0, 8))}`;
  byId("scarTable").innerHTML = `<h3>Climate Scar candidates</h3><p>analysis.vulnerability_matrix 상위 후보입니다. 인과적 피해 추정이 아닙니다.</p>${table([
    { label: "Rank", render: (_row, index) => rankPill(index + 1) },
    { label: "Region", key: "merchant_region" },
    { label: "Industry", key: "industry" },
    { label: "Scar Score", render: (row) => escapeHtml(formatValue(row.support_priority_score, "score")) },
    { label: "Initial Shock", render: (row) => escapeHtml(formatValue(row.median_initial_shock_pp, "percentPoint")) },
    { label: "Net Damage", render: (row) => escapeHtml(formatValue(row.median_net_damage_pp, "percentPoint")) },
    { label: "Persistent Share", render: (row) => escapeHtml(formatValue(row.persistent_damage_share, "percent")) },
    { label: "Reliability", render: (row) => statusPill(row.reliability_flag) }
  ], scars.slice(0, 8))}`;
}

function renderGuardrails() {
  const modelingQuality = state.modeling?.quality;
  const analysisQuality = state.analysis?.quality;
  const cards = [
    ["01", "인과로 읽지 않습니다", "이 결과는 비인과적 예측·순위화 신호입니다. 기상 때문에 매출이 감소했다고 단정하지 않습니다."],
    ["02", "회고적 평가입니다", "현재 웹은 same-day 또는 retrospective evaluation artifact입니다. 실시간 운영 결과가 아닙니다."],
    ["03", "사전 예측 경계", "Prospective use에는 예보 기상 입력, 별도 검증, 배포 후 모니터링이 필요합니다."],
    ["04", "손실 해석", "Loss Priority의 손실은 baseline-relative modeled loss이며, 감사된 실제 피해액이 아닙니다."],
    ["05", "사람의 최종 검토", "후보 점수는 의사결정 보조 신호입니다. 최종 정책·지원 결정은 사람이 현장 맥락과 함께 판단해야 합니다."],
    ["06", "Aggregate-only runtime", "런타임은 정적 asset과 public aggregate bundle 2개만 fetch합니다. raw CSV나 분석 파이프라인 파일을 읽지 않습니다."],
    ["07", "품질 체크", `Modeling quality: ${modelingQuality ? `${modelingQuality.passed} passed / ${modelingQuality.failed} failed` : "N/A"}. Analysis quality: ${analysisQuality ? `${analysisQuality.passed} passed / ${analysisQuality.failed} failed` : "N/A"}.`]
  ];
  byId("guardrailCards").innerHTML = cards.map(([number, title, text]) => `<article><span>${escapeHtml(number)}</span><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></div></article>`).join("");
}

function setupBoardEvents() {
  byId("modeTriage").addEventListener("click", () => setBoardMode("triage"));
  byId("modeLoss").addEventListener("click", () => setBoardMode("loss"));
  byId("industryFilter").addEventListener("change", renderBoard);
  byId("candidateSearch").addEventListener("input", renderBoard);
}

function renderAll() {
  renderHeroMetrics();
  renderStages();
  renderEvidence();
  setBoardMode("triage");
  renderScarAndRegional();
  renderGuardrails();
  setText("loadStatus", "현재 aggregate analysis/modeling bundle을 불러왔습니다.");
}

function renderFatal(error) {
  setText("loadStatus", "aggregate bundle을 불러오지 못했습니다.");
  const message = `Unable to load copied aggregate bundles from web/public/data. Run npm start from web/ and open http://localhost:4173. Detail: ${error.message}`;
  const main = byId("main");
  main.innerHTML = `<section class="section wrap">${emptyState("번들 로딩 실패", message)}</section>`;
}

async function loadBundles() {
  const [analysisResponse, modelingResponse] = await Promise.all([
    fetch(DATA_PATHS.analysis, { cache: "no-cache" }),
    fetch(DATA_PATHS.modeling, { cache: "no-cache" })
  ]);
  if (!analysisResponse.ok) throw new Error(`${DATA_PATHS.analysis} returned ${analysisResponse.status}`);
  if (!modelingResponse.ok) throw new Error(`${DATA_PATHS.modeling} returned ${modelingResponse.status}`);
  const [analysis, modeling] = await Promise.all([analysisResponse.json(), modelingResponse.json()]);
  if (!analysis || typeof analysis !== "object" || !modeling || typeof modeling !== "object") throw new Error("Invalid aggregate bundle shape");
  state.analysis = analysis;
  state.modeling = modeling;
  renderAll();
}

setupChrome();
setupBoardEvents();
setSignalExample("risk");
loadBundles().catch(renderFatal);
