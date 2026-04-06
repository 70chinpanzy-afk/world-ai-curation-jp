import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.curation_pipeline import SourceItem
from src.engine import refresh_cards


class EngineTests(unittest.TestCase):
    def _make_config(self, path: Path) -> None:
        path.write_text(
            """
version: 1
policy:
  main_feed_minimum_tier: B
sources:
  - name: "Tier A RSS"
    kind: "rss"
    tier: "A"
    url: "https://example.com/a.xml"
  - name: "Tier C RSS"
    kind: "rss"
    tier: "C"
    url: "https://example.com/c.xml"
""".strip(),
            encoding="utf-8",
        )

    def test_tier_c_stays_in_signals_without_confirmation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            self._make_config(config_path)

            def fake_fetch(source, limit):
                if source.tier == "A":
                    return [
                        SourceItem(
                            source_name=source.name,
                            source_tier=source.tier,
                            title="Official API release",
                            url="https://example.com/a-release",
                            published_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
                            language="en",
                            summary="Primary-source release note",
                        )
                    ], None

                return [
                    SourceItem(
                        source_name=source.name,
                        source_tier=source.tier,
                        title="Rumor from social post",
                        url="https://example.com/c-rumor",
                        published_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
                        language="en",
                        summary="Unverified rumor",
                    )
                ], None

            with patch("src.engine.fetch_rss_items", side_effect=fake_fetch):
                snapshot = refresh_cards(config_path=config_path, limit_per_source=5)

            by_title = {card["headline"]: card for card in snapshot["cards"]}
            self.assertEqual(by_title["Official API release"]["section"], "main")
            self.assertEqual(by_title["Rumor from social post"]["section"], "signals")
            self.assertIn("builder_pack", by_title["Official API release"])
            self.assertIn("prototype_30m", by_title["Official API release"]["builder_pack"])
            self.assertTrue(isinstance(by_title["Official API release"]["builder_pack"]["prototype_30m"], list))
            self.assertIn("difficulty", by_title["Official API release"]["builder_pack"])
            self.assertIn("for_non_engineers", by_title["Official API release"]["builder_pack"])
            self.assertTrue(
                isinstance(
                    by_title["Official API release"]["builder_pack"]["for_non_engineers"].get("no_code_path"),
                    list,
                )
            )

    def test_x_provider_source_is_supported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
version: 1
policy: {}
sources:
  - name: "X Signals"
    kind: "api"
    tier: "C"
    url: "https://api.x.com"
    params:
      provider: "x"
""".strip(),
                encoding="utf-8",
            )

            with patch("src.engine.fetch_x_items", return_value=([], "x test path")) as mock_fetch_x:
                snapshot = refresh_cards(config_path=config_path, limit_per_source=5)

            self.assertEqual(mock_fetch_x.call_count, 1)
            self.assertTrue(any("x test path" in e for e in snapshot["errors"]))

    def test_dedup_prefers_higher_tier_source_for_same_story(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            self._make_config(config_path)

            long_title = "Official model release introduces new coding agent capabilities for production teams"

            def fake_fetch(source, limit):
                if source.tier == "A":
                    return [
                        SourceItem(
                            source_name=source.name,
                            source_tier=source.tier,
                            title=long_title,
                            url="https://example.com/a-release",
                            published_at=datetime(2026, 3, 25, 1, 0, tzinfo=timezone.utc),
                            language="en",
                            summary="Primary release notes",
                        )
                    ], None

                return [
                    SourceItem(
                        source_name=source.name,
                        source_tier=source.tier,
                        title=long_title,
                        url="https://another.example.com/c-signal",
                        published_at=datetime(2026, 3, 25, 2, 0, tzinfo=timezone.utc),
                        language="en",
                        summary="Social rumor copy",
                    )
                ], None

            with patch("src.engine.fetch_rss_items", side_effect=fake_fetch):
                snapshot = refresh_cards(config_path=config_path, limit_per_source=5)

            matched = [card for card in snapshot["cards"] if card["headline"] == long_title]
            self.assertEqual(len(matched), 1)
            self.assertEqual(matched[0]["source"]["tier"], "A")

    def test_tier_c_source_limit_policy_is_applied(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "sources.yaml"
            config_path.write_text(
                """
version: 1
policy:
  tier_c_max_items_per_source: 2
sources:
  - name: "Tier C RSS"
    kind: "rss"
    tier: "C"
    url: "https://example.com/c.xml"
""".strip(),
                encoding="utf-8",
            )

            observed_limits = []

            def fake_fetch(source, limit):
                observed_limits.append(limit)
                return [
                    SourceItem(
                        source_name=source.name,
                        source_tier=source.tier,
                        title=f"Signal {i}",
                        url=f"https://example.com/signal-{i}",
                        published_at=datetime(2026, 3, 25, tzinfo=timezone.utc),
                        language="en",
                        summary="Signal item",
                    )
                    for i in range(limit)
                ], None

            with patch("src.engine.fetch_rss_items", side_effect=fake_fetch):
                snapshot = refresh_cards(config_path=config_path, limit_per_source=10)

            self.assertEqual(observed_limits, [2])
            self.assertEqual(snapshot["stats"]["policy_tier_c_source_limit"], 2)


if __name__ == "__main__":
    unittest.main()
