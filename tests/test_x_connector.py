import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.connectors.x_connector import fetch_x_items
from src.source_config import SourceDefinition


class XConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = SourceDefinition(
            name="X Signals",
            kind="api",
            tier="C",
            url="https://api.x.com",
            params={"provider": "x", "queries": ["test query"]},
        )

    def test_missing_token_returns_empty_without_error(self):
        with patch.dict(os.environ, {}, clear=True):
            items, err = fetch_x_items(self.source, limit=5)

        self.assertEqual(items, [])
        self.assertIsNone(err)

    def test_maps_tweets_to_source_items(self):
        fake_payload = {
            "data": [
                {
                    "id": "12345",
                    "text": "New AI API release with SDK examples",
                    "created_at": "2026-03-25T00:00:00Z",
                    "lang": "en",
                }
            ]
        }

        with patch.dict(os.environ, {"X_BEARER_TOKEN": "dummy"}, clear=True):
            with patch("src.connectors.x_connector._request_json", return_value=fake_payload):
                items, err = fetch_x_items(self.source, limit=5)

        self.assertIsNone(err)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_tier, "C")
        self.assertEqual(items[0].url, "https://x.com/i/web/status/12345")
        self.assertIsInstance(items[0].published_at, datetime)
        self.assertEqual(items[0].published_at.tzinfo, timezone.utc)


if __name__ == "__main__":
    unittest.main()
