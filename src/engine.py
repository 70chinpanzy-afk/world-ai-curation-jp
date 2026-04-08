"""Ingestion and curation orchestration."""

from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .connectors.rss_connector import fetch_rss_items
from .connectors.x_connector import fetch_x_items
from .curation_pipeline import SourceItem, rank_items
from .llm_enricher import enrich_variants
from .source_config import SourceDefinition, load_source_settings


_WORD_RE = re.compile(r"[a-zA-Z0-9]+")
_JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_TIER_PRIORITY = {"A": 3, "B": 2, "C": 1}


def _normalized_title(title: str) -> str:
    words = _WORD_RE.findall(title.lower())
    return " ".join(words[:20])


def _item_id(item: SourceItem) -> str:
    key = f"{item.source_name}|{item.url}|{item.title}".encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:16]


def _topic_from_text(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if any(x in text for x in ["agent", "workflow", "automation"]):
        return "agents"
    if any(x in text for x in ["coding", "developer", "sdk", "api"]):
        return "developer-tools"
    if any(x in text for x in ["safety", "policy", "governance", "regulation"]):
        return "policy"
    if any(x in text for x in ["benchmark", "paper", "arxiv", "research"]):
        return "research"
    return "general"


def _has_japanese(text: str) -> bool:
    return bool(_JA_RE.search(str(text or "")))


def _extract_easy_summary_from_vibe(vibe: str) -> str:
    for raw_line in str(vibe or "").splitlines():
        line = raw_line.strip()
        if line.startswith("やさしい要約:"):
            return line.replace("やさしい要約:", "", 1).strip()
    return ""


def _topic_label_ja(topic: str) -> str:
    if topic == "agents":
        return "AIエージェント"
    if topic == "developer-tools":
        return "開発ツール"
    if topic == "research":
        return "研究"
    if topic == "policy":
        return "政策・ルール"
    return "AI一般"


def _section_hint_ja(section: str) -> str:
    if section == "main":
        return "優先して確認すべき主要アップデートです。"
    return "補助シグナルとして、裏取り前提で扱う情報です。"


def _fallback_summary_ja(*, headline: str, topic: str, section: str) -> str:
    topic_ja = _topic_label_ja(topic)
    section_hint = _section_hint_ja(section)
    return f"{topic_ja}分野の更新です。{headline}に関する発表で、{section_hint}"


def _builder_focus_for_topic(topic: str) -> str:
    if topic == "agents":
        return "エージェントのタスク分解と再試行設計"
    if topic == "developer-tools":
        return "既存プロダクトへのSDK/API統合"
    if topic == "research":
        return "再現実験の最小構成と評価指標"
    if topic == "policy":
        return "ガードレールと監査ログ設計"
    return "ユーザー価値に直結する小さな自動化"


def _difficulty_profile(item: SourceItem, topic: str) -> Dict[str, Any]:
    text = f"{item.title} {item.summary}".lower()
    advanced_terms = [
        "benchmark",
        "ablation",
        "alignment",
        "distillation",
        "architecture",
        "scaling law",
        "theorem",
        "proof",
    ]
    medium_terms = ["sdk", "api", "integration", "workflow", "agent", "deployment", "dataset", "finetune"]

    if any(term in text for term in advanced_terms):
        return {
            "level": "上級寄り",
            "reason": "研究評価や高度な設計判断が必要な可能性があります。",
            "estimated_minutes": 120,
        }
    if any(term in text for term in medium_terms) or topic in {"developer-tools", "agents"}:
        return {
            "level": "中級",
            "reason": "API連携や実装判断を伴うため、段階的に試すと安全です。",
            "estimated_minutes": 60,
        }
    if item.source_tier == "C":
        return {
            "level": "初級（検証前提）",
            "reason": "シグナル情報なので、まずは事実確認を優先してください。",
            "estimated_minutes": 30,
        }
    return {
        "level": "初級",
        "reason": "小さく試して学べるテーマです。まずは動く最小形から始められます。",
        "estimated_minutes": 30,
    }


def _no_code_path(topic: str) -> List[str]:
    if topic == "agents":
        return [
            "Notion: タスクDBを作り、状態遷移（todo/doing/done）を定義する",
            "Zapier/Make: 新規タスク作成時にSlack通知するフローを組む",
            "ChatGPT/Claude: タスク本文から次アクション3件を自動生成する",
        ]
    if topic == "developer-tools":
        return [
            "Postman: APIリクエストを1本だけ再現する",
            "Retool: API結果を一覧表示する簡易UIを作る",
            "Google Sheets: 結果を蓄積して差分を目視確認する",
        ]
    if topic == "research":
        return [
            "NotebookLM/Notion: 論文要点を3行でまとめる",
            "Google Sheets: 比較表（精度/速度/コスト）を作る",
            "ChatGPT: 自分の用途への適用条件をQ&A化する",
        ]
    if topic == "policy":
        return [
            "Notion: リスク項目と確認担当をチェックリスト化する",
            "Slack Workflow: 公開前確認フローをテンプレ化する",
            "Google Forms: 社内レビューの記録を残す",
        ]
    return [
        "Notion: 要件を1ページで整理する",
        "Zapier/Make: 1つだけ自動化フローを作る",
        "Google Sheets: 成果指標（時間削減など）を記録する",
    ]


def _decision_checklist(section: str) -> List[str]:
    checks = [
        "一次情報URLを開き、見出しと本文が一致するか確認したか",
        "誰に何の価値が出る機能かを1文で説明できるか",
        "30分以内で試せる最小スコープに切れているか",
    ]
    if section == "signals":
        checks.append("未検証情報であることを明記し、公開前に再確認する前提か")
    else:
        checks.append("公開前にコスト・遅延・安全性の3点を確認したか")
    return checks


def _fact_guardrails(item: SourceItem, section: str) -> List[str]:
    source_kind = "一次・信頼ソース" if item.source_tier in {"A", "B"} else "補助シグナル"
    lines = [
        f"事実: このカードは {source_kind}（Tier {item.source_tier}）を参照しています。",
        "推測: 効果や将来性は、あなたの用途での検証結果が出るまで仮説として扱ってください。",
    ]
    if section == "signals":
        lines.append("注意: Signalsは誤情報を含む可能性があるため、必ずTier A/Bで裏取りしてください。")
    return lines


def _vibe_prompt_template(item: SourceItem, topic: str) -> str:
    return (
        "あなたはやさしいAIメンターです。次のニュースを、非エンジニア向けに実装手順へ変換してください。\n"
        f"- ニュース: {item.title}\n"
        f"- 要約: {item.summary[:220]}\n"
        f"- トピック: {topic}\n"
        "出力条件:\n"
        "1) 専門用語を中学生でも分かる表現に言い換える\n"
        "2) 15分でできる最初の一歩を1つ\n"
        "3) ノーコード手順を3ステップ\n"
        "4) 失敗しやすいポイントを2つ\n"
        "5) 今日のゴールを1行"
    )


def _builder_pack_for_item(*, item: SourceItem, topic: str, section: str) -> Dict[str, Any]:
    trust_note = "一次情報寄りのため、先行導入の検討価値あり。" if item.source_tier in {"A", "B"} else "未検証シグナル。先に検証実験から着手。"
    section_note = "Main扱いなのでプロトタイプ候補。" if section == "main" else "Signals扱いなので本番化前提ではなく検証前提。"
    focus = _builder_focus_for_topic(topic)
    difficulty = _difficulty_profile(item, topic)

    prototype_30m = [
        f"1) 10分: {item.title} を1文で説明し、やらない範囲を決める",
        f"2) 10分: {focus} を最小機能1つに切る",
        "3) 10分: ダミーデータでUIまたはAPIの動作確認を行う",
    ]
    next_24h = [
        "一次情報で仕様差分を再確認する",
        "ログと失敗時フォールバックを追加する",
        "公開前チェックリスト（コスト/遅延/安全性）を埋める",
    ]

    return {
        "focus": focus,
        "context": [trust_note, section_note],
        "prototype_30m": prototype_30m,
        "next_24h": next_24h,
        "difficulty": difficulty,
        "for_non_engineers": {
            "first_15m": f"ニュースを1文で説明し、{focus} のうち1機能だけを試作対象に決める。",
            "no_code_path": _no_code_path(topic),
            "decision_checklist": _decision_checklist(section),
            "fact_guardrails": _fact_guardrails(item, section),
            "vibe_prompt_template": _vibe_prompt_template(item, topic),
        },
        "prompt_seed": f"{item.title} を題材に、非エンジニア向けに実装ステップを3段階で提案してください。",
    }


def _tier_rank(tier: str) -> int:
    return _TIER_PRIORITY.get(str(tier or "").upper(), 0)


def _main_feed_minimum_tier(policy: Dict[str, Any]) -> str:
    value = str(policy.get("main_feed_minimum_tier", "B")).upper().strip()
    return value if value in _TIER_PRIORITY else "B"


def _resolve_tier_c_source_limit(policy: Dict[str, Any], default_limit: int) -> int:
    env_value = os.getenv("TIER_C_SOURCE_LIMIT", "").strip()
    raw_value: Any = env_value if env_value else policy.get("tier_c_max_items_per_source", 5)
    try:
        parsed = int(raw_value)
    except Exception:
        parsed = 5
    return max(1, min(default_limit, parsed))


def _story_key(item: SourceItem) -> str:
    norm = _normalized_title(item.title)
    if not norm:
        return item.url.strip().lower()

    # 短いタイトルは別記事衝突を避けるため、ホスト単位で分離する。
    if len(norm) < 28:
        host = urllib.parse.urlparse(item.url).netloc.lower().strip()
        return f"{norm}|{host}"
    return norm


def _is_better_item(candidate: SourceItem, current: SourceItem) -> bool:
    candidate_rank = _tier_rank(candidate.source_tier)
    current_rank = _tier_rank(current.source_tier)
    if candidate_rank != current_rank:
        return candidate_rank > current_rank

    candidate_signal = candidate.impact_hint + candidate.actionability_hint + candidate.novelty_hint
    current_signal = current.impact_hint + current.actionability_hint + current.novelty_hint
    if candidate_signal != current_signal:
        return candidate_signal > current_signal

    if candidate.published_at != current.published_at:
        return candidate.published_at > current.published_at

    return len(candidate.summary or "") > len(current.summary or "")


def _deduplicate_items(items: List[SourceItem]) -> List[SourceItem]:
    deduped_by_story: Dict[str, SourceItem] = {}
    seen_urls = set()

    for item in items:
        url_key = item.url.strip().lower()
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)

        key = _story_key(item)
        current = deduped_by_story.get(key)
        if current is None or _is_better_item(item, current):
            deduped_by_story[key] = item

    return list(deduped_by_story.values())


def _collect_items(sources: List[SourceDefinition], limit_per_source: int, policy: Dict[str, Any]) -> Tuple[List[SourceItem], List[str]]:
    all_items: List[SourceItem] = []
    errors: List[str] = []
    tier_c_source_limit = _resolve_tier_c_source_limit(policy, default_limit=limit_per_source)

    for source in sources:
        if not source.is_active:
            continue
        effective_limit = limit_per_source if _tier_rank(source.tier) >= _tier_rank("B") else tier_c_source_limit

        if source.kind in {"rss", "website"}:
            items, err = fetch_rss_items(source, limit=effective_limit)
            all_items.extend(items)
            if err:
                errors.append(err)
            continue

        if source.kind == "api":
            provider = str((source.params or {}).get("provider", "")).lower()
            if provider == "x":
                items, err = fetch_x_items(source, limit=effective_limit)
                all_items.extend(items)
                if err:
                    errors.append(err)
                continue

            if source.tier == "C":
                errors.append(f"Skipped social API source (optional): {source.name}")
                continue

            errors.append(f"Unsupported API source: {source.name} provider={provider or 'unknown'}")
            continue

        errors.append(f"Unsupported source kind for now: {source.name} ({source.kind})")

    return all_items, errors


def _fallback_items() -> List[SourceItem]:
    now = datetime.now(tz=timezone.utc)
    return [
        SourceItem(
            source_name="Fallback Global Research",
            source_tier="A",
            title="How to evaluate new AI model updates safely",
            url="https://example.com/fallback/research-eval",
            published_at=now,
            language="en",
            summary="Primary-source style fallback card to keep the UI usable when feeds are temporarily unavailable.",
            novelty_hint=0.6,
            impact_hint=0.7,
            actionability_hint=0.8,
        ),
        SourceItem(
            source_name="Fallback Builder Ops",
            source_tier="B",
            title="Practical checklist for shipping AI features weekly",
            url="https://example.com/fallback/shipping-checklist",
            published_at=now,
            language="en",
            summary="A builder-friendly fallback for aspiring engineers and non-engineers.",
            novelty_hint=0.5,
            impact_hint=0.6,
            actionability_hint=0.9,
        ),
        SourceItem(
            source_name="Fallback Social Signal",
            source_tier="C",
            title="Unconfirmed social rumor about model benchmark",
            url="https://example.com/fallback/social-rumor",
            published_at=now,
            language="en",
            summary="Signal-only item kept out of the main section unless corroborated.",
            novelty_hint=0.7,
            impact_hint=0.5,
            actionability_hint=0.3,
        ),
    ]


def refresh_cards(config_path: Path | None = None, limit_per_source: int = 20) -> Dict[str, Any]:
    settings = load_source_settings(config_path=config_path)
    main_min_tier = _main_feed_minimum_tier(settings.policy)
    tier_c_source_limit = _resolve_tier_c_source_limit(settings.policy, default_limit=limit_per_source)
    items, errors = _collect_items(settings.sources, limit_per_source=limit_per_source, policy=settings.policy)

    deduped_items = _deduplicate_items(items)
    if not deduped_items:
        errors.append("No live items were ingested. Fallback cards were generated.")
        deduped_items = _fallback_items()

    normalized_title_to_tiers: Dict[str, set[str]] = {}
    for item in deduped_items:
        norm = _normalized_title(item.title)
        normalized_title_to_tiers.setdefault(norm, set()).add(item.source_tier)

    ranked_cards = rank_items(deduped_items)

    serialized_cards: List[Dict[str, Any]] = []
    source_item_by_id = {_item_id(item): item for item in deduped_items}

    for card in ranked_cards:
        card_item_key = _item_id(
            SourceItem(
                source_name=card.source_name,
                source_tier=card.source_tier,
                title=card.headline,
                url=card.source_url,
                published_at=card.published_at,
                language="en",
                summary="",
            )
        )
        source_item = source_item_by_id.get(card_item_key)
        if source_item is None:
            source_item = SourceItem(
                source_name=card.source_name,
                source_tier=card.source_tier,
                title=card.headline,
                url=card.source_url,
                published_at=card.published_at,
                language="en",
                summary="",
            )

        variants, enrichment_meta = enrich_variants(
            item=source_item,
            base=card.variants,
            score_breakdown=card.score_breakdown,
        )

        norm = _normalized_title(card.headline)
        tiers_for_story = normalized_title_to_tiers.get(norm, {card.source_tier})
        confirmed_by_main_tier = any(_tier_rank(t) >= _tier_rank(main_min_tier) for t in tiers_for_story)

        section = "main" if _tier_rank(card.source_tier) >= _tier_rank(main_min_tier) else "signals"
        if section == "signals" and confirmed_by_main_tier:
            section = "main"

        topic = _topic_from_text(card.headline, source_item.summary if source_item else "")
        summary_original = source_item.summary if source_item else ""
        summary_from_vibe = _extract_easy_summary_from_vibe(variants.vibe)
        if _has_japanese(summary_original):
            summary_ja = summary_original
        elif _has_japanese(summary_from_vibe):
            summary_ja = summary_from_vibe
        else:
            summary_ja = _fallback_summary_ja(
                headline=card.headline,
                topic=topic,
                section=section,
            )

        serialized_cards.append(
            {
                "id": card_item_key,
                "headline": card.headline,
                "topic": topic,
                "section": section,
                "score_total": card.score_total,
                "score_breakdown": card.score_breakdown,
                "source": {
                    "name": card.source_name,
                    "tier": card.source_tier,
                    "url": card.source_url,
                    "published_at": card.published_at.isoformat(),
                    "language": source_item.language,
                },
                "summary": summary_original,
                "summary_original": summary_original,
                "summary_ja": summary_ja,
                "variants": {
                    "raw": variants.raw,
                    "vibe": variants.vibe,
                    "builder": variants.builder,
                },
                "builder_pack": _builder_pack_for_item(
                    item=source_item,
                    topic=topic,
                    section=section,
                ),
                "enrichment": enrichment_meta,
                "generated_at": card.generated_at.isoformat(),
            }
        )

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "cards": serialized_cards,
        "errors": errors,
        "stats": {
            "sources_total": len(settings.sources),
            "items_ingested": len(items),
            "items_after_dedup": len(deduped_items),
            "cards_published": len(serialized_cards),
            "policy_main_feed_minimum_tier": main_min_tier,
            "policy_tier_c_source_limit": tier_c_source_limit,
        },
    }
