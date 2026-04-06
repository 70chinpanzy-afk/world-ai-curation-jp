import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.curation_pipeline import CardVariants, SourceItem
from src.llm_enricher import enrich_variants


class LLMEnricherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = SourceItem(
            source_name="Test Source",
            source_tier="A",
            title="Test Title",
            url="https://example.com",
            published_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
            language="en",
            summary="Test summary",
        )
        self.base = CardVariants(raw="raw", vibe="vibe", builder="builder")

    def test_provider_none_keeps_base(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "none"}, clear=True):
            variants, meta = enrich_variants(self.item, self.base, {"total": 80.0})

        self.assertEqual(variants.raw, "raw")
        self.assertFalse(meta["enabled"])

    def test_openai_without_key_falls_back(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=True):
            variants, meta = enrich_variants(self.item, self.base, {"total": 80.0})

        self.assertEqual(variants.builder, "builder")
        self.assertFalse(meta["enabled"])
        self.assertEqual(meta["provider"], "openai")


if __name__ == "__main__":
    unittest.main()
