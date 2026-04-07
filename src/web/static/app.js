const cardsRoot = document.getElementById("cards");
const template = document.getElementById("cardTemplate");
const statusText = document.getElementById("statusText");

const audienceSelect = document.getElementById("audience");
const sectionSelect = document.getElementById("section");
const topicSelect = document.getElementById("topic");
const difficultySelect = document.getElementById("difficulty");
const refreshButton = document.getElementById("refresh");
const presetSelect = document.getElementById("presetSelect");
const presetNameInput = document.getElementById("presetName");
const presetSaveButton = document.getElementById("presetSave");
const presetApplyButton = document.getElementById("presetApply");
const presetDeleteButton = document.getElementById("presetDelete");
const copyFilterUrlButton = document.getElementById("copyFilterUrl");
const affiliateDisclosure = document.getElementById("affiliateDisclosure");
const affiliateList = document.getElementById("affiliateList");

const FILTER_PRESETS_KEY = "world_ai_curation_feed_filter_presets_v1";
const LAST_FILTER_KEY = "world_ai_curation_feed_last_filter_v1";

function formatDate(iso) {
  if (!iso) return "不明";
  const date = new Date(iso);
  return date.toLocaleString();
}

function clearCards() {
  while (cardsRoot.firstChild) {
    cardsRoot.removeChild(cardsRoot.firstChild);
  }
}

function clearAffiliateList() {
  while (affiliateList.firstChild) {
    affiliateList.removeChild(affiliateList.firstChild);
  }
}

function loadJsonStorage(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed ?? fallback;
  } catch (error) {
    return fallback;
  }
}

function saveJsonStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // Ignore storage failures.
  }
}

function setSelectIfPresent(selectEl, value) {
  if (!selectEl || value == null) return;
  const next = String(value);
  const hasOption = Array.from(selectEl.options || []).some((opt) => opt.value === next);
  if (hasOption) {
    selectEl.value = next;
  }
}

function currentFilters() {
  return {
    audience: audienceSelect.value || "vibe",
    section: sectionSelect.value || "all",
    topic: topicSelect.value || "",
    difficulty: difficultySelect.value || "",
  };
}

function applyFilters(filters) {
  if (!filters || typeof filters !== "object") return;
  setSelectIfPresent(audienceSelect, filters.audience || "vibe");
  setSelectIfPresent(sectionSelect, filters.section || "all");
  setSelectIfPresent(topicSelect, filters.topic || "");
  setSelectIfPresent(difficultySelect, filters.difficulty || "");
}

function filtersToParams(filters) {
  const params = new URLSearchParams();
  params.set("audience", filters.audience || "vibe");
  params.set("section", filters.section || "all");
  if (filters.topic) params.set("topic", filters.topic);
  if (filters.difficulty) params.set("difficulty", filters.difficulty);
  return params;
}

function updateUrlByFilters(filters) {
  const params = filtersToParams(filters);
  const next = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", next);
}

function readUrlFilters() {
  const params = new URLSearchParams(window.location.search || "");
  if (!params.toString()) return null;
  return {
    audience: params.get("audience") || "vibe",
    section: params.get("section") || "all",
    topic: params.get("topic") || "",
    difficulty: params.get("difficulty") || "",
  };
}

function readPresets() {
  const raw = loadJsonStorage(FILTER_PRESETS_KEY, []);
  if (!Array.isArray(raw)) return [];
  return raw.filter((item) => item && typeof item === "object" && item.id && item.name && item.filters);
}

function writePresets(presets) {
  saveJsonStorage(FILTER_PRESETS_KEY, presets);
}

function presetDisplayName(item) {
  if (!item || typeof item !== "object") return "名称未設定";
  return String(item.name || "名称未設定");
}

function refreshPresetOptions(selectedId = "") {
  const presets = readPresets();
  presetSelect.innerHTML = "";

  const baseOption = document.createElement("option");
  baseOption.value = "";
  baseOption.textContent = "保存済みを選択";
  baseOption.selected = true;
  presetSelect.appendChild(baseOption);

  presets.forEach((item) => {
    const opt = document.createElement("option");
    opt.value = String(item.id);
    opt.textContent = presetDisplayName(item);
    if (selectedId && opt.value === selectedId) {
      opt.selected = true;
    }
    presetSelect.appendChild(opt);
  });
}

function persistLastFilter() {
  saveJsonStorage(LAST_FILTER_KEY, currentFilters());
}

function restoreInitialFilters() {
  const fromUrl = readUrlFilters();
  if (fromUrl) {
    applyFilters(fromUrl);
    persistLastFilter();
    return;
  }
  const fromStorage = loadJsonStorage(LAST_FILTER_KEY, null);
  if (fromStorage && typeof fromStorage === "object") {
    applyFilters(fromStorage);
  }
}

function renderAffiliateLinks(payload) {
  clearAffiliateList();
  const disclosure = payload && typeof payload.disclosure === "string" ? payload.disclosure : "";
  affiliateDisclosure.textContent =
    disclosure || "本ページにはアフィリエイトリンクが含まれる場合があります。";

  const links = Array.isArray(payload?.links) ? payload.links : [];
  if (!links.length) {
    const empty = document.createElement("p");
    empty.className = "affiliate-empty";
    empty.textContent = "現在、掲載準備中です。";
    affiliateList.appendChild(empty);
    return;
  }

  links.forEach((item) => {
    const card = document.createElement("article");
    card.className = "affiliate-card";

    if (item.image_url) {
      const imageLink = document.createElement("a");
      imageLink.href = item.url || "#";
      imageLink.target = "_blank";
      imageLink.rel = "nofollow sponsored noopener noreferrer";
      imageLink.className = "affiliate-image-link";

      const image = document.createElement("img");
      image.className = "affiliate-image";
      image.src = item.image_url;
      image.alt = item.image_alt || `${item.title || "おすすめリンク"} の商品画像`;
      image.loading = "lazy";
      image.decoding = "async";
      image.referrerPolicy = "no-referrer";
      imageLink.appendChild(image);
      card.appendChild(imageLink);
    }

    const title = document.createElement("h3");
    title.className = "affiliate-title";
    title.textContent = item.title || "おすすめリンク";
    card.appendChild(title);

    if (item.badge) {
      const badge = document.createElement("span");
      badge.className = "affiliate-badge";
      badge.textContent = item.badge;
      card.appendChild(badge);
    }

    if (item.description) {
      const desc = document.createElement("p");
      desc.className = "affiliate-description";
      desc.textContent = item.description;
      card.appendChild(desc);
    }

    const link = document.createElement("a");
    link.href = item.url || "#";
    link.target = "_blank";
    link.rel = "nofollow sponsored noopener noreferrer";
    link.className = "affiliate-link";
    link.textContent = "詳細を見る";
    card.appendChild(link);

    if (item.image_url) {
      const imageNote = document.createElement("p");
      imageNote.className = "affiliate-image-note";
      imageNote.textContent = "画像はAmazon提供素材を使用しています。";
      card.appendChild(imageNote);
    }

    affiliateList.appendChild(card);
  });
}

async function loadAffiliateLinks() {
  try {
    const response = await fetch("/api/affiliate-links");
    if (!response.ok) throw new Error(`おすすめ情報の取得に失敗しました: ${response.status}`);
    const payload = await response.json();
    renderAffiliateLinks(payload);
  } catch (error) {
    affiliateDisclosure.textContent = "おすすめリンクの読み込みに失敗しました。";
    clearAffiliateList();
  }
}

function difficultyClass(level) {
  if (level === "初級" || level === "初級（検証前提）") return "difficulty-beginner";
  if (level === "中級") return "difficulty-intermediate";
  if (level === "上級寄り") return "difficulty-advanced";
  return "difficulty-unknown";
}

function sectionLabel(value) {
  if (value === "main") return "メイン";
  if (value === "signals") return "シグナル（未検証ふくむ）";
  return value || "不明";
}

function topicLabel(value) {
  if (value === "agents") return "エージェント";
  if (value === "developer-tools") return "開発ツール";
  if (value === "research") return "研究";
  if (value === "policy") return "ポリシー";
  if (value === "general") return "一般";
  return value || "一般";
}

function compactList(value, limit = 3) {
  const rows = Array.isArray(value) ? value : [];
  return rows
    .map((line) => String(line || "").trim())
    .filter((line) => line.length > 0)
    .slice(0, limit);
}

function hasJapanese(text) {
  return /[\u3040-\u30ff\u3400-\u9fff]/.test(String(text || ""));
}

function personaActionHint(topic) {
  if (topic === "agents") return "まずは1つの作業だけ自動化すると理解しやすいです。";
  if (topic === "developer-tools") return "まずは使っているアプリ1つとの連携イメージを持てば十分です。";
  if (topic === "research") return "結論だけ先に押さえて、詳しい式や実験条件は後でOKです。";
  if (topic === "policy") return "ルール変更は『何が禁止・必須になったか』だけ先に見ればOKです。";
  return "まずは『自分に関係あるか』だけ判断すれば十分です。";
}

function buildJapaneseFallbackSummary(card) {
  const topic = topicLabel(card.topic);
  const section = sectionHint(card.section);
  const trust = tierHint(card.source?.tier || "");
  const published = formatDate(card.source?.published_at);
  const sourceName = String(card.source?.name || "海外ソース");
  const actionHint = personaActionHint(card.topic);

  return `海外の${topic}分野で新しい動きが出ています。情報元は${sourceName}で、分類は「${section}」、信頼度の目安は「${trust}」、公開時点は${published}です。${actionHint}`;
}

function localizedSummary(card) {
  const summary = simplifyJapanese(card.summary || "");
  if (summary && hasJapanese(summary)) return summary;
  return buildJapaneseFallbackSummary(card);
}

function localizeBodyText(text, card) {
  const value = String(text || "").trim();
  if (!value) return buildJapaneseFallbackSummary(card);
  if (hasJapanese(value)) return value;

  const lines = [];
  lines.push("このカードの読み方");
  lines.push(`・${buildJapaneseFallbackSummary(card)}`);
  lines.push("・詳細は「元情報（原文）を開く」から確認できます。");
  lines.push("・難しい場合は、下の「作ってみる手順」を上から順に試してください。");
  return lines.join("\n");
}

function renderReadableBody(text, headline, summary) {
  const lines = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

  const output = [];
  const skipExact = new Set([
    "[Vibe]",
    "[Raw]",
    "[Builder]",
    "今日やること:",
    "今日できること:",
    "専門用語ミニ辞典:",
  ]);

  lines.forEach((line) => {
    if (skipExact.has(line)) return;
    if (/^\[[^\]]+\]$/.test(line)) return;
    if (/^Source:\s*/i.test(line)) return;
    if (/^Published:\s*/i.test(line)) return;
    if (/^URL:\s*/i.test(line)) return;
    if (/^Summary:\s*/i.test(line)) line = line.replace(/^Summary:\s*/i, "");
    if (/^タイトル:\s*/.test(line)) return;
    if (/^やさしい要約:\s*/.test(line)) line = line.replace(/^やさしい要約:\s*/, "");
    if (/^なぜ大事？:\s*/.test(line)) line = line.replace(/^なぜ大事？:\s*/, "なぜ重要か: ");
    if (/^注意:\s*/.test(line)) line = line.replace(/^注意:\s*/, "注意: ");
    if (line === headline) return;
    if (summary && line === summary) return;
    output.push(line);
  });

  if (!output.length) return summary || "要点を整理中です。";
  return output.join("\n");
}

function simplifyJapanese(text) {
  let value = String(text || "").trim();
  if (!value) return "";

  const replacements = [
    ["API", "連携機能"],
    ["SDK", "開発キット"],
    ["LLM", "AIモデル"],
    ["benchmark", "比較テスト"],
    ["ベンチマーク", "比較テスト"],
    ["agent", "自動実行AI"],
    ["エージェント", "自動実行AI"],
    ["fine-tuning", "追加学習"],
    ["ファインチューニング", "追加学習"],
  ];
  replacements.forEach(([from, to]) => {
    value = value.replaceAll(from, to);
  });
  return value;
}

function tierHint(tier) {
  if (tier === "A") return "高い（公式・一次情報）";
  if (tier === "B") return "中くらい（信頼メディア）";
  if (tier === "C") return "低め（未検証を含む）";
  return "不明";
}

function sectionHint(section) {
  if (section === "main") return "メイン情報（優先して読めばOK）";
  if (section === "signals") return "補助シグナル（未検証を含む）";
  return "一般";
}

function buildPersonaDigest(card) {
  const summary = localizedSummary(card);
  const lines = [];
  lines.push("何のニュース？");
  lines.push(summary || "要約準備中です。");
  lines.push("");
  lines.push(`情報の種類: ${sectionHint(card.section)}`);
  lines.push(`読み方のコツ: ${personaActionHint(card.topic)}`);
  lines.push(`信頼度: ${tierHint(card.source?.tier || "")}`);
  lines.push(`いつの情報？: ${formatDate(card.source?.published_at)}`);
  return lines.join("\n");
}

function renderBuilderPack(builderPack) {
  if (!builderPack || typeof builderPack !== "object") {
    return "実践手順は準備中です。";
  }

  const focus = String(builderPack.focus || "").trim();
  const prototype = compactList(builderPack.prototype_30m, 3);
  const next24h = compactList(builderPack.next_24h, 3);
  const difficulty = builderPack.difficulty && typeof builderPack.difficulty === "object" ? builderPack.difficulty : null;
  const beginner = builderPack.for_non_engineers && typeof builderPack.for_non_engineers === "object"
    ? builderPack.for_non_engineers
    : null;
  const noCode = compactList(beginner?.no_code_path, 3);
  const checks = compactList(beginner?.decision_checklist, 3);
  const guardrails = compactList(beginner?.fact_guardrails, 3);

  const lines = [];
  if (focus) {
    lines.push(`ポイント: ${focus}`);
  }
  if (prototype.length) {
    lines.push("");
    lines.push("30分で試すこと:");
    prototype.forEach((line, index) => lines.push(`${index + 1}. ${line}`));
  }
  if (next24h.length) {
    lines.push("");
    lines.push("次の一手:");
    next24h.forEach((line, index) => lines.push(`${index + 1}. ${line}`));
  }
  if (difficulty) {
    if (difficulty.level) lines.push(`難易度: ${difficulty.level}`);
    if (difficulty.estimated_minutes) lines.push(`目安時間: ${difficulty.estimated_minutes}分`);
  }
  if (beginner) {
    if (beginner.first_15m) {
      lines.push("");
      lines.push(`最初の15分: ${beginner.first_15m}`);
    }
    if (noCode.length) {
      lines.push("");
      lines.push("ノーコード手順:");
      noCode.forEach((line, index) => lines.push(`${index + 1}. ${line}`));
    }
    if (checks.length) {
      lines.push("");
      lines.push("確認ポイント:");
      checks.forEach((line, index) => lines.push(`${index + 1}. ${line}`));
    }
    if (guardrails.length) {
      lines.push("");
      lines.push("事実確認:");
      guardrails.forEach((line, index) => lines.push(`${index + 1}. ${line}`));
    }
  }

  if (!lines.length) return "実践手順は準備中です。";
  return lines.join("\n");
}

function renderCards(cards) {
  clearCards();
  const audience = currentFilters().audience || "vibe";

  if (!cards.length) {
    const empty = document.createElement("p");
    empty.textContent = "この条件に一致するカードはありません。";
    cardsRoot.appendChild(empty);
    return;
  }

  cards.forEach((card) => {
    const fragment = template.content.cloneNode(true);

    fragment.querySelector(".tier").textContent = `信頼度 Tier ${card.source.tier}`;

    const sectionEl = fragment.querySelector(".section");
    sectionEl.textContent = sectionLabel(card.section);
    sectionEl.classList.add(card.section);

    fragment.querySelector(".topic").textContent = topicLabel(card.topic);
    const difficultyLevel = card.builder_pack?.difficulty?.level || "不明";
    const difficultyEl = fragment.querySelector(".difficulty");
    difficultyEl.textContent = difficultyLevel;
    difficultyEl.classList.add(difficultyClass(difficultyLevel));
    fragment.querySelector(".score").textContent = `スコア ${card.score_total}`;
    fragment.querySelector(".headline").textContent = card.headline;
    fragment.querySelector(".source-meta").textContent = `${card.source.name} | ${formatDate(card.source.published_at)}`;
    const summaryPrefix = card.section === "signals" ? "補助シグナル: " : "";
    fragment.querySelector(".summary").textContent = `${summaryPrefix}${localizedSummary(card)}`;
    const enrich = card.enrichment || {};
    const enrichLabel = enrich.enabled
      ? `要約モード: AI補助 (${enrich.provider}${enrich.model ? ` / ${enrich.model}` : ""})`
      : `要約モード: 標準 (${enrich.reason || "設定オフ"})`;
    fragment.querySelector(".enrichment-meta").textContent = enrichLabel;
    const displayText = audience === "vibe"
      ? buildPersonaDigest(card)
      : localizeBodyText(renderReadableBody(card.display_text, card.headline, card.summary), card);
    fragment.querySelector(".display-text").textContent = displayText;

    const builderPackEl = fragment.querySelector(".builder-pack");
    if (audience === "builder") {
      builderPackEl.hidden = false;
      fragment.querySelector(".builder-pack-text").textContent = renderBuilderPack(card.builder_pack);
    } else {
      builderPackEl.hidden = true;
    }

    const link = fragment.querySelector(".source-link");
    link.href = card.source.url;
    const sourceLang = String(card.source?.language || "").toLowerCase();
    link.textContent = sourceLang.startsWith("ja") ? "元情報を開く" : "元情報（原文）を開く";
    link.setAttribute("aria-label", `${card.headline} の元情報を開く`);

    cardsRoot.appendChild(fragment);
  });
}

async function loadCards() {
  const filters = currentFilters();
  const params = new URLSearchParams({
    audience: filters.audience,
    section: filters.section,
    limit: "60",
  });

  if (filters.topic) {
    params.set("topic", filters.topic);
  }
  if (filters.difficulty) {
    params.set("difficulty", filters.difficulty);
  }

  const response = await fetch(`/api/cards?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`記事の読み込みに失敗しました: ${response.status}`);
  }

  const data = await response.json();
  statusText.textContent = `最終更新: ${formatDate(data.generated_at)} | 件数: ${data.total}`;
  renderCards(data.cards || []);
}

async function refreshNow() {
  refreshButton.disabled = true;
  refreshButton.textContent = "更新中...";

  try {
    const response = await fetch("/api/refresh", { method: "POST" });
    if (!response.ok) {
      throw new Error(`更新に失敗しました: ${response.status}`);
    }
    await loadCards();
  } catch (error) {
    statusText.textContent = `更新エラー: ${error.message}`;
  } finally {
    refreshButton.disabled = false;
    refreshButton.textContent = "最新情報に更新";
  }
}

function buildAutoPresetName(filters) {
  const topicLabel = filters.topic || "すべてのテーマ";
  const difficultyLabel = filters.difficulty || "すべての難易度";
  return `${topicLabel} | ${difficultyLabel}`;
}

function saveCurrentPreset() {
  const filters = currentFilters();
  const name = (presetNameInput.value || "").trim() || buildAutoPresetName(filters);
  const presets = readPresets();
  const next = [
    ...presets,
    {
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      name: name.slice(0, 40),
      filters,
      created_at: new Date().toISOString(),
    },
  ];
  const limited = next.slice(-20);
  writePresets(limited);
  const selected = limited[limited.length - 1]?.id || "";
  refreshPresetOptions(selected);
  statusText.textContent = `フィルタを保存しました: ${name}`;
}

function applySelectedPreset() {
  const id = presetSelect.value;
  if (!id) {
    statusText.textContent = "先に保存済みフィルタを選択してください。";
    return;
  }
  const preset = readPresets().find((item) => String(item.id) === id);
  if (!preset) {
    statusText.textContent = "保存済みフィルタが見つかりません。";
    refreshPresetOptions("");
    return;
  }
  applyFilters(preset.filters);
  persistLastFilter();
  updateUrlByFilters(currentFilters());
  loadCards().catch((error) => {
    statusText.textContent = `読み込みエラー: ${error.message}`;
  });
}

function deleteSelectedPreset() {
  const id = presetSelect.value;
  if (!id) {
    statusText.textContent = "削除する保存済みフィルタを選択してください。";
    return;
  }
  const presets = readPresets();
  const target = presets.find((item) => String(item.id) === id);
  const next = presets.filter((item) => String(item.id) !== id);
  writePresets(next);
  refreshPresetOptions("");
  statusText.textContent = `フィルタを削除しました: ${target ? target.name : id}`;
}

async function copyCurrentFilterUrl() {
  const filters = currentFilters();
  const url = `${window.location.origin}${window.location.pathname}?${filtersToParams(filters).toString()}`;
  try {
    await navigator.clipboard.writeText(url);
    statusText.textContent = "条件URLをコピーしました。";
  } catch (error) {
    statusText.textContent = "URLのコピーに失敗しました。";
  }
}

[audienceSelect, sectionSelect, topicSelect, difficultySelect].forEach((el) => {
  el.addEventListener("change", () => {
    persistLastFilter();
    updateUrlByFilters(currentFilters());
    loadCards().catch((error) => {
      statusText.textContent = `読み込みエラー: ${error.message}`;
    });
  });
});

refreshButton.addEventListener("click", () => {
  refreshNow();
});

presetSaveButton.addEventListener("click", saveCurrentPreset);
presetApplyButton.addEventListener("click", applySelectedPreset);
presetDeleteButton.addEventListener("click", deleteSelectedPreset);
copyFilterUrlButton.addEventListener("click", () => {
  copyCurrentFilterUrl();
});

restoreInitialFilters();
refreshPresetOptions("");
persistLastFilter();
updateUrlByFilters(currentFilters());
loadCards().catch((error) => {
  statusText.textContent = `読み込みエラー: ${error.message}`;
});
loadAffiliateLinks();
