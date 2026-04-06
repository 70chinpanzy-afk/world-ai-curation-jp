from datetime import datetime, timezone

from src.curation_pipeline import SourceItem, rank_items


if __name__ == "__main__":
    sample_items = [
        SourceItem(
            source_name="OpenAI News",
            source_tier="A",
            title="New model release and toolchain updates",
            url="https://example.com/openai-release",
            published_at=datetime(2026, 3, 25, 6, 0, tzinfo=timezone.utc),
            language="en",
            summary="Official release update from an AI lab.",
            novelty_hint=0.8,
            impact_hint=0.9,
            actionability_hint=0.8,
        ),
        SourceItem(
            source_name="X Signals",
            source_tier="C",
            title="Rumor about upcoming benchmark jump",
            url="https://example.com/x-signal",
            published_at=datetime(2026, 3, 25, 7, 0, tzinfo=timezone.utc),
            language="en",
            summary="Unverified social signal that needs confirmation.",
            novelty_hint=0.7,
            impact_hint=0.6,
            actionability_hint=0.3,
        ),
    ]

    ranked = rank_items(sample_items)
    for card in ranked:
        print("=" * 80)
        print(card.headline)
        print("score:", card.score_total)
        print(card.variants.vibe)
