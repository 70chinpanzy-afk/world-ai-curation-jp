"""Starter curation pipeline logic (no external dependencies)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List


TIER_TRUST = {
    "A": 0.95,
    "B": 0.75,
    "C": 0.45,
}


@dataclass
class SourceItem:
    source_name: str
    source_tier: str
    title: str
    url: str
    published_at: datetime
    language: str
    summary: str
    novelty_hint: float = 0.5
    impact_hint: float = 0.5
    actionability_hint: float = 0.5


@dataclass
class CardVariants:
    raw: str
    vibe: str
    builder: str


@dataclass
class CuratedCard:
    headline: str
    source_name: str
    source_tier: str
    published_at: datetime
    score_total: float
    score_breakdown: Dict[str, float]
    variants: CardVariants
    source_url: str
    generated_at: datetime


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def score_item(item: SourceItem) -> Dict[str, float]:
    trust = TIER_TRUST.get(item.source_tier, 0.4)
    novelty = clamp(item.novelty_hint)
    impact = clamp(item.impact_hint)
    actionability = clamp(item.actionability_hint)

    total = (
        trust * 0.35
        + novelty * 0.20
        + impact * 0.25
        + actionability * 0.20
    )

    return {
        "trust": round(trust, 3),
        "novelty": round(novelty, 3),
        "impact": round(impact, 3),
        "actionability": round(actionability, 3),
        "total": round(total * 100, 2),
    }


def _jargon_hints(title: str, summary: str) -> List[str]:
    text = f"{title} {summary}".lower()
    glossary = {
        "api": "API: サービス同士をつなぐための窓口です。",
        "sdk": "SDK: 開発を楽にする部品セットです。",
        "agent": "エージェント: 指示を受けて自動で作業を進める仕組みです。",
        "benchmark": "ベンチマーク: 性能を比較するためのテストです。",
        "open source": "オープンソース: 中身が公開され、誰でも改善に参加できます。",
        "dataset": "データセット: 学習や検証に使うデータのまとまりです。",
        "fine-tuning": "ファインチューニング: 既存モデルを目的に合わせて追加調整することです。",
    }
    lines: List[str] = []
    for key, desc in glossary.items():
        if key in text:
            lines.append(f"- {desc}")
    return lines[:3]


def _easy_action_steps(trust: float) -> List[str]:
    if trust >= 0.7:
        return [
            "1) まず1分で: タイトルを『誰に何が良くなる話か』に言い換える",
            "2) 次の10分で: 自分の作りたいものに当てはまる機能を1つ決める",
            "3) 次の20分で: 画面モック or API呼び出し1本だけ動かしてみる",
        ]
    return [
        "1) まず5分で: 公式発表があるかを確認する",
        "2) 次の10分で: 本番ではなく検証メモを作る",
        "3) 次の15分で: 裏取り後に試す小さな実験案を1つ決める",
    ]


def build_variants(item: SourceItem) -> CardVariants:
    trust = TIER_TRUST.get(item.source_tier, 0.4)
    jargon = _jargon_hints(item.title, item.summary)
    action_steps = _easy_action_steps(trust)

    raw = (
        f"[Raw] {item.title}\n"
        f"Source: {item.source_name} ({item.source_tier})\n"
        f"Published: {item.published_at.isoformat()}\n"
        f"Summary: {item.summary}\n"
        f"URL: {item.url}"
    )

    if trust >= 0.7:
        vibe = (
            f"[Vibe]\n"
            f"タイトル: {item.title}\n"
            f"やさしい要約: {item.summary}\n"
            "なぜ大事？: 海外の一次情報に近い更新なので、先に動ける可能性があります。\n"
            "今日やること:\n"
            f"{action_steps[0]}\n"
            f"{action_steps[1]}\n"
            f"{action_steps[2]}\n"
            "専門用語ミニ辞典:\n"
            + ("\n".join(jargon) if jargon else "- 難しい単語が出たら、Builder PlaybookのNo-code Pathから始めるのがおすすめです。")
        )
    else:
        vibe = (
            f"[Vibe]\n"
            f"タイトル: {item.title}\n"
            f"やさしい要約: {item.summary}\n"
            "注意: これは未検証のシグナル情報です。\n"
            "今日できること:\n"
            f"{action_steps[0]}\n"
            f"{action_steps[1]}\n"
            f"{action_steps[2]}\n"
            "専門用語ミニ辞典:\n"
            + ("\n".join(jargon) if jargon else "- まずは公式発表の有無を確認してから判断しましょう。")
        )

    builder = (
        f"[Builder]\n"
        f"タイトル: {item.title}\n"
        "実装観点（やさしめ）:\n"
        "- まず誰のどんな手間が減るか\n"
        "- 既存の画面/運用にどう足すか\n"
        "- コストと速度が許容範囲か\n"
        "実装チェック:\n"
        "1) 30分で動く最小版を作る\n"
        "2) うまくいかない時の代替手段を決める\n"
        "3) 本番前に一次情報で最終確認する"
    )

    return CardVariants(raw=raw, vibe=vibe, builder=builder)


def curate_item(item: SourceItem) -> CuratedCard:
    score = score_item(item)
    variants = build_variants(item)

    return CuratedCard(
        headline=item.title,
        source_name=item.source_name,
        source_tier=item.source_tier,
        published_at=item.published_at,
        score_total=score["total"],
        score_breakdown=score,
        variants=variants,
        source_url=item.url,
        generated_at=datetime.now(tz=timezone.utc),
    )


def rank_items(items: List[SourceItem]) -> List[CuratedCard]:
    cards = [curate_item(item) for item in items]
    cards.sort(key=lambda card: card.score_total, reverse=True)
    return cards
