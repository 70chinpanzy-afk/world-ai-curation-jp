import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.persistence import SnapshotPersistence


class SnapshotPersistenceTests(unittest.TestCase):
    def test_file_roundtrip_without_database_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)

            input_snapshot = {
                "generated_at": "2026-03-27T00:00:00+00:00",
                "cards": [{"id": "1"}],
                "errors": [],
                "stats": {"cards_published": 1},
            }

            saved = store.save_snapshot(input_snapshot)
            loaded = store.load_snapshot()

            self.assertEqual(saved["storage"]["backend"], "file")
            self.assertEqual(loaded["cards"][0]["id"], "1")

    def test_invalid_database_url_falls_back_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url="postgresql://invalid-host:5432/db", cache_path=cache_path)

            snapshot = {
                "generated_at": "2026-03-27T00:00:00+00:00",
                "cards": [{"id": "x"}],
                "errors": [],
                "stats": {},
            }

            saved = store.save_snapshot(snapshot)
            self.assertEqual(saved["storage"]["backend"], "file")
            self.assertTrue(cache_path.exists())

    def test_editorial_state_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.editorial_state_path = Path(tmpdir) / "editorial_states.json"

            store.upsert_editorial_state(card_id="card-1", status="draft", is_pinned=True, pin_rank=9)
            states = store.load_editorial_states()

            self.assertIn("card-1", states)
            self.assertEqual(states["card-1"]["status"], "draft")
            self.assertTrue(states["card-1"]["is_pinned"])

    def test_audit_log_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            saved = store.append_audit_log(
                actor="admin",
                action="status_update",
                card_id="card-1",
                details={"from": "published", "to": "draft"},
            )
            logs = store.load_audit_logs(limit=10)

            self.assertEqual(saved["actor"], "admin")
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["card_id"], "card-1")

    def test_audit_log_file_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            store.append_audit_log(actor="admin", action="status_update", card_id="card-1", details={})
            store.append_audit_log(actor="editor", action="pin_update", card_id="card-2", details={})

            logs_action = store.load_audit_logs(limit=10, action="pin_update")
            logs_card = store.load_audit_logs(limit=10, card_id="card-1")
            logs_actor = store.load_audit_logs(limit=10, actor="editor")

            self.assertEqual(len(logs_action), 1)
            self.assertEqual(logs_action[0]["action"], "pin_update")
            self.assertEqual(len(logs_card), 1)
            self.assertEqual(logs_card[0]["card_id"], "card-1")
            self.assertEqual(len(logs_actor), 1)
            self.assertEqual(logs_actor[0]["actor"], "editor")

    def test_audit_log_file_offset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            store.append_audit_log(actor="admin", action="status_update", card_id="card-1", details={})
            store.append_audit_log(actor="admin", action="status_update", card_id="card-2", details={})
            store.append_audit_log(actor="admin", action="status_update", card_id="card-3", details={})

            logs = store.load_audit_logs(limit=1, offset=1)
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["card_id"], "card-2")

    def test_audit_log_file_datetime_range(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            payload = [
                {
                    "id": "1",
                    "timestamp": "2026-03-27T10:00:00+00:00",
                    "actor": "admin",
                    "action": "status_update",
                    "card_id": "card-1",
                    "details": {},
                },
                {
                    "id": "2",
                    "timestamp": "2026-03-28T10:00:00+00:00",
                    "actor": "admin",
                    "action": "status_update",
                    "card_id": "card-2",
                    "details": {},
                },
                {
                    "id": "3",
                    "timestamp": "2026-03-29T10:00:00+00:00",
                    "actor": "admin",
                    "action": "status_update",
                    "card_id": "card-3",
                    "details": {},
                },
            ]
            with store.audit_log_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            logs = store.load_audit_logs(
                limit=10,
                from_timestamp=datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc),
                to_timestamp=datetime(2026, 3, 28, 23, 59, tzinfo=timezone.utc),
            )

            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0]["card_id"], "card-2")

    def test_count_audit_logs_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            store.append_audit_log(actor="admin", action="status_update", card_id="card-1", details={})
            store.append_audit_log(actor="admin", action="pin_update", card_id="card-2", details={})
            store.append_audit_log(actor="editor", action="pin_update", card_id="card-3", details={})

            count_pin = store.count_audit_logs(action="pin_update")
            count_actor = store.count_audit_logs(actor="admin")

            self.assertEqual(count_pin, 2)
            self.assertEqual(count_actor, 2)

    def test_load_audit_stats_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            now = datetime.now(tz=timezone.utc)
            payload = [
                {
                    "id": "1",
                    "timestamp": (now - timedelta(days=1)).isoformat(),
                    "actor": "admin",
                    "action": "status_update",
                    "card_id": "card-1",
                    "details": {},
                },
                {
                    "id": "2",
                    "timestamp": now.isoformat(),
                    "actor": "admin",
                    "action": "pin_update",
                    "card_id": "card-2",
                    "details": {},
                },
            ]
            with store.audit_log_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)

            stats_payload = store.load_audit_stats(days=7)
            self.assertEqual(stats_payload["total_filtered"], 2)
            self.assertEqual(stats_payload["action_counts"]["status_update"], 1)
            self.assertEqual(stats_payload["action_counts"]["pin_update"], 1)
            self.assertEqual(len(stats_payload["daily"]), 7)

    def test_load_audit_top_breakdown_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cards_cache.json"
            store = SnapshotPersistence(database_url=None, cache_path=cache_path)
            store.audit_log_path = Path(tmpdir) / "audit_logs.json"

            store.append_audit_log(actor="admin", action="status_update", card_id="card-1", details={})
            store.append_audit_log(actor="admin", action="status_update", card_id="card-1", details={})
            store.append_audit_log(actor="editor", action="pin_update", card_id="card-2", details={})
            store.append_audit_log(actor="editor", action="pin_update", card_id="card-3", details={})

            breakdown = store.load_audit_top_breakdown(top_limit=2)
            self.assertEqual(breakdown["top_actors"][0]["actor"], "admin")
            self.assertEqual(breakdown["top_actors"][0]["count"], 2)
            self.assertEqual(breakdown["top_cards"][0]["card_id"], "card-1")
            self.assertEqual(breakdown["top_cards"][0]["count"], 2)


if __name__ == "__main__":
    unittest.main()
