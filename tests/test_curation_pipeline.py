import unittest
from datetime import datetime, timezone

from src.curation_pipeline import SourceItem, build_variants, rank_items, score_item


class CurationPipelineTests(unittest.TestCase):
    def test_tier_a_scores_higher_than_tier_c_when_other_signals_equal(self):
        published = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)

        item_a = SourceItem(
            source_name="Tier A",
            source_tier="A",
            title="A",
            url="https://a.example.com",
            published_at=published,
            language="en",
            summary="A",
            novelty_hint=0.5,
            impact_hint=0.5,
            actionability_hint=0.5,
        )
        item_c = SourceItem(
            source_name="Tier C",
            source_tier="C",
            title="C",
            url="https://c.example.com",
            published_at=published,
            language="en",
            summary="C",
            novelty_hint=0.5,
            impact_hint=0.5,
            actionability_hint=0.5,
        )

        self.assertGreater(score_item(item_a)["total"], score_item(item_c)["total"])

    def test_rank_items_orders_by_score_desc(self):
        published = datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)

        high = SourceItem(
            source_name="A",
            source_tier="A",
            title="High",
            url="https://high.example.com",
            published_at=published,
            language="en",
            summary="High",
            novelty_hint=0.9,
            impact_hint=0.9,
            actionability_hint=0.9,
        )
        low = SourceItem(
            source_name="C",
            source_tier="C",
            title="Low",
            url="https://low.example.com",
            published_at=published,
            language="en",
            summary="Low",
            novelty_hint=0.3,
            impact_hint=0.3,
            actionability_hint=0.3,
        )

        ranked = rank_items([low, high])
        self.assertEqual(ranked[0].headline, "High")

    def test_tier_c_vibe_variant_contains_unverified_caveat(self):
        item = SourceItem(
            source_name="X Signals",
            source_tier="C",
            title="Signal",
            url="https://signal.example.com",
            published_at=datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc),
            language="en",
            summary="Signal",
        )

        variants = build_variants(item)
        self.assertIn("未検証", variants.vibe)


if __name__ == "__main__":
    unittest.main()
