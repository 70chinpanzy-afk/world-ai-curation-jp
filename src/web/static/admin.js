const cardsRoot = document.getElementById("cards");
const template = document.getElementById("adminCardTemplate");
const statusText = document.getElementById("statusText");
const auditStatus = document.getElementById("auditStatus");
const auditActionSummary = document.getElementById("auditActionSummary");
const auditTrendRoot = document.getElementById("auditTrend");
const auditLogsRoot = document.getElementById("auditLogs");
const auditActionSelect = document.getElementById("auditAction");
const auditCardIdInput = document.getElementById("auditCardId");
const auditActorInput = document.getElementById("auditActor");
const auditFromTsInput = document.getElementById("auditFromTs");
const auditToTsInput = document.getElementById("auditToTs");
const auditRangePresetSelect = document.getElementById("auditRangePreset");
const auditLimitSelect = document.getElementById("auditLimit");
const auditClearRangeButton = document.getElementById("auditClearRange");
const auditReloadButton = document.getElementById("auditReload");
const auditDownloadButton = document.getElementById("auditDownload");
const auditTrendDownloadButton = document.getElementById("auditTrendDownload");
const auditWeeklyReportButton = document.getElementById("auditWeeklyReport");
const auditWeeklyMdButton = document.getElementById("auditWeeklyMd");
const auditWeeklySaveButton = document.getElementById("auditWeeklySave");
const auditWeeklyPublishButton = document.getElementById("auditWeeklyPublish");
const auditWeeklyHistoryButton = document.getElementById("auditWeeklyHistory");
const auditWeeklyHistoryReloadButton = document.getElementById("auditWeeklyHistoryReload");
const auditWeeklyHistoryCsvButton = document.getElementById("auditWeeklyHistoryCsv");
const auditWeeklyHistoryClearButton = document.getElementById("auditWeeklyHistoryClear");
const auditWeeklyHistoryCleanupButton = document.getElementById("auditWeeklyHistoryCleanup");
const auditCopyLinkButton = document.getElementById("auditCopyLink");
const auditPrevButton = document.getElementById("auditPrev");
const auditNextButton = document.getElementById("auditNext");
const auditPageInfo = document.getElementById("auditPageInfo");
const auditTrendScopeSelect = document.getElementById("auditTrendScope");
const auditTrendDaysSelect = document.getElementById("auditTrendDays");
const auditTopLimitSelect = document.getElementById("auditTopLimit");
const auditHistorySearchInput = document.getElementById("auditHistorySearch");
const auditHistoryLimitSelect = document.getElementById("auditHistoryLimit");
const auditHistorySortSelect = document.getElementById("auditHistorySort");
const auditHistoryKeepLatestSelect = document.getElementById("auditHistoryKeepLatest");
const auditWeeklyBriefRoot = document.getElementById("auditWeeklyBrief");
const auditWeeklyHistoryRoot = document.getElementById("auditWeeklyHistoryText");

const audienceSelect = document.getElementById("audience");
const sectionSelect = document.getElementById("section");
const statusSelect = document.getElementById("status");
const difficultySelect = document.getElementById("difficulty");
const reloadButton = document.getElementById("reload");
const AUDIT_FILTER_STATE_KEY = "world_ai_curation_admin_audit_filters_v2";
let auditOffset = 0;
auditPrevButton.disabled = true;
auditNextButton.disabled = true;

function formatDate(iso) {
  if (!iso) return "n/a";
  return new Date(iso).toLocaleString();
}

function clearCards() {
  while (cardsRoot.firstChild) {
    cardsRoot.removeChild(cardsRoot.firstChild);
  }
}

function clearAuditLogs() {
  while (auditLogsRoot.firstChild) {
    auditLogsRoot.removeChild(auditLogsRoot.firstChild);
  }
}

function difficultyClass(level) {
  if (level === "初級" || level === "初級（検証前提）") return "difficulty-beginner";
  if (level === "中級") return "difficulty-intermediate";
  if (level === "上級寄り") return "difficulty-advanced";
  return "difficulty-unknown";
}

function formatDetails(details) {
  if (!details || typeof details !== "object") return "{}";
  const text = JSON.stringify(details, null, 2);
  return text.length > 500 ? `${text.slice(0, 500)}\n...` : text;
}

function toIsoOrEmpty(datetimeLocalText) {
  if (!datetimeLocalText) return "";
  const dt = new Date(datetimeLocalText);
  if (Number.isNaN(dt.getTime())) return "";
  return dt.toISOString();
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

function toDatetimeLocalValue(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(
    date.getMinutes()
  )}`;
}

function fromIsoToDatetimeLocalValue(isoText) {
  if (!isoText) return "";
  const parsed = new Date(isoText);
  if (Number.isNaN(parsed.getTime())) return "";
  return toDatetimeLocalValue(parsed);
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0, 0, 0);
}

function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1, 0, 0, 0, 0);
}

function endOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0, 23, 59, 0, 0);
}

function applyRangePreset(preset) {
  const now = new Date();

  if (preset === "last24h") {
    const from = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    auditFromTsInput.value = toDatetimeLocalValue(from);
    auditToTsInput.value = toDatetimeLocalValue(now);
    return;
  }

  if (preset === "today") {
    auditFromTsInput.value = toDatetimeLocalValue(startOfDay(now));
    auditToTsInput.value = toDatetimeLocalValue(now);
    return;
  }

  if (preset === "last7") {
    const from = startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 6));
    auditFromTsInput.value = toDatetimeLocalValue(from);
    auditToTsInput.value = toDatetimeLocalValue(now);
    return;
  }

  if (preset === "thisMonth") {
    auditFromTsInput.value = toDatetimeLocalValue(startOfMonth(now));
    auditToTsInput.value = toDatetimeLocalValue(now);
    return;
  }

  if (preset === "lastMonth") {
    const base = new Date(now.getFullYear(), now.getMonth() - 1, 1, 0, 0, 0, 0);
    auditFromTsInput.value = toDatetimeLocalValue(startOfMonth(base));
    auditToTsInput.value = toDatetimeLocalValue(endOfMonth(base));
  }
}

function getRangeLabel() {
  const preset = auditRangePresetSelect.value;
  if (preset === "last24h") return "過去24時間";
  if (preset === "today") return "今日";
  if (preset === "last7") return "過去7日";
  if (preset === "thisMonth") return "今月";
  if (preset === "lastMonth") return "先月";

  const fromText = (auditFromTsInput.value || "").trim();
  const toText = (auditToTsInput.value || "").trim();
  if (fromText && toText) return `${fromText} 〜 ${toText}`;
  if (fromText) return `${fromText} 以降`;
  if (toText) return `${toText} 以前`;
  return "";
}

function setSelectIfPresent(selectEl, value) {
  if (!value) return;
  const exists = Array.from(selectEl.options || []).some((opt) => opt.value === value);
  if (exists) selectEl.value = value;
}

function saveAuditFilterState() {
  const payload = {
    action: auditActionSelect.value || "",
    card_id: (auditCardIdInput.value || "").trim(),
    actor: (auditActorInput.value || "").trim(),
    from_ts_local: auditFromTsInput.value || "",
    to_ts_local: auditToTsInput.value || "",
    range_preset: auditRangePresetSelect.value || "custom",
    limit: auditLimitSelect.value || "50",
    trend_scope: auditTrendScopeSelect.value || "page",
    trend_days: auditTrendDaysSelect.value || "7",
    top_limit: auditTopLimitSelect.value || "5",
    history_q: (auditHistorySearchInput.value || "").trim(),
    history_limit: auditHistoryLimitSelect.value || "20",
    history_sort: auditHistorySortSelect.value || "desc",
    history_keep_latest: auditHistoryKeepLatestSelect.value || "0",
  };
  try {
    window.localStorage.setItem(AUDIT_FILTER_STATE_KEY, JSON.stringify(payload));
  } catch (error) {
    // Ignore storage errors in private mode or restricted browsers.
  }
}

function restoreAuditFilterState() {
  try {
    const raw = window.localStorage.getItem(AUDIT_FILTER_STATE_KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved !== "object") return;

    setSelectIfPresent(auditActionSelect, saved.action);
    setSelectIfPresent(auditRangePresetSelect, saved.range_preset);
    setSelectIfPresent(auditLimitSelect, saved.limit);
    setSelectIfPresent(auditTrendScopeSelect, saved.trend_scope);
    setSelectIfPresent(auditTrendDaysSelect, saved.trend_days);
    setSelectIfPresent(auditTopLimitSelect, saved.top_limit);
    setSelectIfPresent(auditHistoryLimitSelect, saved.history_limit);
    setSelectIfPresent(auditHistorySortSelect, saved.history_sort);
    setSelectIfPresent(auditHistoryKeepLatestSelect, saved.history_keep_latest);

    if (typeof saved.card_id === "string") auditCardIdInput.value = saved.card_id;
    if (typeof saved.actor === "string") auditActorInput.value = saved.actor;
    if (typeof saved.from_ts_local === "string") auditFromTsInput.value = saved.from_ts_local;
    if (typeof saved.to_ts_local === "string") auditToTsInput.value = saved.to_ts_local;
    if (typeof saved.history_q === "string") auditHistorySearchInput.value = saved.history_q;
  } catch (error) {
    // Ignore malformed state.
  }
}

function applyAuditFiltersFromUrl() {
  const params = new URLSearchParams(window.location.search || "");
  if (!params.toString()) return;

  setSelectIfPresent(auditActionSelect, params.get("action"));
  setSelectIfPresent(auditLimitSelect, params.get("limit"));
  setSelectIfPresent(auditTrendScopeSelect, params.get("trend_scope"));
  setSelectIfPresent(auditTrendDaysSelect, params.get("trend_days"));
  setSelectIfPresent(auditTopLimitSelect, params.get("top_limit"));
  setSelectIfPresent(auditHistoryLimitSelect, params.get("history_limit"));
  setSelectIfPresent(auditHistorySortSelect, params.get("history_sort"));
  setSelectIfPresent(auditHistoryKeepLatestSelect, params.get("history_keep_latest"));

  const cardId = params.get("card_id");
  const actor = params.get("actor");
  const fromTs = params.get("from_ts");
  const toTs = params.get("to_ts");
  if (cardId) auditCardIdInput.value = cardId;
  if (actor) auditActorInput.value = actor;
  if (fromTs) auditFromTsInput.value = fromIsoToDatetimeLocalValue(fromTs);
  if (toTs) auditToTsInput.value = fromIsoToDatetimeLocalValue(toTs);
  if (params.get("history_q")) auditHistorySearchInput.value = String(params.get("history_q"));

  const offset = Number(params.get("offset") || "0");
  if (Number.isFinite(offset) && offset >= 0) {
    auditOffset = Math.floor(offset);
  }

  if (fromTs || toTs) {
    auditRangePresetSelect.value = "custom";
  }
}

function auditFilterUrl(includeOffset = false) {
  const params = buildAuditParams({ includeOffset });
  params.set("trend_scope", auditTrendScopeSelect.value || "page");
  params.set("trend_days", auditTrendDaysSelect.value || "7");
  params.set("top_limit", auditTopLimitSelect.value || "5");
  params.set("history_q", (auditHistorySearchInput.value || "").trim());
  params.set("history_limit", auditHistoryLimitSelect.value || "20");
  params.set("history_sort", auditHistorySortSelect.value || "desc");
  params.set("history_keep_latest", auditHistoryKeepLatestSelect.value || "0");
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
}

function normalizeActionClass(action) {
  return String(action || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, "_");
}

function actionDisplay(action) {
  if (action === "status_update") return "status_update (Status)";
  if (action === "pin_update") return "pin_update (Pin)";
  return String(action || "unknown");
}

function actionShortLabel(action) {
  if (action === "status_update") return "Status";
  if (action === "pin_update") return "Pin";
  return String(action || "unknown");
}

function countActions(logs) {
  const counts = {};
  if (!Array.isArray(logs)) return counts;
  logs.forEach((log) => {
    const key = String(log.action || "unknown");
    counts[key] = (counts[key] || 0) + 1;
  });
  return counts;
}

function renderActionSummary(counts, scopeLabel = "") {
  const total = Object.values(counts || {}).reduce((sum, n) => sum + Number(n || 0), 0);
  if (!total) {
    auditActionSummary.textContent = "Action summary: 0 rows";
    return;
  }

  const parts = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([action, count]) => `${actionShortLabel(action)}: ${count}`);
  const scopeText = scopeLabel ? ` | ${scopeLabel}` : "";
  auditActionSummary.textContent = `Action summary: ${parts.join(" | ")}${scopeText}`;
}

function dayKey(date) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function dayLabelFromKey(key) {
  const [year, month, day] = key.split("-");
  return `${month}/${day}`;
}

function lastNDays(n) {
  const base = startOfDay(new Date());
  const days = [];
  for (let i = n - 1; i >= 0; i -= 1) {
    const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() - i, 0, 0, 0, 0);
    days.push(dayKey(d));
  }
  return days;
}

function appendTrendMetric(container, label, value, maxValue, cssClass) {
  const metric = document.createElement("div");
  metric.className = "trend-metric";

  const name = document.createElement("span");
  name.className = "trend-label";
  name.textContent = label;

  const bar = document.createElement("div");
  bar.className = "trend-bar";

  const fill = document.createElement("div");
  fill.className = `trend-fill ${cssClass}`;
  const width = maxValue > 0 ? (value / maxValue) * 100 : 0;
  fill.style.width = `${Math.max(width, 2)}%`;

  const count = document.createElement("span");
  count.className = "trend-count";
  count.textContent = String(value);

  bar.appendChild(fill);
  metric.appendChild(name);
  metric.appendChild(bar);
  metric.appendChild(count);
  container.appendChild(metric);
}

function computeDailyFromLogs(logs, days) {
  const keys = lastNDays(days);
  const bucket = {};
  keys.forEach((k) => {
    bucket[k] = { status_update: 0, pin_update: 0, other: 0, total: 0 };
  });

  (logs || []).forEach((log) => {
    const parsed = new Date(log.timestamp || "");
    if (Number.isNaN(parsed.getTime())) return;
    const key = dayKey(parsed);
    if (!(key in bucket)) return;
    if (log.action === "status_update") {
      bucket[key].status_update += 1;
    } else if (log.action === "pin_update") {
      bucket[key].pin_update += 1;
    } else {
      bucket[key].other += 1;
    }
    bucket[key].total += 1;
  });
  return keys.map((k) => ({ day: k, ...bucket[k] }));
}

function renderTrendRows(dailyRows, titleText) {
  while (auditTrendRoot.firstChild) {
    auditTrendRoot.removeChild(auditTrendRoot.firstChild);
  }

  if (!Array.isArray(dailyRows) || !dailyRows.length) {
    auditTrendRoot.textContent = "トレンド: データなし";
    return;
  }

  let maxCount = 0;
  dailyRows.forEach((row) => {
    maxCount = Math.max(maxCount, Number(row.status_update || 0), Number(row.pin_update || 0));
  });
  maxCount = Math.max(maxCount, 1);

  const title = document.createElement("p");
  title.className = "status-row";
  title.textContent = titleText;
  auditTrendRoot.appendChild(title);

  dailyRows.forEach((rowData) => {
    const row = document.createElement("div");
    row.className = "trend-row";

    const day = document.createElement("div");
    day.className = "trend-day";
    day.textContent = dayLabelFromKey(String(rowData.day || ""));

    const metrics = document.createElement("div");
    metrics.className = "trend-metrics";
    appendTrendMetric(metrics, "Status", Number(rowData.status_update || 0), maxCount, "status");
    appendTrendMetric(metrics, "Pin", Number(rowData.pin_update || 0), maxCount, "pin");

    row.appendChild(day);
    row.appendChild(metrics);
    auditTrendRoot.appendChild(row);
  });
}

function setAuditLoadError(message) {
  auditStatus.textContent = `Load error: ${message}`;
  auditActionSummary.textContent = `Load error: ${message}`;
  auditTrendRoot.textContent = `Load error: ${message}`;
  auditWeeklyBriefRoot.textContent = `週次ブリーフ取得エラー: ${message}`;
  auditWeeklyHistoryRoot.textContent = `週次履歴取得エラー: ${message}`;
}

function renderAuditLogs(logs) {
  clearAuditLogs();

  if (!logs.length) {
    const p = document.createElement("p");
    p.textContent = "No audit logs yet.";
    auditLogsRoot.appendChild(p);
    return;
  }

  logs.forEach((log) => {
    const row = document.createElement("article");
    row.className = "audit-row";
    row.classList.add(`action-${normalizeActionClass(log.action)}`);

    const top = document.createElement("div");
    top.className = "audit-row-top";
    top.textContent = `[${formatDate(log.timestamp)}] ${log.actor} | ${actionDisplay(log.action)} | card=${log.card_id}`;

    const details = document.createElement("pre");
    details.className = "audit-details";
    details.textContent = formatDetails(log.details);

    row.appendChild(top);
    row.appendChild(details);
    auditLogsRoot.appendChild(row);
  });
}

function buildAuditParams(options = {}) {
  const { includeOffset = true } = options;
  const params = new URLSearchParams();
  params.set("limit", auditLimitSelect.value || "50");
  if (includeOffset) {
    params.set("offset", String(Math.max(auditOffset, 0)));
  }

  const action = (auditActionSelect.value || "").trim();
  const cardId = (auditCardIdInput.value || "").trim();
  const actor = (auditActorInput.value || "").trim();
  const fromTs = toIsoOrEmpty((auditFromTsInput.value || "").trim());
  const toTs = toIsoOrEmpty((auditToTsInput.value || "").trim());

  if (action) params.set("action", action);
  if (cardId) params.set("card_id", cardId);
  if (actor) params.set("actor", actor);
  if (fromTs) params.set("from_ts", fromTs);
  if (toTs) params.set("to_ts", toTs);

  return params;
}

function buildAuditStatsParams(days) {
  const params = buildAuditParams({ includeOffset: false });
  params.set("days", String(Math.max(Number(days || 7), 1)));
  params.set("top_limit", auditTopLimitSelect.value || "5");
  return params;
}

function buildHistoryParams() {
  const params = new URLSearchParams();
  params.set("limit", auditHistoryLimitSelect.value || "20");
  params.set("sort", auditHistorySortSelect.value || "desc");
  const query = (auditHistorySearchInput.value || "").trim();
  const fromTs = toIsoOrEmpty((auditFromTsInput.value || "").trim());
  const toTs = toIsoOrEmpty((auditToTsInput.value || "").trim());
  if (query) params.set("q", query);
  if (fromTs) params.set("from_ts", fromTs);
  if (toTs) params.set("to_ts", toTs);
  return params;
}

function resetAuditOffset() {
  auditOffset = 0;
}

function updateAuditPager(meta = {}) {
  const limit = Number(meta.limit || Number(auditLimitSelect.value || "50"));
  const offset = Number(meta.offset || 0);
  const returned = Number(meta.returned || 0);
  const page = Math.floor(offset / Math.max(limit, 1)) + 1;

  if (!returned) {
    auditPageInfo.textContent = `Page ${page} | no rows`;
  } else {
    const start = offset + 1;
    const end = offset + returned;
    auditPageInfo.textContent = `Page ${page} | showing ${start}-${end}`;
  }

  auditPrevButton.disabled = offset <= 0;
  auditNextButton.disabled = !meta.has_more;
}

async function saveCard(cardId, status, pinned, pinRank) {
  const statusRes = await fetch(`/api/admin/cards/${cardId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!statusRes.ok) throw new Error(`status update failed: ${statusRes.status}`);

  const pinRes = await fetch(`/api/admin/cards/${cardId}/pin`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pinned, pin_rank: pinRank }),
  });
  if (!pinRes.ok) throw new Error(`pin update failed: ${pinRes.status}`);
}

async function loadAuditLogs() {
  const params = buildAuditParams();
  const response = await fetch(`/api/admin/audit?${params.toString()}`);
  if (!response.ok) throw new Error(`audit load failed: ${response.status}`);

  const data = await response.json();
  auditOffset = Number(data.offset || 0);
  const activeFilters = [];
  if (params.get("action")) activeFilters.push(`action=${params.get("action")}`);
  if (params.get("card_id")) activeFilters.push(`card_id=${params.get("card_id")}`);
  if (params.get("actor")) activeFilters.push(`actor=${params.get("actor")}`);
  if (params.get("from_ts")) activeFilters.push(`from=${params.get("from_ts")}`);
  if (params.get("to_ts")) activeFilters.push(`to=${params.get("to_ts")}`);
  const filterText = activeFilters.length ? ` | filters: ${activeFilters.join(", ")}` : "";
  const rangeLabel = getRangeLabel();
  const rangeText = rangeLabel ? ` | 期間: ${rangeLabel}` : "";
  const totalFiltered = Number(data.total_filtered || data.returned || 0);
  auditStatus.textContent = `Audit rows: ${data.returned}/${totalFiltered}${filterText}${rangeText}`;
  updateAuditPager(data);
  const logs = data.logs || [];
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const trendScope = auditTrendScopeSelect.value || "page";

  if (trendScope === "filtered") {
    try {
      const statsRes = await fetch(`/api/admin/audit/stats?${buildAuditStatsParams(trendDays).toString()}`);
      if (!statsRes.ok) throw new Error(`audit stats failed: ${statsRes.status}`);
      const stats = await statsRes.json();
      renderActionSummary(stats.action_counts || {}, `Filtered All (${stats.total_filtered || 0})`);
      renderTrendRows(stats.daily || [], `直近${trendDays}日トレンド（フィルタ全件）`);
    } catch (error) {
      const pageCounts = countActions(logs);
      renderActionSummary(pageCounts, "Current Page (stats fallback)");
      renderTrendRows(computeDailyFromLogs(logs, trendDays), `直近${trendDays}日トレンド（現在の表示ページ）`);
    }
  } else {
    const pageCounts = countActions(logs);
    renderActionSummary(pageCounts, "Current Page");
    renderTrendRows(computeDailyFromLogs(logs, trendDays), `直近${trendDays}日トレンド（現在の表示ページ）`);
  }

  renderAuditLogs(logs);
  try {
    await loadAuditWeeklyBrief();
  } catch (error) {
    auditWeeklyBriefRoot.textContent = `週次ブリーフ取得失敗: ${error.message}`;
  }
  try {
    await loadWeeklyHistory();
  } catch (error) {
    auditWeeklyHistoryRoot.textContent = `週次履歴取得失敗: ${error.message}`;
  }
  saveAuditFilterState();
}

function downloadAuditCsv() {
  const params = buildAuditParams({ includeOffset: false });
  window.location.href = `/api/admin/audit.csv?${params.toString()}`;
}

function downloadAuditTrendCsv() {
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const params = buildAuditStatsParams(trendDays);
  window.location.href = `/api/admin/audit/trend.csv?${params.toString()}`;
}

function downloadAuditWeeklyMd() {
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const params = buildAuditStatsParams(trendDays);
  window.location.href = `/api/admin/audit/weekly-report.md?${params.toString()}`;
}

function renderWeeklyBrief(report) {
  if (!report || typeof report !== "object") {
    auditWeeklyBriefRoot.textContent = "週次ブリーフ: データなし";
    return;
  }

  const total = Number(report.total_filtered || 0);
  const days = Number(report.days || 7);
  const generated = formatDate(report.generated_at);
  const highlights = Array.isArray(report.highlights) ? report.highlights : [];
  const playbook = Array.isArray(report.playbook_for_vibe_coders) ? report.playbook_for_vibe_coders : [];
  const lines = [];

  lines.push(`Weekly Brief (${days} days) | total=${total} | generated=${generated}`);

  if (report.busiest_day && report.busiest_day.day) {
    lines.push(`Busiest day: ${report.busiest_day.day} (${Number(report.busiest_day.total || 0)}件)`);
  }

  const topActors = Array.isArray(report.top_actors) ? report.top_actors.slice(0, 3) : [];
  const topCards = Array.isArray(report.top_cards) ? report.top_cards.slice(0, 3) : [];
  if (topActors.length) {
    lines.push(`Top actors: ${topActors.map((row) => `${row.actor}(${row.count})`).join(", ")}`);
  }
  if (topCards.length) {
    lines.push(`Top cards: ${topCards.map((row) => `${row.card_id}(${row.count})`).join(", ")}`);
  }

  if (highlights.length) {
    lines.push("");
    lines.push("[Highlights]");
    highlights.forEach((line) => lines.push(`- ${line}`));
  }
  if (playbook.length) {
    lines.push("");
    lines.push("[Vibe Playbook]");
    playbook.forEach((line) => lines.push(`- ${line}`));
  }

  auditWeeklyBriefRoot.textContent = lines.join("\n");
}

async function loadAuditWeeklyBrief() {
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const params = buildAuditStatsParams(trendDays);
  const response = await fetch(`/api/admin/audit/weekly-report?${params.toString()}`);
  if (!response.ok) throw new Error(`weekly brief failed: ${response.status}`);
  const report = await response.json();
  renderWeeklyBrief(report);
}

async function saveWeeklyBriefFiles() {
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const params = buildAuditStatsParams(trendDays);
  params.set("archive", "true");
  const response = await fetch(`/api/admin/audit/weekly-report/write?${params.toString()}`, { method: "POST" });
  if (!response.ok) throw new Error(`weekly brief save failed: ${response.status}`);
  const payload = await response.json();
  auditActionSummary.textContent = `Action summary: weekly brief saved (${payload.total_filtered || 0} rows)`;
  await loadWeeklyHistory();
}

async function publishWeeklyBrief() {
  const trendDays = Number(auditTrendDaysSelect.value || "7");
  const params = buildAuditStatsParams(trendDays);
  params.set("save", "true");
  params.set("archive", "true");
  const response = await fetch(`/api/admin/audit/weekly-report/publish?${params.toString()}`, { method: "POST" });
  if (!response.ok) throw new Error(`weekly brief publish failed: ${response.status}`);
  const payload = await response.json();
  const publish = payload.publish && typeof payload.publish === "object" ? payload.publish : {};
  const channels = Object.entries(publish).map(([name, state]) => `${name}=${state}`);
  const channelText = channels.length ? channels.join(", ") : "no channel";
  auditActionSummary.textContent = `Action summary: weekly brief published (${channelText})`;
  await loadWeeklyHistory();
}

function renderWeeklyHistory(items) {
  if (!Array.isArray(items) || !items.length) {
    auditWeeklyHistoryRoot.textContent = "履歴: まだ保存履歴がありません";
    return;
  }
  const lines = [];
  lines.push("Weekly Brief History");
  items.forEach((row, index) => {
    const savedAt = formatDate(row.saved_at);
    const days = Number(row.days || 7);
    const total = Number(row.total_filtered || 0);
    const archiveJson = row.archive_json_path ? ` | archive_json=${row.archive_json_path}` : "";
    lines.push(`${index + 1}. ${savedAt} | ${days}d | total=${total}${archiveJson}`);
  });
  auditWeeklyHistoryRoot.textContent = lines.join("\n");
}

async function loadWeeklyHistory() {
  const params = buildHistoryParams();
  const response = await fetch(`/api/admin/audit/weekly-report/history?${params.toString()}`);
  if (!response.ok) throw new Error(`weekly history failed: ${response.status}`);
  const payload = await response.json();
  renderWeeklyHistory(payload.items || []);
  const query = params.get("q");
  const scope = query ? `history_q=${query}` : "history_q=none";
  auditStatus.textContent = `${auditStatus.textContent.split(" | history:")[0]} | history: ${payload.total_filtered || 0}/${payload.total || 0} (${scope})`;
}

function downloadWeeklyHistoryCsv() {
  const params = buildHistoryParams();
  window.location.href = `/api/admin/audit/weekly-report/history.csv?${params.toString()}`;
}

async function clearWeeklyHistory() {
  const keepLatest = Number(auditHistoryKeepLatestSelect.value || "0");
  const ok = window.confirm(`保存済みの週次履歴を削除します（keep_latest=${keepLatest}）。続けますか？`);
  if (!ok) return;
  const params = buildHistoryParams();
  params.set("confirm", "true");
  params.set("keep_latest", String(Math.max(keepLatest, 0)));
  const response = await fetch(`/api/admin/audit/weekly-report/history?${params.toString()}`, { method: "DELETE" });
  if (!response.ok) throw new Error(`weekly history delete failed: ${response.status}`);
  const payload = await response.json();
  auditActionSummary.textContent = `Action summary: weekly history deleted=${payload.deleted}`;
  await loadWeeklyHistory();
}

async function trimWeeklyHistory() {
  const keepLatest = Number(auditHistoryKeepLatestSelect.value || "0");
  if (keepLatest <= 0) {
    throw new Error("keep_latest must be > 0 for trim");
  }
  const ok = window.confirm(`履歴全体を最新${keepLatest}件に圧縮します。続けますか？`);
  if (!ok) return;
  const params = new URLSearchParams();
  params.set("confirm", "true");
  params.set("keep_latest", String(keepLatest));
  const response = await fetch(`/api/admin/audit/weekly-report/history/cleanup?${params.toString()}`, { method: "POST" });
  if (!response.ok) throw new Error(`weekly history cleanup failed: ${response.status}`);
  const payload = await response.json();
  auditActionSummary.textContent = `Action summary: weekly history trimmed deleted=${payload.deleted}`;
  await loadWeeklyHistory();
}

async function copyAuditFilterUrl() {
  const url = auditFilterUrl(false);
  try {
    await navigator.clipboard.writeText(url);
    auditActionSummary.textContent = `Action summary: URL copied`;
  } catch (error) {
    auditActionSummary.textContent = `Action summary: copy failed`;
  }
}

function renderCards(cards) {
  clearCards();

  if (!cards.length) {
    const p = document.createElement("p");
    p.textContent = "No cards found.";
    cardsRoot.appendChild(p);
    return;
  }

  cards.forEach((card) => {
    const fragment = template.content.cloneNode(true);

    fragment.querySelector(".tier").textContent = `Tier ${card.source.tier}`;

    const sectionEl = fragment.querySelector(".section");
    sectionEl.textContent = card.section;
    sectionEl.classList.add(card.section);

    const difficultyLevel = card.builder_pack?.difficulty?.level || "n/a";
    const difficultyEl = fragment.querySelector(".difficulty");
    difficultyEl.textContent = difficultyLevel;
    difficultyEl.classList.add(difficultyClass(difficultyLevel));

    const statusChip = fragment.querySelector(".status");
    statusChip.textContent = card.status;

    fragment.querySelector(".score").textContent = `Score ${card.score_total}`;
    fragment.querySelector(".headline").textContent = card.headline;
    fragment.querySelector(".source-meta").textContent = `${card.source.name} | ${formatDate(card.source.published_at)}`;
    fragment.querySelector(".summary").textContent = card.summary;
    fragment.querySelector(".display-text").textContent = card.display_text;

    const statusInput = fragment.querySelector(".status-select");
    statusInput.value = card.status || "published";

    const pinInput = fragment.querySelector(".pin-check");
    pinInput.checked = Boolean(card.is_pinned);

    const pinRankInput = fragment.querySelector(".pin-rank");
    pinRankInput.value = Number.isFinite(card.pin_rank) ? card.pin_rank : 1000;

    const saveBtn = fragment.querySelector(".save-btn");
    saveBtn.addEventListener("click", async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";

      try {
        await saveCard(card.id, statusInput.value, pinInput.checked, Number(pinRankInput.value || 1000));
        statusText.textContent = `Saved: ${card.headline}`;
        await loadCards();
        await loadAuditLogs();
      } catch (error) {
        statusText.textContent = `Save error: ${error.message}`;
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save";
      }
    });

    const link = fragment.querySelector(".source-link");
    link.href = card.source.url;

    cardsRoot.appendChild(fragment);
  });
}

async function loadCards() {
  const params = new URLSearchParams({
    audience: audienceSelect.value,
    section: sectionSelect.value,
    status: statusSelect.value,
    limit: "300",
  });
  if (difficultySelect.value) {
    params.set("difficulty", difficultySelect.value);
  }

  const response = await fetch(`/api/admin/cards?${params.toString()}`);
  if (!response.ok) throw new Error(`load failed: ${response.status}`);

  const data = await response.json();
  statusText.textContent = `Updated: ${formatDate(data.generated_at)} | cards: ${data.total}`;
  renderCards(data.cards || []);
}

async function reloadAll() {
  await loadCards();
  await loadAuditLogs();
}

[audienceSelect, sectionSelect, statusSelect, difficultySelect].forEach((el) => {
  el.addEventListener("change", () => {
    reloadAll().catch((error) => {
      statusText.textContent = `Load error: ${error.message}`;
    });
  });
});

reloadButton.addEventListener("click", () => {
  reloadAll().catch((error) => {
    statusText.textContent = `Load error: ${error.message}`;
  });
});

[auditActionSelect, auditLimitSelect].forEach((el) => {
  el.addEventListener("change", () => {
    resetAuditOffset();
    saveAuditFilterState();
    loadAuditLogs().catch((error) => {
      setAuditLoadError(error.message);
    });
  });
});

[auditCardIdInput, auditActorInput].forEach((el) => {
  el.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    resetAuditOffset();
    saveAuditFilterState();
    loadAuditLogs().catch((error) => {
      setAuditLoadError(error.message);
    });
  });
  el.addEventListener("change", saveAuditFilterState);
});

[auditFromTsInput, auditToTsInput].forEach((el) => {
  el.addEventListener("change", () => {
    auditRangePresetSelect.value = "custom";
    resetAuditOffset();
    saveAuditFilterState();
    loadAuditLogs().catch((error) => {
      setAuditLoadError(error.message);
    });
  });
});

auditRangePresetSelect.addEventListener("change", () => {
  const preset = auditRangePresetSelect.value;
  if (preset !== "custom") applyRangePreset(preset);
  resetAuditOffset();
  saveAuditFilterState();
  loadAuditLogs().catch((error) => {
    setAuditLoadError(error.message);
  });
});

auditClearRangeButton.addEventListener("click", () => {
  auditRangePresetSelect.value = "custom";
  auditFromTsInput.value = "";
  auditToTsInput.value = "";
  resetAuditOffset();
  saveAuditFilterState();
  loadAuditLogs().catch((error) => {
    setAuditLoadError(error.message);
  });
});

auditReloadButton.addEventListener("click", () => {
  loadAuditLogs().catch((error) => {
    setAuditLoadError(error.message);
  });
});

auditDownloadButton.addEventListener("click", downloadAuditCsv);
auditTrendDownloadButton.addEventListener("click", downloadAuditTrendCsv);
auditWeeklyReportButton.addEventListener("click", () => {
  loadAuditWeeklyBrief().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyMdButton.addEventListener("click", downloadAuditWeeklyMd);
auditWeeklySaveButton.addEventListener("click", () => {
  saveWeeklyBriefFiles().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyPublishButton.addEventListener("click", () => {
  publishWeeklyBrief().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyHistoryButton.addEventListener("click", () => {
  loadWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyHistoryReloadButton.addEventListener("click", () => {
  loadWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyHistoryCsvButton.addEventListener("click", downloadWeeklyHistoryCsv);
auditWeeklyHistoryClearButton.addEventListener("click", () => {
  clearWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditWeeklyHistoryCleanupButton.addEventListener("click", () => {
  trimWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditCopyLinkButton.addEventListener("click", () => {
  copyAuditFilterUrl().catch((error) => {
    setAuditLoadError(error.message);
  });
});

[auditTrendScopeSelect, auditTrendDaysSelect, auditTopLimitSelect].forEach((el) => {
  el.addEventListener("change", () => {
    saveAuditFilterState();
    loadAuditLogs().catch((error) => {
      setAuditLoadError(error.message);
    });
  });
});

auditHistoryLimitSelect.addEventListener("change", () => {
  saveAuditFilterState();
  loadWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});

[auditHistorySortSelect, auditHistoryKeepLatestSelect].forEach((el) => {
  el.addEventListener("change", () => {
    saveAuditFilterState();
    loadWeeklyHistory().catch((error) => {
      setAuditLoadError(error.message);
    });
  });
});

auditHistorySearchInput.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") return;
  saveAuditFilterState();
  loadWeeklyHistory().catch((error) => {
    setAuditLoadError(error.message);
  });
});
auditHistorySearchInput.addEventListener("change", saveAuditFilterState);

auditPrevButton.addEventListener("click", () => {
  const pageSize = Number(auditLimitSelect.value || "50");
  auditOffset = Math.max(auditOffset - pageSize, 0);
  loadAuditLogs().catch((error) => {
    setAuditLoadError(error.message);
  });
});

auditNextButton.addEventListener("click", () => {
  const pageSize = Number(auditLimitSelect.value || "50");
  auditOffset += pageSize;
  loadAuditLogs().catch((error) => {
    setAuditLoadError(error.message);
  });
});

restoreAuditFilterState();
applyAuditFiltersFromUrl();
reloadAll().catch((error) => {
  statusText.textContent = `Load error: ${error.message}`;
  setAuditLoadError(error.message);
});
