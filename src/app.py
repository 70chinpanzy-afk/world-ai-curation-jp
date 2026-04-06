"""FastAPI app for world AI curation."""

from __future__ import annotations

import csv
import json
import io
import os
import secrets
import threading
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape as xml_escape

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .editorial import ALLOWED_STATUSES, apply_editorial_state, normalize_status, sort_for_public_feed
from .engine import refresh_cards
from .persistence import SnapshotPersistence


ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "src" / "web"
STATIC_DIR = WEB_DIR / "static"
DEFAULT_AFFILIATE_CONFIG_PATH = ROOT_DIR / "config" / "affiliate_links.json"


class RuntimeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.snapshot: Dict[str, Any] = {"generated_at": None, "cards": [], "errors": [], "stats": {}}
        self.stop_event = threading.Event()

    def set_snapshot(self, snapshot: Dict[str, Any]) -> None:
        with self._lock:
            self.snapshot = snapshot

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self.snapshot


state = RuntimeState()
persistence = SnapshotPersistence()
app = FastAPI(title="World AI Curation", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
security = HTTPBasic()
ALLOWED_DIFFICULTY_LEVELS = {"初級", "中級", "上級寄り", "初級（検証前提）"}


class StatusUpdateRequest(BaseModel):
    status: str


class PinUpdateRequest(BaseModel):
    pinned: bool = False
    pin_rank: int = Field(default=1000, ge=0, le=100000)


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> Dict[str, str]:
    expected_username = os.getenv("ADMIN_USERNAME", "admin")
    expected_password = os.getenv("ADMIN_PASSWORD", "admin")

    valid_user = secrets.compare_digest(credentials.username, expected_username)
    valid_pass = secrets.compare_digest(credentials.password, expected_password)

    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return {"username": credentials.username}


def _decorate_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    editorial_states = persistence.load_editorial_states()
    cards = apply_editorial_state(snapshot.get("cards", []), editorial_states)
    cards = sort_for_public_feed(cards)

    decorated = dict(snapshot)
    decorated["cards"] = cards
    decorated["editorial_stats"] = {
        "states_total": len(editorial_states),
        "published": len([c for c in cards if c.get("status") == "published"]),
        "draft": len([c for c in cards if c.get("status") == "draft"]),
        "archived": len([c for c in cards if c.get("status") == "archived"]),
        "pinned": len([c for c in cards if c.get("is_pinned")]),
    }
    return decorated


def _set_state_with_editorial(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    decorated = _decorate_snapshot(snapshot)
    state.set_snapshot(decorated)
    return decorated


def _find_card(snapshot: Dict[str, Any], card_id: str) -> Dict[str, Any] | None:
    for card in snapshot.get("cards", []):
        if str(card.get("id")) == card_id:
            return card
    return None


def _request_meta(request: Request) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    if request.client and request.client.host:
        meta["client_host"] = request.client.host

    user_agent = request.headers.get("user-agent", "").strip()
    if user_agent:
        meta["user_agent"] = user_agent[:300]

    return meta


def _public_base_url() -> str:
    raw = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").strip()
    if not raw:
        raw = "http://127.0.0.1:8000"
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _render_web_html(filename: str) -> str:
    path = WEB_DIR / filename
    html = path.read_text(encoding="utf-8")
    return html.replace("__PUBLIC_BASE_URL__", _public_base_url())


def _affiliate_config_path() -> Path:
    return Path(os.getenv("AFFILIATE_LINKS_PATH", str(DEFAULT_AFFILIATE_CONFIG_PATH)))


def _sanitize_affiliate_payload(raw: Any, default_payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return default_payload

    disclosure = str(raw.get("disclosure") or default_payload["disclosure"])
    links_raw = raw.get("links")
    links: List[Dict[str, Any]] = []

    if isinstance(links_raw, list):
        for row in links_raw:
            if not isinstance(row, dict):
                continue
            if not bool(row.get("is_active", True)):
                continue

            url = str(row.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue

            links.append(
                {
                    "title": str(row.get("title") or "おすすめリンク"),
                    "url": url,
                    "description": str(row.get("description") or ""),
                    "badge": str(row.get("badge") or ""),
                }
            )
    return {"disclosure": disclosure, "links": links[:20]}


def _load_affiliate_payload_from_env(default_payload: Dict[str, Any]) -> Dict[str, Any] | None:
    raw_env = os.getenv("AFFILIATE_LINKS_JSON", "").strip()
    if not raw_env:
        return None
    try:
        payload = json.loads(raw_env)
    except Exception:
        return None
    return _sanitize_affiliate_payload(payload, default_payload)


def _load_affiliate_payload() -> Dict[str, Any]:
    default_payload = {
        "disclosure": "本ページにはアフィリエイトリンクが含まれる場合があります。掲載順は広告報酬の大小で決めていません。",
        "links": [],
    }
    env_payload = _load_affiliate_payload_from_env(default_payload)
    if env_payload is not None:
        return env_payload

    path = _affiliate_config_path()
    if not path.exists():
        return default_payload

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_payload

    return _sanitize_affiliate_payload(raw, default_payload)


def _card_difficulty_level(card: Dict[str, Any]) -> str:
    builder_pack = card.get("builder_pack") if isinstance(card.get("builder_pack"), dict) else {}
    difficulty = builder_pack.get("difficulty") if isinstance(builder_pack, dict) else {}
    if not isinstance(difficulty, dict):
        return ""
    return str(difficulty.get("level", "")).strip()


def _normalize_difficulty_filter(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() == "all":
        return None
    if text not in ALLOWED_DIFFICULTY_LEVELS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid difficulty. Allowed: {', '.join(sorted(ALLOWED_DIFFICULTY_LEVELS))}",
        )
    return text


def _parse_query_timestamp(value: str | None, param_name: str) -> datetime | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Invalid {param_name}. Use ISO 8601 datetime (example: 2026-03-28T00:00:00+09:00).",
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve_audit_filters(
    *,
    action: str | None = None,
    card_id: str | None = None,
    actor: str | None = None,
    from_ts: str | None = None,
    to_ts: str | None = None,
) -> Dict[str, Any]:
    from_timestamp = _parse_query_timestamp(from_ts, "from_ts")
    to_timestamp = _parse_query_timestamp(to_ts, "to_ts")
    if from_timestamp and to_timestamp and from_timestamp > to_timestamp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_ts must be earlier than or equal to to_ts.",
        )

    return {
        "action": action,
        "card_id": card_id,
        "actor": actor,
        "from_timestamp": from_timestamp,
        "to_timestamp": to_timestamp,
        "filter_meta": {
            "action": action,
            "card_id": card_id,
            "actor": actor,
            "from_ts": from_timestamp.isoformat() if from_timestamp else None,
            "to_ts": to_timestamp.isoformat() if to_timestamp else None,
        },
    }


def _build_weekly_highlights(
    *,
    total_filtered: int,
    action_counts: Dict[str, Any],
    busiest_day: Dict[str, Any] | None,
    top_actors: List[Dict[str, Any]],
    top_cards: List[Dict[str, Any]],
) -> List[str]:
    highlights: List[str] = []
    status_count = int(action_counts.get("status_update", 0) or 0)
    pin_count = int(action_counts.get("pin_update", 0) or 0)
    other_count = int(action_counts.get("other", 0) or 0)

    if total_filtered == 0:
        highlights.append("直近期間の監査ログは0件でした。運用変更は落ち着いています。")
        return highlights

    highlights.append(f"直近期間の変更は合計{total_filtered}件（Status: {status_count} / Pin: {pin_count} / Other: {other_count}）です。")

    if busiest_day and busiest_day.get("day"):
        highlights.append(
            f"最も変更が集中した日は {busiest_day.get('day')}（{int(busiest_day.get('total', 0) or 0)}件）でした。"
        )

    if top_actors:
        top_actor = top_actors[0]
        highlights.append(f"変更の中心は `{top_actor.get('actor')}`（{int(top_actor.get('count', 0) or 0)}件）です。")

    if top_cards:
        top_card = top_cards[0]
        highlights.append(f"最も触られたカードは `{top_card.get('card_id')}`（{int(top_card.get('count', 0) or 0)}件）です。")

    return highlights


def _build_vibe_playbook(*, total_filtered: int, status_count: int, pin_count: int, top_cards: List[Dict[str, Any]]) -> List[str]:
    if total_filtered == 0:
        return [
            "今週は運用変更が少ないため、新しい配信ルールやカード分類ルールを試す余白があります。",
            "来週に向けて、重要トピックの定義と `published/draft` の判断基準を1ページで整理しておくと実装しやすくなります。",
        ]

    actions: List[str] = []
    if status_count >= pin_count:
        actions.append("Status変更が多い週です。まず `draft -> published` の基準を短く固定し、判断のブレを減らすと運用が安定します。")
    else:
        actions.append("Pin変更が多い週です。`pin_rank` の優先順位ルール（速報優先/解説優先など）を先に決めると迷いが減ります。")

    if top_cards:
        actions.append(
            f"`{top_cards[0].get('card_id')}` のような更新頻度が高いカードは、テンプレ文面を作っておくと非エンジニアでも高速に編集できます。"
        )

    actions.append("次の改善として、変更理由を `details` に1行で残す運用にすると、後でAIに要約させやすくなります。")
    return actions


def _generate_weekly_report_payload(
    *,
    days: int,
    top_limit: int,
    action: str | None = None,
    card_id: str | None = None,
    actor: str | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> Dict[str, Any]:
    safe_days = max(int(days), 1)
    safe_top = max(int(top_limit), 1)

    stats_payload = persistence.load_audit_stats(
        days=safe_days,
        action=action,
        card_id=card_id,
        actor=actor,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    breakdown_payload = persistence.load_audit_top_breakdown(
        top_limit=safe_top,
        action=action,
        card_id=card_id,
        actor=actor,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )

    daily = stats_payload.get("daily", []) if isinstance(stats_payload.get("daily"), list) else []
    busiest_day = None
    if daily:
        busiest_day = max(daily, key=lambda row: int(row.get("total", 0) or 0))

    total_filtered = int(stats_payload.get("total_filtered", 0) or 0)
    action_counts = stats_payload.get("action_counts", {}) if isinstance(stats_payload.get("action_counts"), dict) else {}
    top_actors = breakdown_payload.get("top_actors", []) if isinstance(breakdown_payload.get("top_actors"), list) else []
    top_cards = breakdown_payload.get("top_cards", []) if isinstance(breakdown_payload.get("top_cards"), list) else []

    status_count = int(action_counts.get("status_update", 0) or 0)
    pin_count = int(action_counts.get("pin_update", 0) or 0)

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "days": safe_days,
        "total_filtered": total_filtered,
        "action_counts": action_counts,
        "daily": daily,
        "busiest_day": busiest_day,
        "top_actors": top_actors,
        "top_cards": top_cards,
        "highlights": _build_weekly_highlights(
            total_filtered=total_filtered,
            action_counts=action_counts,
            busiest_day=busiest_day,
            top_actors=top_actors,
            top_cards=top_cards,
        ),
        "playbook_for_vibe_coders": _build_vibe_playbook(
            total_filtered=total_filtered,
            status_count=status_count,
            pin_count=pin_count,
            top_cards=top_cards,
        ),
    }


def _render_weekly_report_markdown(payload: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# Weekly Audit Brief ({int(payload.get('days', 7) or 7)} days)")
    lines.append("")
    lines.append(f"- Generated: {payload.get('generated_at', '')}")
    lines.append(f"- Total Changes: {int(payload.get('total_filtered', 0) or 0)}")

    busiest = payload.get("busiest_day") if isinstance(payload.get("busiest_day"), dict) else None
    if busiest and busiest.get("day"):
        lines.append(f"- Busiest Day: {busiest.get('day')} ({int(busiest.get('total', 0) or 0)} changes)")

    action_counts = payload.get("action_counts", {}) if isinstance(payload.get("action_counts"), dict) else {}
    if action_counts:
        lines.append("- Action Counts:")
        for action_name, count in sorted(action_counts.items()):
            lines.append(f"  - {action_name}: {int(count or 0)}")

    top_actors = payload.get("top_actors", []) if isinstance(payload.get("top_actors"), list) else []
    if top_actors:
        lines.append("- Top Actors:")
        for row in top_actors:
            lines.append(f"  - {row.get('actor')}: {int(row.get('count', 0) or 0)}")

    top_cards = payload.get("top_cards", []) if isinstance(payload.get("top_cards"), list) else []
    if top_cards:
        lines.append("- Top Cards:")
        for row in top_cards:
            lines.append(f"  - {row.get('card_id')}: {int(row.get('count', 0) or 0)}")

    highlights = payload.get("highlights", []) if isinstance(payload.get("highlights"), list) else []
    lines.append("")
    lines.append("## Highlights")
    if highlights:
        for line in highlights:
            lines.append(f"- {line}")
    else:
        lines.append("- No highlights.")

    playbook = payload.get("playbook_for_vibe_coders", []) if isinstance(payload.get("playbook_for_vibe_coders"), list) else []
    lines.append("")
    lines.append("## Vibe Playbook")
    if playbook:
        for line in playbook:
            lines.append(f"- {line}")
    else:
        lines.append("- No playbook items.")

    return "\n".join(lines).strip() + "\n"


def _weekly_report_output_paths() -> Dict[str, Path]:
    json_path = Path(os.getenv("WEEKLY_BRIEF_JSON_PATH", str(ROOT_DIR / "data" / "weekly_brief_latest.json")))
    md_path = Path(os.getenv("WEEKLY_BRIEF_MD_PATH", str(ROOT_DIR / "data" / "weekly_brief_latest.md")))
    return {"json_path": json_path, "md_path": md_path}


def _weekly_report_history_path() -> Path:
    return Path(os.getenv("WEEKLY_BRIEF_HISTORY_PATH", str(ROOT_DIR / "data" / "weekly_brief_history.json")))


def _load_weekly_brief_history() -> List[Dict[str, Any]]:
    path = _weekly_report_history_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    rows: List[Dict[str, Any]] = []
    for row in payload:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _save_weekly_brief_history(rows: List[Dict[str, Any]]) -> None:
    path = _weekly_report_history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _history_max_entries() -> int:
    raw = os.getenv("WEEKLY_BRIEF_HISTORY_MAX_ENTRIES", "200")
    try:
        return max(int(raw), 1)
    except Exception:
        return 200


def _append_weekly_brief_history(entry: Dict[str, Any]) -> None:
    rows = _load_weekly_brief_history()
    max_entries = _history_max_entries()
    updated = [entry, *rows[: max_entries - 1]]
    _save_weekly_brief_history(updated)


def _history_item_saved_at(item: Dict[str, Any]) -> datetime | None:
    raw = item.get("saved_at")
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _history_item_matches(
    item: Dict[str, Any],
    *,
    q: str | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> bool:
    if q:
        blob = json.dumps(item, ensure_ascii=False).lower()
        if q.lower() not in blob:
            return False

    if from_timestamp or to_timestamp:
        saved_at = _history_item_saved_at(item)
        if not saved_at:
            return False
        if from_timestamp and saved_at < from_timestamp:
            return False
        if to_timestamp and saved_at > to_timestamp:
            return False

    return True


def _filter_weekly_brief_history(
    rows: List[Dict[str, Any]],
    *,
    q: str | None = None,
    from_timestamp: datetime | None = None,
    to_timestamp: datetime | None = None,
) -> List[Dict[str, Any]]:
    return [
        row
        for row in rows
        if _history_item_matches(
            row,
            q=q,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
    ]


def _sort_weekly_brief_history(rows: List[Dict[str, Any]], *, sort: str = "desc") -> List[Dict[str, Any]]:
    reverse = str(sort).lower() != "asc"

    def _key(row: Dict[str, Any]) -> datetime:
        parsed = _history_item_saved_at(row)
        return parsed if parsed else datetime.min.replace(tzinfo=timezone.utc)

    return sorted(rows, key=_key, reverse=reverse)


def _parse_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _write_weekly_report_artifacts(payload: Dict[str, Any], *, archive: bool = True) -> Dict[str, str]:
    paths = _weekly_report_output_paths()
    json_path = paths["json_path"]
    md_path = paths["md_path"]
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_weekly_report_markdown(payload), encoding="utf-8")

    result: Dict[str, str] = {
        "json_path": str(json_path),
        "md_path": str(md_path),
    }

    archive_json_path = ""
    archive_md_path = ""
    if archive:
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%SZ")
        archive_dir = Path(os.getenv("WEEKLY_BRIEF_ARCHIVE_DIR", str(ROOT_DIR / "data" / "weekly_briefs")))
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_json = archive_dir / f"weekly_brief_{stamp}.json"
        archive_md = archive_dir / f"weekly_brief_{stamp}.md"
        archive_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        archive_md.write_text(_render_weekly_report_markdown(payload), encoding="utf-8")
        archive_json_path = str(archive_json)
        archive_md_path = str(archive_md)
        result["archive_json_path"] = archive_json_path
        result["archive_md_path"] = archive_md_path

    _append_weekly_brief_history(
        {
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
            "generated_at": payload.get("generated_at"),
            "days": int(payload.get("days", 7) or 7),
            "total_filtered": int(payload.get("total_filtered", 0) or 0),
            "json_path": str(json_path),
            "md_path": str(md_path),
            "archive_json_path": archive_json_path,
            "archive_md_path": archive_md_path,
        }
    )
    return result


def _run_refresh() -> Dict[str, Any]:
    snapshot = refresh_cards()
    persisted = persistence.save_snapshot(snapshot)
    decorated = _set_state_with_editorial(persisted)

    auto_write_weekly = _parse_env_bool("AUTO_WRITE_WEEKLY_BRIEF", default=False)
    auto_post_weekly = _parse_env_bool("AUTO_POST_WEEKLY_BRIEF", default=False)
    if auto_write_weekly or auto_post_weekly:
        try:
            days = int(os.getenv("WEEKLY_BRIEF_DAYS", "7"))
            top_limit = int(os.getenv("WEEKLY_BRIEF_TOP_LIMIT", "5"))
            auto_archive = _parse_env_bool("AUTO_WRITE_WEEKLY_BRIEF_ARCHIVE", default=True)
            weekly_payload = _generate_weekly_report_payload(days=days, top_limit=top_limit)
            if auto_write_weekly:
                _write_weekly_report_artifacts(weekly_payload, archive=auto_archive)
            if auto_post_weekly:
                publish_result = _publish_weekly_brief(weekly_payload)
                if _publish_result_has_errors(publish_result):
                    errors = list(decorated.get("errors", []))
                    errors.append(f"Weekly brief publish failed: {publish_result}")
                    decorated["errors"] = errors
                    state.set_snapshot(decorated)
        except Exception as exc:  # pragma: no cover
            errors = list(decorated.get("errors", []))
            errors.append(f"Weekly brief write failed: {exc}")
            decorated["errors"] = errors
            state.set_snapshot(decorated)

    return decorated


def _scheduler_loop() -> None:
    interval_minutes = int(os.getenv("REFRESH_INTERVAL_MINUTES", "60"))
    wait_seconds = max(interval_minutes, 1) * 60

    while not state.stop_event.wait(wait_seconds):
        try:
            _run_refresh()
        except Exception as exc:  # pragma: no cover
            existing = state.get_snapshot()
            errors = list(existing.get("errors", []))
            errors.append(f"Scheduled refresh failed: {exc}")
            existing["errors"] = errors
            state.set_snapshot(existing)


@app.on_event("startup")
def on_startup() -> None:
    cached = persistence.load_snapshot()
    _set_state_with_editorial(cached)

    should_refresh = os.getenv("AUTO_REFRESH_ON_START", "1") == "1"
    if should_refresh:
        try:
            _run_refresh()
        except Exception as exc:  # pragma: no cover
            existing = state.get_snapshot()
            errors = list(existing.get("errors", []))
            errors.append(f"Initial refresh failed: {exc}")
            existing["errors"] = errors
            state.set_snapshot(existing)

    thread = threading.Thread(target=_scheduler_loop, daemon=True, name="refresh-scheduler")
    thread.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    state.stop_event.set()


@app.get("/api/status")
def api_status() -> Dict[str, Any]:
    snapshot = state.get_snapshot()
    return {
        "generated_at": snapshot.get("generated_at"),
        "card_count": len(snapshot.get("cards", [])),
        "stats": snapshot.get("stats", {}),
        "editorial_stats": snapshot.get("editorial_stats", {}),
        "storage": snapshot.get("storage", {}),
        "errors": snapshot.get("errors", []),
    }


@app.get("/api/affiliate-links")
def api_affiliate_links() -> Dict[str, Any]:
    payload = _load_affiliate_payload()
    return {
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        "disclosure": payload.get("disclosure"),
        "total": len(payload.get("links", [])),
        "links": payload.get("links", []),
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _rss_item_pub_date(card: Dict[str, Any]) -> str:
    source = card.get("source", {}) if isinstance(card.get("source"), dict) else {}
    published = _parse_iso_datetime(source.get("published_at"))
    if not published:
        published = datetime.now(tz=timezone.utc)
    return format_datetime(published)


def _build_rss_xml(snapshot: Dict[str, Any], *, base_url: str, max_items: int = 50) -> str:
    cards = snapshot.get("cards", []) if isinstance(snapshot.get("cards"), list) else []
    published_cards = [c for c in cards if c.get("status", "published") == "published"]
    published_cards.sort(
        key=lambda c: (_parse_iso_datetime((c.get("source") or {}).get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)),
        reverse=True,
    )

    header = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<rss version=\"2.0\">\n"
        "<channel>\n"
        "<title>AI情報まとめ</title>\n"
        f"<link>{xml_escape(base_url)}/</link>\n"
        "<description>海外AI情報の一次ソース中心キュレーション（日本語）</description>\n"
        "<language>ja</language>\n"
        f"<lastBuildDate>{format_datetime(datetime.now(tz=timezone.utc))}</lastBuildDate>\n"
    )

    item_lines: List[str] = []
    for card in published_cards[:max_items]:
        source = card.get("source", {}) if isinstance(card.get("source"), dict) else {}
        title = xml_escape(str(card.get("headline") or "Untitled"))
        link = xml_escape(str(source.get("url") or f"{base_url}/"))
        guid = xml_escape(str(card.get("id") or link))
        summary = xml_escape(str(card.get("summary") or ""))
        pub_date = xml_escape(_rss_item_pub_date(card))
        item_lines.extend(
            [
                "<item>",
                f"<title>{title}</title>",
                f"<link>{link}</link>",
                f"<guid isPermaLink=\"false\">{guid}</guid>",
                f"<description>{summary}</description>",
                f"<pubDate>{pub_date}</pubDate>",
                "</item>",
            ]
        )

    footer = "</channel>\n</rss>\n"
    return header + "\n".join(item_lines) + ("\n" if item_lines else "") + footer


@app.get("/api/cards")
def api_cards(
    audience: str = Query(default="vibe", pattern="^(raw|vibe|builder)$"),
    section: str = Query(default="all", pattern="^(all|main|signals)$"),
    status: str = Query(default="published", pattern="^(all|draft|published|archived)$"),
    limit: int = Query(default=30, ge=1, le=200),
    topic: str | None = Query(default=None),
    difficulty: str | None = Query(default=None, max_length=40),
) -> Dict[str, Any]:
    snapshot = state.get_snapshot()
    cards: List[Dict[str, Any]] = []
    difficulty_filter = _normalize_difficulty_filter(difficulty)

    for card in snapshot.get("cards", []):
        if section != "all" and card.get("section") != section:
            continue
        if topic and card.get("topic") != topic:
            continue
        if status != "all" and card.get("status") != status:
            continue
        if difficulty_filter and _card_difficulty_level(card) != difficulty_filter:
            continue

        cards.append(
            {
                **card,
                "display_text": card.get("variants", {}).get(audience, ""),
            }
        )

    return {
        "generated_at": snapshot.get("generated_at"),
        "audience": audience,
        "section": section,
        "status": status,
        "topic": topic,
        "difficulty": difficulty_filter,
        "total": len(cards),
        "cards": cards[:limit],
    }


@app.post("/api/refresh")
def api_refresh() -> Dict[str, Any]:
    snapshot = _run_refresh()
    return {
        "ok": True,
        "generated_at": snapshot.get("generated_at"),
        "total": len(snapshot.get("cards", [])),
        "errors": snapshot.get("errors", []),
    }


@app.get("/api/admin/cards")
def api_admin_cards(
    _: Dict[str, str] = Depends(require_admin),
    audience: str = Query(default="vibe", pattern="^(raw|vibe|builder)$"),
    section: str = Query(default="all", pattern="^(all|main|signals)$"),
    status: str = Query(default="all", pattern="^(all|draft|published|archived)$"),
    limit: int = Query(default=200, ge=1, le=1000),
    topic: str | None = Query(default=None),
    difficulty: str | None = Query(default=None, max_length=40),
) -> Dict[str, Any]:
    snapshot = state.get_snapshot()
    cards: List[Dict[str, Any]] = []
    difficulty_filter = _normalize_difficulty_filter(difficulty)

    for card in snapshot.get("cards", []):
        if section != "all" and card.get("section") != section:
            continue
        if status != "all" and card.get("status") != status:
            continue
        if topic and card.get("topic") != topic:
            continue
        if difficulty_filter and _card_difficulty_level(card) != difficulty_filter:
            continue

        cards.append(
            {
                **card,
                "display_text": card.get("variants", {}).get(audience, ""),
            }
        )

    return {
        "generated_at": snapshot.get("generated_at"),
        "audience": audience,
        "section": section,
        "status": status,
        "topic": topic,
        "difficulty": difficulty_filter,
        "total": len(cards),
        "cards": cards[:limit],
    }


@app.get("/api/admin/audit")
def api_admin_audit(
    _: Dict[str, str] = Depends(require_admin),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0, le=100000),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
) -> Dict[str, Any]:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    # Fetch one extra row to detect whether next page exists.
    rows = persistence.load_audit_logs(
        limit=limit + 1,
        offset=offset,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    total_filtered = persistence.count_audit_logs(
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    has_more = len(rows) > limit
    logs = rows[:limit]
    return {
        "total": len(logs),
        "total_filtered": total_filtered,
        "returned": len(logs),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "filters": filters["filter_meta"],
        "logs": logs,
    }


@app.get("/api/admin/audit.csv")
def api_admin_audit_csv(
    _: Dict[str, str] = Depends(require_admin),
    limit: int = Query(default=500, ge=1, le=5000),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
) -> PlainTextResponse:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    logs = persistence.load_audit_logs(
        limit=limit,
        offset=0,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "timestamp", "actor", "action", "card_id", "details_json"])
    for log in logs:
        writer.writerow(
            [
                log.get("id", ""),
                log.get("timestamp", ""),
                log.get("actor", ""),
                log.get("action", ""),
                log.get("card_id", ""),
                json.dumps(log.get("details", {}), ensure_ascii=False),
            ]
        )

    headers = {"Content-Disposition": "attachment; filename=admin_audit_logs.csv"}
    return PlainTextResponse(content=output.getvalue(), media_type="text/csv", headers=headers)


@app.get("/api/admin/audit/trend.csv")
def api_admin_audit_trend_csv(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
) -> PlainTextResponse:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    stats_payload = persistence.load_audit_stats(
        days=days,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["day", "status_update", "pin_update", "other", "total"])
    for row in stats_payload.get("daily", []):
        writer.writerow(
            [
                row.get("day", ""),
                row.get("status_update", 0),
                row.get("pin_update", 0),
                row.get("other", 0),
                row.get("total", 0),
            ]
        )
    writer.writerow([])
    writer.writerow(["metric", "value"])
    writer.writerow(["days", days])
    writer.writerow(["total_filtered", stats_payload.get("total_filtered", 0)])
    for action_name, count in sorted((stats_payload.get("action_counts") or {}).items()):
        writer.writerow([f"action_{action_name}", count])

    headers = {"Content-Disposition": f"attachment; filename=admin_audit_trend_{days}d.csv"}
    return PlainTextResponse(content=output.getvalue(), media_type="text/csv", headers=headers)


@app.get("/api/admin/audit/stats")
def api_admin_audit_stats(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
) -> Dict[str, Any]:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )

    stats_payload = persistence.load_audit_stats(
        days=days,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    return {
        "days": days,
        "filters": filters["filter_meta"],
        **stats_payload,
    }


@app.get("/api/admin/audit/weekly-report")
def api_admin_audit_weekly_report(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    top_limit: int = Query(default=5, ge=1, le=20),
) -> Dict[str, Any]:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    payload = _generate_weekly_report_payload(
        days=days,
        top_limit=top_limit,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    return {
        **payload,
        "filters": filters["filter_meta"],
    }


@app.get("/api/admin/audit/weekly-report/history")
def api_admin_audit_weekly_report_history(
    _: Dict[str, str] = Depends(require_admin),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    q: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> Dict[str, Any]:
    from_timestamp = _parse_query_timestamp(from_ts, "from_ts")
    to_timestamp = _parse_query_timestamp(to_ts, "to_ts")
    if from_timestamp and to_timestamp and from_timestamp > to_timestamp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_ts must be earlier than or equal to to_ts.",
        )

    rows = _load_weekly_brief_history()
    filtered = _filter_weekly_brief_history(
        rows,
        q=(q or "").strip() or None,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    sorted_rows = _sort_weekly_brief_history(filtered, sort=sort)
    paged = sorted_rows[offset : offset + limit]
    return {
        "total": len(rows),
        "total_filtered": len(filtered),
        "limit": limit,
        "offset": offset,
        "q": (q or "").strip() or None,
        "sort": sort,
        "items": paged,
    }


@app.get("/api/admin/audit/weekly-report/history.csv")
def api_admin_audit_weekly_report_history_csv(
    _: Dict[str, str] = Depends(require_admin),
    limit: int = Query(default=200, ge=1, le=5000),
    offset: int = Query(default=0, ge=0, le=10000),
    q: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> PlainTextResponse:
    from_timestamp = _parse_query_timestamp(from_ts, "from_ts")
    to_timestamp = _parse_query_timestamp(to_ts, "to_ts")
    if from_timestamp and to_timestamp and from_timestamp > to_timestamp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_ts must be earlier than or equal to to_ts.",
        )

    rows = _load_weekly_brief_history()
    filtered = _filter_weekly_brief_history(
        rows,
        q=(q or "").strip() or None,
        from_timestamp=from_timestamp,
        to_timestamp=to_timestamp,
    )
    sorted_rows = _sort_weekly_brief_history(filtered, sort=sort)
    paged = sorted_rows[offset : offset + limit]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "saved_at",
            "generated_at",
            "days",
            "total_filtered",
            "json_path",
            "md_path",
            "archive_json_path",
            "archive_md_path",
        ]
    )
    for row in paged:
        writer.writerow(
            [
                row.get("saved_at", ""),
                row.get("generated_at", ""),
                row.get("days", ""),
                row.get("total_filtered", ""),
                row.get("json_path", ""),
                row.get("md_path", ""),
                row.get("archive_json_path", ""),
                row.get("archive_md_path", ""),
            ]
        )

    headers = {"Content-Disposition": "attachment; filename=admin_weekly_brief_history.csv"}
    return PlainTextResponse(content=output.getvalue(), media_type="text/csv", headers=headers)


@app.delete("/api/admin/audit/weekly-report/history")
def api_admin_audit_weekly_report_history_delete(
    _: Dict[str, str] = Depends(require_admin),
    confirm: bool = Query(default=False),
    keep_latest: int = Query(default=0, ge=0, le=200),
    q: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    sort: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> Dict[str, Any]:
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set confirm=true to delete history entries.",
        )

    from_timestamp = _parse_query_timestamp(from_ts, "from_ts")
    to_timestamp = _parse_query_timestamp(to_ts, "to_ts")
    if from_timestamp and to_timestamp and from_timestamp > to_timestamp:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="from_ts must be earlier than or equal to to_ts.",
        )

    rows = _load_weekly_brief_history()
    search_q = (q or "").strip() or None
    matched_pairs = [
        (index, row)
        for index, row in enumerate(rows)
        if _history_item_matches(
            row,
            q=search_q,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp,
        )
    ]
    matched_pairs = _sort_weekly_brief_history([row for _, row in matched_pairs], sort=sort)
    sorted_index_pairs: List[tuple[int, Dict[str, Any]]] = []
    for row in matched_pairs:
        for index, original in enumerate(rows):
            if original is row:
                sorted_index_pairs.append((index, row))
                break

    to_delete = set(index for index, _ in sorted_index_pairs[keep_latest:])
    kept = [row for index, row in enumerate(rows) if index not in to_delete]
    deleted = len(to_delete)
    _save_weekly_brief_history(kept)
    return {
        "ok": True,
        "deleted": deleted,
        "remaining": len(kept),
        "keep_latest": keep_latest,
    }


@app.post("/api/admin/audit/weekly-report/history/cleanup")
def api_admin_audit_weekly_report_history_cleanup(
    _: Dict[str, str] = Depends(require_admin),
    confirm: bool = Query(default=False),
    keep_latest: int = Query(default=200, ge=1, le=5000),
) -> Dict[str, Any]:
    if not confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set confirm=true to cleanup history entries.",
        )

    rows = _load_weekly_brief_history()
    sorted_rows = _sort_weekly_brief_history(rows, sort="desc")
    kept = sorted_rows[:keep_latest]
    deleted = max(len(rows) - len(kept), 0)
    _save_weekly_brief_history(kept)
    return {
        "ok": True,
        "deleted": deleted,
        "remaining": len(kept),
        "keep_latest": keep_latest,
    }


def _weekly_brief_publish_text(payload: Dict[str, Any]) -> str:
    days = int(payload.get("days", 7) or 7)
    total = int(payload.get("total_filtered", 0) or 0)
    highlights = payload.get("highlights", []) if isinstance(payload.get("highlights"), list) else []
    top = highlights[0] if highlights else "No highlights"
    return f"Weekly Audit Brief ({days}d)\nTotal changes: {total}\n{top}"


def _http_post_json(
    url: str,
    body: Dict[str, Any],
    headers: Dict[str, str] | None = None,
    timeout_seconds: int = 20,
    method: str = "POST",
) -> None:
    import urllib.request

    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url=url, data=payload, headers=request_headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=timeout_seconds):
        pass


def _publish_weekly_brief(payload: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    text = _weekly_brief_publish_text(payload)

    slack_url = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    if slack_url:
        try:
            _http_post_json(slack_url, {"text": text})
            result["slack"] = "ok"
        except Exception as exc:
            result["slack"] = f"error: {exc}"
    else:
        result["slack"] = "skipped"

    notion_token = (os.getenv("NOTION_API_TOKEN") or "").strip()
    notion_page_id = (os.getenv("NOTION_PAGE_ID") or "").strip()
    if notion_token and notion_page_id:
        try:
            children = [
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {"rich_text": [{"type": "text", "text": {"content": f"Weekly Audit Brief ({payload.get('days', 7)}d)"}}]},
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
                },
            ]
            _http_post_json(
                f"https://api.notion.com/v1/blocks/{notion_page_id}/children",
                {"children": children},
                headers={
                    "Authorization": f"Bearer {notion_token}",
                    "Notion-Version": "2022-06-28",
                },
                method="PATCH",
            )
            result["notion"] = "ok"
        except Exception as exc:
            result["notion"] = f"error: {exc}"
    else:
        result["notion"] = "skipped"

    return result


def _publish_result_has_errors(result: Dict[str, Any]) -> bool:
    for value in result.values():
        if str(value).startswith("error:"):
            return True
    return False


@app.get("/api/admin/audit/weekly-report.md")
def api_admin_audit_weekly_report_md(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    top_limit: int = Query(default=5, ge=1, le=20),
) -> PlainTextResponse:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    payload = _generate_weekly_report_payload(
        days=days,
        top_limit=top_limit,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    content = _render_weekly_report_markdown(
        {
            **payload,
            "filters": filters["filter_meta"],
        }
    )
    headers = {"Content-Disposition": f"attachment; filename=admin_audit_weekly_brief_{days}d.md"}
    return PlainTextResponse(content=content, media_type="text/markdown", headers=headers)


@app.post("/api/admin/audit/weekly-report/write")
def api_admin_audit_weekly_report_write(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    top_limit: int = Query(default=5, ge=1, le=20),
    archive: bool = Query(default=True),
    publish: bool = Query(default=False),
) -> Dict[str, Any]:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    payload = _generate_weekly_report_payload(
        days=days,
        top_limit=top_limit,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    report_payload = {
        **payload,
        "filters": filters["filter_meta"],
    }
    output_paths = _write_weekly_report_artifacts(report_payload, archive=archive)
    result: Dict[str, Any] = {
        "ok": True,
        "days": days,
        "archive": archive,
        "published": publish,
        "total_filtered": payload.get("total_filtered", 0),
        "generated_at": payload.get("generated_at"),
        **output_paths,
    }
    if publish:
        result["publish"] = _publish_weekly_brief(report_payload)
    return result


@app.post("/api/admin/audit/weekly-report/publish")
def api_admin_audit_weekly_report_publish(
    _: Dict[str, str] = Depends(require_admin),
    days: int = Query(default=7, ge=1, le=60),
    action: str | None = Query(default=None),
    card_id: str | None = Query(default=None),
    actor: str | None = Query(default=None),
    from_ts: str | None = Query(default=None),
    to_ts: str | None = Query(default=None),
    top_limit: int = Query(default=5, ge=1, le=20),
    save: bool = Query(default=False),
    archive: bool = Query(default=True),
) -> Dict[str, Any]:
    filters = _resolve_audit_filters(
        action=action,
        card_id=card_id,
        actor=actor,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    payload = _generate_weekly_report_payload(
        days=days,
        top_limit=top_limit,
        action=filters["action"],
        card_id=filters["card_id"],
        actor=filters["actor"],
        from_timestamp=filters["from_timestamp"],
        to_timestamp=filters["to_timestamp"],
    )
    report_payload = {
        **payload,
        "filters": filters["filter_meta"],
    }

    result: Dict[str, Any] = {
        "ok": True,
        "days": days,
        "saved": save,
        "archive": archive,
        "total_filtered": payload.get("total_filtered", 0),
        "generated_at": payload.get("generated_at"),
        "publish": _publish_weekly_brief(report_payload),
    }
    if save:
        result.update(_write_weekly_report_artifacts(report_payload, archive=archive))
    return result


@app.post("/api/admin/cards/{card_id}/status")
def api_admin_update_status(
    card_id: str,
    payload: StatusUpdateRequest,
    request: Request,
    admin: Dict[str, str] = Depends(require_admin),
) -> Dict[str, Any]:
    before_card = _find_card(state.get_snapshot(), card_id)
    normalized = normalize_status(payload.status)
    if normalized not in ALLOWED_STATUSES:
        normalized = "published"

    updated = persistence.upsert_editorial_state(card_id=card_id, status=normalized)
    _set_state_with_editorial(state.get_snapshot())
    after_card = _find_card(state.get_snapshot(), card_id)
    details: Dict[str, Any] = {
        "from_status": before_card.get("status") if before_card else None,
        "to_status": after_card.get("status") if after_card else updated.get("status"),
    }
    request_meta = _request_meta(request)
    if request_meta:
        details["request"] = request_meta

    persistence.append_audit_log(
        actor=admin["username"],
        action="status_update",
        card_id=card_id,
        details=details,
    )

    return {
        "ok": True,
        "card_id": card_id,
        "editorial": updated,
    }


@app.post("/api/admin/cards/{card_id}/pin")
def api_admin_update_pin(
    card_id: str,
    payload: PinUpdateRequest,
    request: Request,
    admin: Dict[str, str] = Depends(require_admin),
) -> Dict[str, Any]:
    before_card = _find_card(state.get_snapshot(), card_id)
    updated = persistence.upsert_editorial_state(
        card_id=card_id,
        is_pinned=payload.pinned,
        pin_rank=payload.pin_rank,
    )
    _set_state_with_editorial(state.get_snapshot())
    after_card = _find_card(state.get_snapshot(), card_id)
    details = {
        "from_is_pinned": before_card.get("is_pinned") if before_card else None,
        "to_is_pinned": after_card.get("is_pinned") if after_card else updated.get("is_pinned"),
        "from_pin_rank": before_card.get("pin_rank") if before_card else None,
        "to_pin_rank": after_card.get("pin_rank") if after_card else updated.get("pin_rank"),
    }
    request_meta = _request_meta(request)
    if request_meta:
        details["request"] = request_meta

    persistence.append_audit_log(
        actor=admin["username"],
        action="pin_update",
        card_id=card_id,
        details=details,
    )

    return {
        "ok": True,
        "card_id": card_id,
        "editorial": updated,
    }


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt() -> str:
    base_url = _public_base_url()
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /api/admin/",
            f"Sitemap: {base_url}/sitemap.xml",
            "",
        ]
    )


@app.get("/sitemap.xml", response_class=PlainTextResponse)
def sitemap_xml() -> PlainTextResponse:
    base_url = _public_base_url()
    now_iso = datetime.now(tz=timezone.utc).date().isoformat()
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n"
        "  <url>\n"
        f"    <loc>{base_url}/</loc>\n"
        f"    <lastmod>{now_iso}</lastmod>\n"
        "    <changefreq>hourly</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/privacy</loc>\n"
        f"    <lastmod>{now_iso}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/terms</loc>\n"
        f"    <lastmod>{now_iso}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/affiliate-disclosure</loc>\n"
        f"    <lastmod>{now_iso}</lastmod>\n"
        "    <changefreq>monthly</changefreq>\n"
        "    <priority>0.5</priority>\n"
        "  </url>\n"
        "  <url>\n"
        f"    <loc>{base_url}/feed.xml</loc>\n"
        f"    <lastmod>{now_iso}</lastmod>\n"
        "    <changefreq>hourly</changefreq>\n"
        "    <priority>0.6</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
    return PlainTextResponse(xml, media_type="application/xml")


@app.get("/feed.xml", response_class=PlainTextResponse)
def feed_xml() -> PlainTextResponse:
    snapshot = state.get_snapshot()
    xml = _build_rss_xml(snapshot, base_url=_public_base_url())
    return PlainTextResponse(xml, media_type="application/rss+xml")


@app.get("/rss.xml", response_class=PlainTextResponse)
def rss_xml() -> PlainTextResponse:
    snapshot = state.get_snapshot()
    xml = _build_rss_xml(snapshot, base_url=_public_base_url())
    return PlainTextResponse(xml, media_type="application/rss+xml")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _render_web_html("index.html")


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page() -> str:
    return _render_web_html("privacy.html")


@app.get("/terms", response_class=HTMLResponse)
def terms_page() -> str:
    return _render_web_html("terms.html")


@app.get("/affiliate-disclosure", response_class=HTMLResponse)
def affiliate_disclosure_page() -> str:
    return _render_web_html("affiliate-disclosure.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page(_: Dict[str, str] = Depends(require_admin)) -> str:
    html_path = WEB_DIR / "admin.html"
    return html_path.read_text(encoding="utf-8")
