import unittest
import os
import json
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.app import _publish_weekly_brief, app


SAMPLE_SNAPSHOT = {
    "generated_at": "2026-03-25T00:00:00+00:00",
    "cards": [
        {
            "id": "abc",
            "headline": "Test headline",
            "topic": "general",
            "section": "main",
            "score_total": 88.0,
            "score_breakdown": {"trust": 0.95, "novelty": 0.8, "impact": 0.9, "actionability": 0.8, "total": 88.0},
            "source": {
                "name": "Test Source",
                "tier": "A",
                "url": "https://example.com",
                "published_at": "2026-03-25T00:00:00+00:00",
            },
            "summary": "Summary",
            "variants": {
                "raw": "raw",
                "vibe": "vibe",
                "builder": "builder",
            },
            "builder_pack": {"difficulty": {"level": "初級"}},
            "generated_at": "2026-03-25T00:00:00+00:00",
        }
    ],
    "errors": [],
    "stats": {"cards_published": 1},
}


class AppTests(unittest.TestCase):
    ADMIN_AUTH = ("admin", "admin")

    def _common_patches(self):
        return [
            patch("src.app.persistence.load_snapshot", return_value=SAMPLE_SNAPSHOT),
            patch("src.app.persistence.save_snapshot", side_effect=lambda s: s),
            patch("src.app.persistence.load_editorial_states", return_value={}),
            patch("src.app.persistence.load_audit_logs", return_value=[]),
        ]

    def test_cards_endpoint_returns_display_text(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4:
                with TestClient(app) as client:
                    res = client.get("/api/cards?audience=builder")
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 1)
                    self.assertEqual(payload["cards"][0]["display_text"], "builder")

    def test_cards_endpoint_filters_by_difficulty(self):
        snapshot = {
            **SAMPLE_SNAPSHOT,
            "cards": [
                {
                    **SAMPLE_SNAPSHOT["cards"][0],
                    "id": "c1",
                    "headline": "Beginner",
                    "builder_pack": {"difficulty": {"level": "初級"}},
                },
                {
                    **SAMPLE_SNAPSHOT["cards"][0],
                    "id": "c2",
                    "headline": "Intermediate",
                    "builder_pack": {"difficulty": {"level": "中級"}},
                },
            ],
        }
        with patch("src.app.refresh_cards", return_value=snapshot):
            p1, p2, p3, p4 = self._common_patches()
            with patch("src.app.persistence.load_snapshot", return_value=snapshot), p2, p3, p4:
                with TestClient(app) as client:
                    res = client.get("/api/cards?difficulty=中級&status=all")
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 1)
                    self.assertEqual(payload["cards"][0]["headline"], "Intermediate")

    def test_admin_cards_endpoint_filters_by_difficulty(self):
        snapshot = {
            **SAMPLE_SNAPSHOT,
            "cards": [
                {
                    **SAMPLE_SNAPSHOT["cards"][0],
                    "id": "c1",
                    "headline": "Advanced",
                    "builder_pack": {"difficulty": {"level": "上級寄り"}},
                },
                {
                    **SAMPLE_SNAPSHOT["cards"][0],
                    "id": "c2",
                    "headline": "Beginner",
                    "builder_pack": {"difficulty": {"level": "初級"}},
                },
            ],
        }
        with patch("src.app.refresh_cards", return_value=snapshot):
            p1, p2, p3, p4 = self._common_patches()
            with patch("src.app.persistence.load_snapshot", return_value=snapshot), p2, p3, p4:
                with TestClient(app) as client:
                    res = client.get("/api/admin/cards?difficulty=上級寄り", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 1)
                    self.assertEqual(payload["cards"][0]["headline"], "Advanced")

    def test_affiliate_links_endpoint_returns_payload(self):
        sample_affiliate = {
            "disclosure": "affiliate disclosure",
            "links": [{"title": "A", "url": "https://example.com/a", "description": "d", "badge": "b"}],
        }
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4, patch("src.app._load_affiliate_payload", return_value=sample_affiliate):
                with TestClient(app) as client:
                    res = client.get("/api/affiliate-links")
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 1)
                    self.assertEqual(payload["disclosure"], "affiliate disclosure")
                    self.assertEqual(payload["links"][0]["title"], "A")

    def test_affiliate_links_json_env_overrides_file(self):
        env_payload = {
            "disclosure": "env disclosure",
            "links": [
                {"title": "Env Link", "url": "https://example.com/env", "description": "env", "badge": "env", "is_active": True}
            ],
        }
        with patch.dict(os.environ, {"AFFILIATE_LINKS_JSON": json.dumps(env_payload)}, clear=False):
            from src.app import _load_affiliate_payload

            loaded = _load_affiliate_payload()
            self.assertEqual(loaded["disclosure"], "env disclosure")
            self.assertEqual(len(loaded["links"]), 1)
            self.assertEqual(loaded["links"][0]["title"], "Env Link")

    def test_affiliate_links_json_env_invalid_falls_back(self):
        with patch.dict(os.environ, {"AFFILIATE_LINKS_JSON": "{invalid"}, clear=False):
            from src.app import _load_affiliate_payload

            loaded = _load_affiliate_payload()
            self.assertIn("disclosure", loaded)
            self.assertIn("links", loaded)

    def test_robots_and_sitemap_use_public_base_url(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4, patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://example.jp"}, clear=False):
                with TestClient(app) as client:
                    robots = client.get("/robots.txt")
                    self.assertEqual(robots.status_code, 200)
                    self.assertIn("Sitemap: https://example.jp/sitemap.xml", robots.text)

                    sitemap = client.get("/sitemap.xml")
                    self.assertEqual(sitemap.status_code, 200)
                    self.assertIn("<loc>https://example.jp/</loc>", sitemap.text)

    def test_index_includes_canonical_base_url(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4, patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://example.jp"}, clear=False):
                with TestClient(app) as client:
                    res = client.get("/")
                    self.assertEqual(res.status_code, 200)
                    self.assertIn('href="https://example.jp/"', res.text)
                    self.assertNotIn("__PUBLIC_BASE_URL__", res.text)

    def test_feed_and_legal_pages_are_available(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4, patch.dict(os.environ, {"PUBLIC_BASE_URL": "https://example.jp"}, clear=False):
                with TestClient(app) as client:
                    feed = client.get("/feed.xml")
                    self.assertEqual(feed.status_code, 200)
                    self.assertIn("<rss version=", feed.text)
                    self.assertIn("Test headline", feed.text)

                    rss_alias = client.get("/rss.xml")
                    self.assertEqual(rss_alias.status_code, 200)
                    self.assertIn("<rss version=", rss_alias.text)

                    privacy = client.get("/privacy")
                    self.assertEqual(privacy.status_code, 200)
                    self.assertIn("プライバシーポリシー", privacy.text)
                    self.assertNotIn("__PUBLIC_BASE_URL__", privacy.text)

                    terms = client.get("/terms")
                    self.assertEqual(terms.status_code, 200)
                    self.assertIn("利用規約", terms.text)

                    disclosure = client.get("/affiliate-disclosure")
                    self.assertEqual(disclosure.status_code, 200)
                    self.assertIn("アフィリエイト開示", disclosure.text)

    def test_refresh_endpoint_returns_ok(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4:
                with TestClient(app) as client:
                    res = client.post("/api/refresh")
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["total"], 1)

    def test_admin_status_and_pin_endpoints(self):
        updated_state = {"status": "draft", "is_pinned": True, "pin_rank": 7, "updated_at": None}

        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, _, p4 = self._common_patches()
            with p1, p2, patch(
                "src.app.persistence.load_editorial_states", return_value={}
            ), patch("src.app.persistence.upsert_editorial_state", return_value=updated_state), patch(
                "src.app.persistence.append_audit_log", return_value={"id": "x"}
            ), p4:
                with TestClient(app) as client:
                    res1 = client.post("/api/admin/cards/abc/status", json={"status": "draft"}, auth=self.ADMIN_AUTH)
                    self.assertEqual(res1.status_code, 200)
                    self.assertTrue(res1.json()["ok"])

                    res2 = client.post(
                        "/api/admin/cards/abc/pin",
                        json={"pinned": True, "pin_rank": 7},
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res2.status_code, 200)
                    self.assertTrue(res2.json()["ok"])

    def test_admin_requires_auth(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, p4 = self._common_patches()
            with p1, p2, p3, p4:
                with TestClient(app) as client:
                    res = client.get("/api/admin/cards")
                    self.assertEqual(res.status_code, 401)

    def test_admin_audit_endpoint_with_auth(self):
        logs = [{"id": "1", "action": "status_update"}]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_logs", return_value=logs) as p_logs, patch(
                "src.app.persistence.count_audit_logs", return_value=7
            ) as p_count:
                with TestClient(app) as client:
                    res = client.get(
                        "/api/admin/audit?limit=10&offset=20&action=status_update&card_id=abc&actor=admin"
                        "&from_ts=2026-03-27T00:00:00%2B00:00&to_ts=2026-03-28T00:00:00%2B00:00",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 1)
                    self.assertEqual(payload["total_filtered"], 7)
                    self.assertEqual(payload["offset"], 20)
                    self.assertFalse(payload["has_more"])
                    p_logs.assert_called_once_with(
                        limit=11,
                        offset=20,
                        action="status_update",
                        card_id="abc",
                        actor="admin",
                        from_timestamp=datetime(2026, 3, 27, 0, 0, tzinfo=timezone.utc),
                        to_timestamp=datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc),
                    )
                    p_count.assert_called_once_with(
                        action="status_update",
                        card_id="abc",
                        actor="admin",
                        from_timestamp=datetime(2026, 3, 27, 0, 0, tzinfo=timezone.utc),
                        to_timestamp=datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc),
                    )

    def test_admin_audit_csv_endpoint_with_auth(self):
        logs = [
            {
                "id": "1",
                "timestamp": "2026-03-27T00:00:00+00:00",
                "actor": "admin",
                "action": "pin_update",
                "card_id": "abc",
                "details": {"to_is_pinned": True},
            }
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_logs", return_value=logs) as p_logs:
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit.csv?limit=10", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.headers["content-type"].startswith("text/csv"))
                    self.assertIn("id,timestamp,actor,action,card_id,details_json", res.text)
                    self.assertIn("pin_update", res.text)
                    p_logs.assert_called_once_with(
                        limit=10,
                        offset=0,
                        action=None,
                        card_id=None,
                        actor=None,
                        from_timestamp=None,
                        to_timestamp=None,
                    )

    def test_admin_audit_endpoint_has_more(self):
        logs = [
            {"id": "1", "action": "status_update"},
            {"id": "2", "action": "status_update"},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_logs", return_value=logs), patch(
                "src.app.persistence.count_audit_logs", return_value=2
            ):
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit?limit=1", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["returned"], 1)
                    self.assertTrue(payload["has_more"])
                    self.assertEqual(payload["total_filtered"], 2)

    def test_admin_audit_endpoint_invalid_date_range(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_logs", return_value=[]):
                with TestClient(app) as client:
                    res = client.get(
                        "/api/admin/audit?from_ts=2026-03-29T00:00:00%2B00:00&to_ts=2026-03-28T00:00:00%2B00:00",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 422)

    def test_admin_audit_stats_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 3,
            "action_counts": {"status_update": 2, "pin_update": 1},
            "daily": [{"day": "2026-03-28", "status_update": 1, "pin_update": 0, "other": 0, "total": 1}],
        }
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload) as p_stats:
                with TestClient(app) as client:
                    res = client.get(
                        "/api/admin/audit/stats?days=14&action=pin_update&from_ts=2026-03-01T00:00:00%2B00:00",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["days"], 14)
                    self.assertEqual(payload["total_filtered"], 3)
                    self.assertEqual(payload["action_counts"]["pin_update"], 1)
                    p_stats.assert_called_once_with(
                        days=14,
                        action="pin_update",
                        card_id=None,
                        actor=None,
                        from_timestamp=datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc),
                        to_timestamp=None,
                    )

    def test_admin_audit_stats_endpoint_invalid_date_range(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value={}):
                with TestClient(app) as client:
                    res = client.get(
                        "/api/admin/audit/stats?from_ts=2026-03-29T00:00:00%2B00:00&to_ts=2026-03-28T00:00:00%2B00:00",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 422)

    def test_admin_audit_trend_csv_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 3,
            "action_counts": {"status_update": 2, "pin_update": 1},
            "daily": [
                {"day": "2026-03-27", "status_update": 1, "pin_update": 0, "other": 0, "total": 1},
                {"day": "2026-03-28", "status_update": 1, "pin_update": 1, "other": 0, "total": 2},
            ],
        }
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload) as p_stats:
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/trend.csv?days=14&action=status_update", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.headers["content-type"].startswith("text/csv"))
                    self.assertIn("day,status_update,pin_update,other,total", res.text)
                    self.assertIn("2026-03-28,1,1,0,2", res.text)
                    self.assertIn("metric,value", res.text)
                    p_stats.assert_called_once_with(
                        days=14,
                        action="status_update",
                        card_id=None,
                        actor=None,
                        from_timestamp=None,
                        to_timestamp=None,
                    )

    def test_admin_audit_weekly_report_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 4,
            "action_counts": {"status_update": 3, "pin_update": 1},
            "daily": [
                {"day": "2026-03-27", "status_update": 2, "pin_update": 0, "other": 0, "total": 2},
                {"day": "2026-03-28", "status_update": 1, "pin_update": 1, "other": 0, "total": 2},
            ],
        }
        top_payload = {
            "top_actors": [{"actor": "admin", "count": 3}],
            "top_cards": [{"card_id": "abc", "count": 2}],
        }
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload) as p_stats, patch(
                "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
            ) as p_top:
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/weekly-report?days=7&top_limit=3", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["days"], 7)
                    self.assertEqual(payload["total_filtered"], 4)
                    self.assertEqual(payload["busiest_day"]["day"], "2026-03-27")
                    self.assertEqual(payload["top_actors"][0]["actor"], "admin")
                    self.assertTrue(isinstance(payload["highlights"], list))
                    self.assertTrue(isinstance(payload["playbook_for_vibe_coders"], list))
                    p_stats.assert_called_once_with(
                        days=7,
                        action=None,
                        card_id=None,
                        actor=None,
                        from_timestamp=None,
                        to_timestamp=None,
                    )
                    p_top.assert_called_once_with(
                        top_limit=3,
                        action=None,
                        card_id=None,
                        actor=None,
                        from_timestamp=None,
                        to_timestamp=None,
                    )

    def test_admin_audit_weekly_report_endpoint_invalid_date_range(self):
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value={}):
                with TestClient(app) as client:
                    res = client.get(
                        "/api/admin/audit/weekly-report?from_ts=2026-03-29T00:00:00%2B00:00&to_ts=2026-03-28T00:00:00%2B00:00",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 422)

    def test_admin_audit_weekly_report_md_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 2,
            "action_counts": {"status_update": 1, "pin_update": 1},
            "daily": [{"day": "2026-03-28", "status_update": 1, "pin_update": 1, "other": 0, "total": 2}],
        }
        top_payload = {"top_actors": [{"actor": "admin", "count": 2}], "top_cards": [{"card_id": "abc", "count": 1}]}
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload), patch(
                "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
            ):
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/weekly-report.md?days=7", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.headers["content-type"].startswith("text/markdown"))
                    self.assertIn("Weekly Audit Brief", res.text)
                    self.assertIn("Highlights", res.text)

    def test_admin_audit_weekly_report_write_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 1,
            "action_counts": {"status_update": 1},
            "daily": [{"day": "2026-03-28", "status_update": 1, "pin_update": 0, "other": 0, "total": 1}],
        }
        top_payload = {"top_actors": [{"actor": "admin", "count": 1}], "top_cards": [{"card_id": "abc", "count": 1}]}
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload), patch(
                "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
            ), patch(
                "src.app._write_weekly_report_artifacts",
                return_value={"json_path": "/tmp/brief.json", "md_path": "/tmp/brief.md"},
            ) as p_write:
                with TestClient(app) as client:
                    res = client.post(
                        "/api/admin/audit/weekly-report/write?days=7&top_limit=5&archive=false",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertFalse(payload["archive"])
                    self.assertFalse(payload["published"])
                    self.assertEqual(payload["json_path"], "/tmp/brief.json")
                    self.assertEqual(payload["md_path"], "/tmp/brief.md")
                    self.assertEqual(payload["total_filtered"], 1)
                    p_write.assert_called_once()
                    self.assertEqual(p_write.call_args.kwargs["archive"], False)

    def test_admin_audit_weekly_report_write_endpoint_with_publish(self):
        stats_payload = {
            "total_filtered": 1,
            "action_counts": {"status_update": 1},
            "daily": [{"day": "2026-03-28", "status_update": 1, "pin_update": 0, "other": 0, "total": 1}],
        }
        top_payload = {"top_actors": [{"actor": "admin", "count": 1}], "top_cards": [{"card_id": "abc", "count": 1}]}
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload), patch(
                "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
            ), patch(
                "src.app._write_weekly_report_artifacts",
                return_value={"json_path": "/tmp/brief.json", "md_path": "/tmp/brief.md"},
            ) as p_write, patch(
                "src.app._publish_weekly_brief", return_value={"slack": "ok", "notion": "skipped"}
            ) as p_publish:
                with TestClient(app) as client:
                    res = client.post(
                        "/api/admin/audit/weekly-report/write?days=7&top_limit=5&archive=false&publish=true",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertTrue(payload["published"])
                    self.assertEqual(payload["publish"]["slack"], "ok")
                    p_write.assert_called_once()
                    p_publish.assert_called_once()

    def test_admin_audit_weekly_report_publish_endpoint_with_auth(self):
        stats_payload = {
            "total_filtered": 2,
            "action_counts": {"status_update": 2},
            "daily": [{"day": "2026-03-28", "status_update": 2, "pin_update": 0, "other": 0, "total": 2}],
        }
        top_payload = {"top_actors": [{"actor": "admin", "count": 2}], "top_cards": [{"card_id": "abc", "count": 1}]}
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app.persistence.load_audit_stats", return_value=stats_payload), patch(
                "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
            ), patch(
                "src.app._publish_weekly_brief", return_value={"slack": "ok", "notion": "ok"}
            ) as p_publish, patch(
                "src.app._write_weekly_report_artifacts",
                return_value={"json_path": "/tmp/brief.json", "md_path": "/tmp/brief.md"},
            ) as p_write:
                with TestClient(app) as client:
                    res = client.post(
                        "/api/admin/audit/weekly-report/publish?days=7&top_limit=5&save=true&archive=false",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertTrue(payload["saved"])
                    self.assertEqual(payload["publish"]["notion"], "ok")
                    self.assertEqual(payload["json_path"], "/tmp/brief.json")
                    p_publish.assert_called_once()
                    p_write.assert_called_once()
                    self.assertEqual(p_write.call_args.kwargs["archive"], False)

    def test_refresh_endpoint_auto_post_weekly_brief(self):
        stats_payload = {
            "total_filtered": 1,
            "action_counts": {"status_update": 1},
            "daily": [{"day": "2026-03-28", "status_update": 1, "pin_update": 0, "other": 0, "total": 1}],
        }
        top_payload = {"top_actors": [{"actor": "admin", "count": 1}], "top_cards": [{"card_id": "abc", "count": 1}]}
        env_patch = {
            "AUTO_REFRESH_ON_START": "0",
            "AUTO_WRITE_WEEKLY_BRIEF": "0",
            "AUTO_POST_WEEKLY_BRIEF": "1",
            "WEEKLY_BRIEF_DAYS": "7",
            "WEEKLY_BRIEF_TOP_LIMIT": "5",
        }
        with patch.dict(os.environ, env_patch, clear=False):
            with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
                p1, p2, p3, p4 = self._common_patches()
                with p1, p2, p3, p4, patch("src.app.persistence.load_audit_stats", return_value=stats_payload), patch(
                    "src.app.persistence.load_audit_top_breakdown", return_value=top_payload
                ), patch("src.app._publish_weekly_brief", return_value={"slack": "ok"}) as p_publish, patch(
                    "src.app._write_weekly_report_artifacts"
                ) as p_write:
                    with TestClient(app) as client:
                        res = client.post("/api/refresh")
                        self.assertEqual(res.status_code, 200)
                        self.assertTrue(res.json()["ok"])
                        p_publish.assert_called_once()
                        p_write.assert_not_called()

    def test_admin_audit_weekly_report_history_endpoint_with_auth(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00", "total_filtered": 5},
            {"saved_at": "2026-03-27T00:00:00+00:00", "total_filtered": 3},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows):
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/weekly-report/history?limit=1", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["total"], 2)
                    self.assertEqual(payload["total_filtered"], 2)
                    self.assertEqual(payload["limit"], 1)
                    self.assertEqual(len(payload["items"]), 1)
                    self.assertEqual(payload["items"][0]["total_filtered"], 5)

    def test_admin_audit_weekly_report_history_csv_endpoint_with_auth(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00", "generated_at": "2026-03-28T00:00:00+00:00", "days": 7, "total_filtered": 5},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows):
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/weekly-report/history.csv?limit=10", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    self.assertTrue(res.headers["content-type"].startswith("text/csv"))
                    self.assertIn("saved_at,generated_at,days,total_filtered", res.text)
                    self.assertIn("2026-03-28T00:00:00+00:00", res.text)

    def test_admin_audit_weekly_report_history_delete_endpoint_with_auth(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00", "total_filtered": 5},
            {"saved_at": "2026-03-27T00:00:00+00:00", "total_filtered": 3},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows), patch(
                "src.app._save_weekly_brief_history"
            ) as p_save:
                with TestClient(app) as client:
                    bad = client.delete("/api/admin/audit/weekly-report/history", auth=self.ADMIN_AUTH)
                    self.assertEqual(bad.status_code, 400)

                    res = client.delete(
                        "/api/admin/audit/weekly-report/history?confirm=true&q=2026-03-27",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["deleted"], 1)
                    self.assertEqual(payload["remaining"], 1)
                    p_save.assert_called_once()

    def test_admin_audit_weekly_report_history_delete_keep_latest(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00", "total_filtered": 5},
            {"saved_at": "2026-03-27T00:00:00+00:00", "total_filtered": 3},
            {"saved_at": "2026-03-26T00:00:00+00:00", "total_filtered": 2},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows), patch(
                "src.app._save_weekly_brief_history"
            ) as p_save:
                with TestClient(app) as client:
                    res = client.delete(
                        "/api/admin/audit/weekly-report/history?confirm=true&keep_latest=1",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["deleted"], 2)
                    self.assertEqual(payload["remaining"], 1)
                    p_save.assert_called_once()
                    saved_rows = p_save.call_args.args[0]
                    self.assertEqual(len(saved_rows), 1)
                    self.assertEqual(saved_rows[0]["saved_at"], "2026-03-28T00:00:00+00:00")

    def test_admin_audit_weekly_report_history_cleanup_endpoint_with_auth(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00"},
            {"saved_at": "2026-03-27T00:00:00+00:00"},
            {"saved_at": "2026-03-26T00:00:00+00:00"},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows), patch(
                "src.app._save_weekly_brief_history"
            ) as p_save:
                with TestClient(app) as client:
                    bad = client.post("/api/admin/audit/weekly-report/history/cleanup", auth=self.ADMIN_AUTH)
                    self.assertEqual(bad.status_code, 400)

                    res = client.post(
                        "/api/admin/audit/weekly-report/history/cleanup?confirm=true&keep_latest=2",
                        auth=self.ADMIN_AUTH,
                    )
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertTrue(payload["ok"])
                    self.assertEqual(payload["deleted"], 1)
                    self.assertEqual(payload["remaining"], 2)
                    p_save.assert_called_once()

    def test_admin_audit_weekly_report_history_sort_asc(self):
        history_rows = [
            {"saved_at": "2026-03-28T00:00:00+00:00", "total_filtered": 5},
            {"saved_at": "2026-03-27T00:00:00+00:00", "total_filtered": 3},
        ]
        with patch("src.app.refresh_cards", return_value=SAMPLE_SNAPSHOT):
            p1, p2, p3, _ = self._common_patches()
            with p1, p2, p3, patch("src.app._load_weekly_brief_history", return_value=history_rows):
                with TestClient(app) as client:
                    res = client.get("/api/admin/audit/weekly-report/history?sort=asc", auth=self.ADMIN_AUTH)
                    self.assertEqual(res.status_code, 200)
                    payload = res.json()
                    self.assertEqual(payload["sort"], "asc")
                    self.assertEqual(payload["items"][0]["saved_at"], "2026-03-27T00:00:00+00:00")

    def test_publish_weekly_brief_uses_patch_for_notion(self):
        payload = {"days": 7, "total_filtered": 1, "highlights": ["test"]}
        env_patch = {
            "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/TOKEN/TEST/TEST",
            "NOTION_API_TOKEN": "ntn_test",
            "NOTION_PAGE_ID": "33113622-d7c7-8089-8b12-fd9c3d87a3e2",
        }
        with patch.dict(os.environ, env_patch, clear=False), patch("src.app._http_post_json") as p_http:
            result = _publish_weekly_brief(payload)
            self.assertEqual(result["slack"], "ok")
            self.assertEqual(result["notion"], "ok")
            self.assertEqual(p_http.call_count, 2)
            self.assertEqual(p_http.call_args_list[1].kwargs.get("method"), "PATCH")


if __name__ == "__main__":
    unittest.main()
