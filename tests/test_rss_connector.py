import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.connectors.rss_connector import fetch_rss_items
from src.source_config import SourceDefinition


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class RSSConnectorTests(unittest.TestCase):
    def test_website_fallback_extracts_article_links(self):
        source = SourceDefinition(
            name="Anthropic News",
            kind="website",
            tier="A",
            url="https://www.anthropic.com/news",
        )
        fake_parsed = SimpleNamespace(
            bozo=True,
            bozo_exception=ValueError("invalid token"),
            entries=[],
            feed=SimpleNamespace(language="en"),
        )
        fake_html = """
        <html><body>
          <a href="/news/claude-opus-4-6">Introducing Claude Opus 4.6</a>
          <a href="/news/claude-sonnet-4-6">Introducing Claude Sonnet 4.6</a>
        </body></html>
        """

        with patch("src.connectors.rss_connector.feedparser.parse", return_value=fake_parsed), patch(
            "src.connectors.rss_connector.urllib.request.urlopen",
            return_value=_FakeResponse(fake_html),
        ):
            items, err = fetch_rss_items(source, limit=5)

        self.assertIsNone(err)
        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(items[0].source_name, "Anthropic News")
        self.assertTrue(items[0].url.startswith("https://www.anthropic.com/news/"))

    def test_rss_invalid_feed_returns_error(self):
        source = SourceDefinition(
            name="Broken RSS",
            kind="rss",
            tier="B",
            url="https://example.com/feed.xml",
        )
        fake_parsed = SimpleNamespace(
            bozo=True,
            bozo_exception=ValueError("broken xml"),
            entries=[],
            feed=SimpleNamespace(language="en"),
        )

        with patch("src.connectors.rss_connector.feedparser.parse", return_value=fake_parsed):
            items, err = fetch_rss_items(source, limit=5)

        self.assertEqual(items, [])
        self.assertIn("RSS parse failed", err)


if __name__ == "__main__":
    unittest.main()

