"""Snapshot persistence with Postgres-first fallback to JSON file."""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import CACHE_PATH, load_snapshot as load_file_snapshot, save_snapshot as save_file_snapshot


DEFAULT_SNAPSHOT: Dict[str, Any] = {
    "generated_at": None,
    "cards": [],
    "errors": [],
    "stats": {},
}
EDITORIAL_STATE_PATH = CACHE_PATH.parent / "editorial_states.json"
AUDIT_LOG_PATH = CACHE_PATH.parent / "audit_logs.json"
DEFAULT_EDITORIAL_STATE = {
    "status": "published",
    "is_pinned": False,
    "pin_rank": 1000,
}
MAX_AUDIT_LOGS_FILE = 5000


class SnapshotPersistence:
    def __init__(self, database_url: str | None = None, cache_path: Path | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self.cache_path = cache_path or CACHE_PATH
        self.editorial_state_path = EDITORIAL_STATE_PATH
        self.audit_log_path = AUDIT_LOG_PATH
        self.backend = "file"
        self.last_warning: Optional[str] = None

        self._psycopg = None
        if self.database_url:
            try:
                import psycopg  # type: ignore

                self._psycopg = psycopg
                self.backend = "postgres"
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"psycopg import failed; fallback to file storage: {exc}"

    def _merge_defaults(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(DEFAULT_SNAPSHOT)
        merged.update(snapshot or {})
        return merged

    def _normalize_editorial_state(self, raw: Dict[str, Any] | None) -> Dict[str, Any]:
        state = dict(DEFAULT_EDITORIAL_STATE)
        if raw:
            state.update(raw)
        return {
            "status": str(state.get("status", "published")),
            "is_pinned": bool(state.get("is_pinned", False)),
            "pin_rank": int(state.get("pin_rank", 1000)),
            "updated_at": state.get("updated_at"),
        }

    def _normalize_audit_log(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(raw.get("id") or uuid.uuid4().hex),
            "timestamp": str(raw.get("timestamp") or datetime.now(tz=timezone.utc).isoformat()),
            "actor": str(raw.get("actor") or "unknown"),
            "action": str(raw.get("action") or "unknown"),
            "card_id": str(raw.get("card_id") or ""),
            "details": raw.get("details") if isinstance(raw.get("details"), dict) else {},
        }

    def _to_datetime(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value

        if not isinstance(value, str) or not value.strip():
            return None

        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _annotate(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        annotated = dict(snapshot)
        annotated["storage"] = {
            "backend": self.backend,
            "warning": self.last_warning,
        }
        return annotated

    def _load_postgres(self) -> Dict[str, Any]:
        assert self.database_url
        assert self._psycopg

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS curation_snapshots (
                      id SMALLINT PRIMARY KEY CHECK (id = 1),
                      generated_at TEXT,
                      payload_json JSONB NOT NULL,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute("SELECT payload_json FROM curation_snapshots WHERE id = 1")
                row = cur.fetchone()

        if not row:
            return self._merge_defaults({})

        payload = row[0]
        if isinstance(payload, dict):
            return self._merge_defaults(payload)

        return self._merge_defaults({})

    def _ensure_editorial_table_postgres(self) -> None:
        assert self.database_url
        assert self._psycopg

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS card_editorial_states (
                      card_id TEXT PRIMARY KEY,
                      status TEXT NOT NULL DEFAULT 'published',
                      is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
                      pin_rank INTEGER NOT NULL DEFAULT 1000,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

    def _ensure_audit_table_postgres(self) -> None:
        assert self.database_url
        assert self._psycopg

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS admin_audit_logs (
                      id TEXT PRIMARY KEY,
                      timestamp TIMESTAMPTZ NOT NULL,
                      actor TEXT NOT NULL,
                      action TEXT NOT NULL,
                      card_id TEXT NOT NULL,
                      details_json JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )

    def _load_editorial_states_postgres(self) -> Dict[str, Dict[str, Any]]:
        assert self.database_url
        assert self._psycopg

        self._ensure_editorial_table_postgres()

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT card_id, status, is_pinned, pin_rank, updated_at
                    FROM card_editorial_states
                    """
                )
                rows = cur.fetchall() or []

        states: Dict[str, Dict[str, Any]] = {}
        for card_id, status, is_pinned, pin_rank, updated_at in rows:
            states[str(card_id)] = self._normalize_editorial_state(
                {
                    "status": status,
                    "is_pinned": is_pinned,
                    "pin_rank": pin_rank,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                }
            )
        return states

    def _upsert_editorial_state_postgres(self, card_id: str, state: Dict[str, Any]) -> None:
        assert self.database_url
        assert self._psycopg

        self._ensure_editorial_table_postgres()

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO card_editorial_states (card_id, status, is_pinned, pin_rank, updated_at)
                    VALUES (%(card_id)s, %(status)s, %(is_pinned)s, %(pin_rank)s, NOW())
                    ON CONFLICT (card_id)
                    DO UPDATE SET
                      status = EXCLUDED.status,
                      is_pinned = EXCLUDED.is_pinned,
                      pin_rank = EXCLUDED.pin_rank,
                      updated_at = NOW()
                    """,
                    {
                        "card_id": card_id,
                        "status": state.get("status", "published"),
                        "is_pinned": bool(state.get("is_pinned", False)),
                        "pin_rank": int(state.get("pin_rank", 1000)),
                    },
                )

    def _load_editorial_states_file(self) -> Dict[str, Dict[str, Any]]:
        path = self.editorial_state_path
        if not path.exists():
            return {}

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f) or {}

        states: Dict[str, Dict[str, Any]] = {}
        for card_id, raw in payload.items():
            if not isinstance(raw, dict):
                continue
            states[str(card_id)] = self._normalize_editorial_state(raw)
        return states

    def _save_editorial_states_file(self, states: Dict[str, Dict[str, Any]]) -> None:
        path = self.editorial_state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(states, f, ensure_ascii=False, indent=2)

    def _load_audit_logs_file_all(self) -> List[Dict[str, Any]]:
        path = self.audit_log_path
        if not path.exists():
            return []

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f) or []

        rows: List[Dict[str, Any]] = []
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict):
                    rows.append(self._normalize_audit_log(row))

        rows.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return rows

    def _apply_audit_filters(
        self,
        rows: List[Dict[str, Any]],
        *,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        filtered = list(rows)
        if action:
            filtered = [row for row in filtered if row.get("action") == action]
        if card_id:
            filtered = [row for row in filtered if row.get("card_id") == card_id]
        if actor:
            filtered = [row for row in filtered if row.get("actor") == actor]
        if from_timestamp:
            filtered = [
                row
                for row in filtered
                if (parsed := self._to_datetime(row.get("timestamp"))) is not None and parsed >= from_timestamp
            ]
        if to_timestamp:
            filtered = [
                row
                for row in filtered
                if (parsed := self._to_datetime(row.get("timestamp"))) is not None and parsed <= to_timestamp
            ]
        return filtered

    def _audit_day_keys(self, days: int) -> List[str]:
        now_utc = datetime.now(tz=timezone.utc)
        start_day = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc) - timedelta(days=days - 1)
        keys: List[str] = []
        for i in range(max(days, 1)):
            keys.append((start_day + timedelta(days=i)).date().isoformat())
        return keys

    def _build_audit_stats_from_rows(self, rows: List[Dict[str, Any]], days: int) -> Dict[str, Any]:
        action_counts: Dict[str, int] = {}
        for row in rows:
            action = str(row.get("action") or "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1

        day_keys = self._audit_day_keys(days)
        daily_map: Dict[str, Dict[str, int]] = {
            key: {
                "status_update": 0,
                "pin_update": 0,
                "other": 0,
                "total": 0,
            }
            for key in day_keys
        }

        for row in rows:
            parsed = self._to_datetime(row.get("timestamp"))
            if not parsed:
                continue
            day_key = parsed.astimezone(timezone.utc).date().isoformat()
            if day_key not in daily_map:
                continue
            action = str(row.get("action") or "unknown")
            if action == "status_update":
                daily_map[day_key]["status_update"] += 1
            elif action == "pin_update":
                daily_map[day_key]["pin_update"] += 1
            else:
                daily_map[day_key]["other"] += 1
            daily_map[day_key]["total"] += 1

        daily = [{"day": key, **daily_map[key]} for key in day_keys]
        return {
            "total_filtered": len(rows),
            "action_counts": action_counts,
            "daily": daily,
        }

    def _audit_where_clause_and_params(
        self,
        *,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> tuple[str, Dict[str, Any]]:
        filters: List[str] = []
        params: Dict[str, Any] = {}
        if action:
            filters.append("action = %(action)s")
            params["action"] = action
        if card_id:
            filters.append("card_id = %(card_id)s")
            params["card_id"] = card_id
        if actor:
            filters.append("actor = %(actor)s")
            params["actor"] = actor
        if from_timestamp:
            filters.append("timestamp >= %(from_timestamp)s")
            params["from_timestamp"] = from_timestamp
        if to_timestamp:
            filters.append("timestamp <= %(to_timestamp)s")
            params["to_timestamp"] = to_timestamp
        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        return where_clause, params

    def _load_audit_logs_file(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        rows = self._load_audit_logs_file_all()
        rows = self._apply_audit_filters(
            rows,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        safe_offset = max(offset, 0)
        safe_limit = max(limit, 0)
        end = safe_offset + safe_limit
        return rows[safe_offset:end]

    def _save_audit_logs_file(self, logs: List[Dict[str, Any]]) -> None:
        path = self.audit_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(logs[:MAX_AUDIT_LOGS_FILE], f, ensure_ascii=False, indent=2)

    def _append_audit_log_file(self, log: Dict[str, Any]) -> Dict[str, Any]:
        existing = self._load_audit_logs_file(limit=MAX_AUDIT_LOGS_FILE)
        updated = [self._normalize_audit_log(log), *existing]
        self._save_audit_logs_file(updated)
        return updated[0]

    def _load_audit_logs_postgres(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        assert self.database_url
        assert self._psycopg
        self._ensure_audit_table_postgres()
        where_clause, params = self._audit_where_clause_and_params(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        params = dict(params)
        params["limit"] = max(limit, 0)
        params["offset"] = max(offset, 0)

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, timestamp, actor, action, card_id, details_json
                    FROM admin_audit_logs
                    {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT %(limit)s
                    OFFSET %(offset)s
                    """,
                    params,
                )
                rows = cur.fetchall() or []

        logs: List[Dict[str, Any]] = []
        for row in rows:
            log_id, timestamp, actor, action, card_id, details_json = row
            logs.append(
                self._normalize_audit_log(
                    {
                        "id": log_id,
                        "timestamp": timestamp.isoformat() if timestamp else None,
                        "actor": actor,
                        "action": action,
                        "card_id": card_id,
                        "details": details_json if isinstance(details_json, dict) else {},
                    }
                )
            )
        return logs

    def _count_audit_logs_file(
        self,
        *,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> int:
        rows = self._load_audit_logs_file_all()
        rows = self._apply_audit_filters(
            rows,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        return len(rows)

    def _count_audit_logs_postgres(
        self,
        *,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> int:
        assert self.database_url
        assert self._psycopg
        self._ensure_audit_table_postgres()
        where_clause, params = self._audit_where_clause_and_params(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT COUNT(*)::BIGINT
                    FROM admin_audit_logs
                    {where_clause}
                    """,
                    params,
                )
                row = cur.fetchone()
        return int(row[0] if row and row[0] is not None else 0)

    def _load_audit_stats_file(
        self,
        *,
        days: int = 7,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        rows = self._load_audit_logs_file_all()
        rows = self._apply_audit_filters(
            rows,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        return self._build_audit_stats_from_rows(rows, max(days, 1))

    def _load_audit_stats_postgres(
        self,
        *,
        days: int = 7,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        assert self.database_url
        assert self._psycopg
        self._ensure_audit_table_postgres()

        total_filtered = self._count_audit_logs_postgres(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )

        where_clause, params = self._audit_where_clause_and_params(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT action, COUNT(*)::BIGINT
                    FROM admin_audit_logs
                    {where_clause}
                    GROUP BY action
                    """,
                    params,
                )
                action_rows = cur.fetchall() or []

        action_counts: Dict[str, int] = {}
        for action_name, count in action_rows:
            action_counts[str(action_name or "unknown")] = int(count or 0)

        day_keys = self._audit_day_keys(max(days, 1))
        trend_start = datetime.fromisoformat(f"{day_keys[0]}T00:00:00+00:00")
        if where_clause:
            where_daily = f"{where_clause} AND timestamp >= %(trend_start)s"
        else:
            where_daily = "WHERE timestamp >= %(trend_start)s"
        params_daily = dict(params)
        params_daily["trend_start"] = trend_start

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT (timestamp AT TIME ZONE 'UTC')::date AS day_utc, action, COUNT(*)::BIGINT
                    FROM admin_audit_logs
                    {where_daily}
                    GROUP BY day_utc, action
                    ORDER BY day_utc ASC
                    """,
                    params_daily,
                )
                daily_rows = cur.fetchall() or []

        daily_map: Dict[str, Dict[str, int]] = {
            key: {"status_update": 0, "pin_update": 0, "other": 0, "total": 0}
            for key in day_keys
        }
        for day_utc, action_name, count in daily_rows:
            key = day_utc.isoformat() if hasattr(day_utc, "isoformat") else str(day_utc)
            if key not in daily_map:
                continue
            value = int(count or 0)
            action_key = str(action_name or "unknown")
            if action_key == "status_update":
                daily_map[key]["status_update"] += value
            elif action_key == "pin_update":
                daily_map[key]["pin_update"] += value
            else:
                daily_map[key]["other"] += value
            daily_map[key]["total"] += value

        daily = [{"day": key, **daily_map[key]} for key in day_keys]
        return {
            "total_filtered": total_filtered,
            "action_counts": action_counts,
            "daily": daily,
        }

    def _load_audit_top_breakdown_file(
        self,
        *,
        top_limit: int = 5,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        rows = self._load_audit_logs_file_all()
        rows = self._apply_audit_filters(
            rows,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )

        actor_counts: Dict[str, int] = {}
        card_counts: Dict[str, int] = {}
        for row in rows:
            actor_key = str(row.get("actor") or "unknown")
            actor_counts[actor_key] = actor_counts.get(actor_key, 0) + 1

            card_key = str(row.get("card_id") or "")
            if card_key:
                card_counts[card_key] = card_counts.get(card_key, 0) + 1

        safe_limit = max(int(top_limit), 1)
        top_actors = [
            {"actor": key, "count": count}
            for key, count in sorted(actor_counts.items(), key=lambda item: (-item[1], item[0]))[:safe_limit]
        ]
        top_cards = [
            {"card_id": key, "count": count}
            for key, count in sorted(card_counts.items(), key=lambda item: (-item[1], item[0]))[:safe_limit]
        ]

        return {
            "top_actors": top_actors,
            "top_cards": top_cards,
        }

    def _load_audit_top_breakdown_postgres(
        self,
        *,
        top_limit: int = 5,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        assert self.database_url
        assert self._psycopg
        self._ensure_audit_table_postgres()

        where_clause, params = self._audit_where_clause_and_params(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
        query_params = dict(params)
        query_params["top_limit"] = max(int(top_limit), 1)

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT actor, COUNT(*)::BIGINT
                    FROM admin_audit_logs
                    {where_clause}
                    GROUP BY actor
                    ORDER BY COUNT(*) DESC, actor ASC
                    LIMIT %(top_limit)s
                    """,
                    query_params,
                )
                actor_rows = cur.fetchall() or []

                if where_clause:
                    where_cards = f"{where_clause} AND card_id <> ''"
                else:
                    where_cards = "WHERE card_id <> ''"

                cur.execute(
                    f"""
                    SELECT card_id, COUNT(*)::BIGINT
                    FROM admin_audit_logs
                    {where_cards}
                    GROUP BY card_id
                    ORDER BY COUNT(*) DESC, card_id ASC
                    LIMIT %(top_limit)s
                    """,
                    query_params,
                )
                card_rows = cur.fetchall() or []

        top_actors = [{"actor": str(actor_name or "unknown"), "count": int(count or 0)} for actor_name, count in actor_rows]
        top_cards = [{"card_id": str(card_name or ""), "count": int(count or 0)} for card_name, count in card_rows]
        return {
            "top_actors": top_actors,
            "top_cards": top_cards,
        }

    def _append_audit_log_postgres(self, log: Dict[str, Any]) -> Dict[str, Any]:
        assert self.database_url
        assert self._psycopg
        normalized = self._normalize_audit_log(log)
        self._ensure_audit_table_postgres()

        timestamp = normalized.get("timestamp")
        parsed_timestamp = datetime.now(tz=timezone.utc)
        try:
            if isinstance(timestamp, str):
                ts = timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
                parsed_timestamp = datetime.fromisoformat(ts)
                if parsed_timestamp.tzinfo is None:
                    parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        except Exception:
            parsed_timestamp = datetime.now(tz=timezone.utc)

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO admin_audit_logs (id, timestamp, actor, action, card_id, details_json)
                    VALUES (%(id)s, %(timestamp)s, %(actor)s, %(action)s, %(card_id)s, %(details_json)s::jsonb)
                    """,
                    {
                        "id": normalized["id"],
                        "timestamp": parsed_timestamp,
                        "actor": normalized["actor"],
                        "action": normalized["action"],
                        "card_id": normalized["card_id"],
                        "details_json": self._psycopg.types.json.Jsonb(normalized["details"]),
                    },
                )

        return normalized

    def _save_postgres(self, snapshot: Dict[str, Any]) -> None:
        assert self.database_url
        assert self._psycopg

        merged = self._merge_defaults(snapshot)

        with self._psycopg.connect(self.database_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS curation_snapshots (
                      id SMALLINT PRIMARY KEY CHECK (id = 1),
                      generated_at TEXT,
                      payload_json JSONB NOT NULL,
                      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO curation_snapshots (id, generated_at, payload_json, updated_at)
                    VALUES (1, %(generated_at)s, %(payload_json)s::jsonb, NOW())
                    ON CONFLICT (id)
                    DO UPDATE SET
                      generated_at = EXCLUDED.generated_at,
                      payload_json = EXCLUDED.payload_json,
                      updated_at = NOW()
                    """,
                    {
                        "generated_at": merged.get("generated_at"),
                        "payload_json": self._psycopg.types.json.Jsonb(merged),
                    },
                )

    def load_snapshot(self) -> Dict[str, Any]:
        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                snapshot = self._load_postgres()
                return self._annotate(snapshot)
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres load failed; fallback to file storage: {exc}"

        snapshot = self._merge_defaults(load_file_snapshot(cache_path=self.cache_path))
        return self._annotate(snapshot)

    def save_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        merged = self._merge_defaults(snapshot)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                self._save_postgres(merged)
                return self._annotate(merged)
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres save failed; fallback to file storage: {exc}"

        save_file_snapshot(merged, cache_path=self.cache_path)
        return self._annotate(merged)

    def load_editorial_states(self) -> Dict[str, Dict[str, Any]]:
        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._load_editorial_states_postgres()
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres editorial load failed; fallback to file storage: {exc}"

        return self._load_editorial_states_file()

    def upsert_editorial_state(
        self,
        card_id: str,
        status: str | None = None,
        is_pinned: bool | None = None,
        pin_rank: int | None = None,
    ) -> Dict[str, Any]:
        states = self.load_editorial_states()
        current = self._normalize_editorial_state(states.get(card_id, {}))

        if status is not None:
            current["status"] = status
        if is_pinned is not None:
            current["is_pinned"] = bool(is_pinned)
        if pin_rank is not None:
            current["pin_rank"] = int(pin_rank)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                self._upsert_editorial_state_postgres(card_id, current)
                return self._normalize_editorial_state(current)
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres editorial save failed; fallback to file storage: {exc}"

        states[card_id] = current
        self._save_editorial_states_file(states)
        return self._normalize_editorial_state(current)

    def append_audit_log(
        self,
        *,
        actor: str,
        action: str,
        card_id: str,
        details: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        log = self._normalize_audit_log(
            {
                "id": uuid.uuid4().hex,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "actor": actor,
                "action": action,
                "card_id": card_id,
                "details": details or {},
            }
        )

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._append_audit_log_postgres(log)
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres audit save failed; fallback to file storage: {exc}"

        return self._append_audit_log_file(log)

    def load_audit_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> List[Dict[str, Any]]:
        parsed_from = self._to_datetime(from_timestamp)
        parsed_to = self._to_datetime(to_timestamp)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._load_audit_logs_postgres(
                    limit=limit,
                    offset=offset,
                    action=action,
                    card_id=card_id,
                    actor=actor,
                    from_timestamp=parsed_from,
                    to_timestamp=parsed_to,
                )
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres audit load failed; fallback to file storage: {exc}"

        return self._load_audit_logs_file(
            limit=limit,
            offset=offset,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=parsed_from,
            to_timestamp=parsed_to,
        )

    def count_audit_logs(
        self,
        *,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> int:
        parsed_from = self._to_datetime(from_timestamp)
        parsed_to = self._to_datetime(to_timestamp)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._count_audit_logs_postgres(
                    action=action,
                    card_id=card_id,
                    actor=actor,
                    from_timestamp=parsed_from,
                    to_timestamp=parsed_to,
                )
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres audit count failed; fallback to file storage: {exc}"

        return self._count_audit_logs_file(
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=parsed_from,
            to_timestamp=parsed_to,
        )

    def load_audit_stats(
        self,
        *,
        days: int = 7,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        safe_days = max(int(days), 1)
        parsed_from = self._to_datetime(from_timestamp)
        parsed_to = self._to_datetime(to_timestamp)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._load_audit_stats_postgres(
                    days=safe_days,
                    action=action,
                    card_id=card_id,
                    actor=actor,
                    from_timestamp=parsed_from,
                    to_timestamp=parsed_to,
                )
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres audit stats failed; fallback to file storage: {exc}"

        return self._load_audit_stats_file(
            days=safe_days,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=parsed_from,
            to_timestamp=parsed_to,
        )

    def load_audit_top_breakdown(
        self,
        *,
        top_limit: int = 5,
        action: str | None = None,
        card_id: str | None = None,
        actor: str | None = None,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
    ) -> Dict[str, Any]:
        safe_limit = max(int(top_limit), 1)
        parsed_from = self._to_datetime(from_timestamp)
        parsed_to = self._to_datetime(to_timestamp)

        if self.backend == "postgres" and self.database_url and self._psycopg:
            try:
                return self._load_audit_top_breakdown_postgres(
                    top_limit=safe_limit,
                    action=action,
                    card_id=card_id,
                    actor=actor,
                    from_timestamp=parsed_from,
                    to_timestamp=parsed_to,
                )
            except Exception as exc:  # pragma: no cover
                self.backend = "file"
                self.last_warning = f"postgres audit top breakdown failed; fallback to file storage: {exc}"

        return self._load_audit_top_breakdown_file(
            top_limit=safe_limit,
            action=action,
            card_id=card_id,
            actor=actor,
            from_timestamp=parsed_from,
            to_timestamp=parsed_to,
        )
