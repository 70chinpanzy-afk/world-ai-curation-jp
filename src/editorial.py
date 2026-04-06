"""Editorial state helpers for admin workflow."""

from __future__ import annotations

from typing import Any, Dict, List


ALLOWED_STATUSES = {"draft", "published", "archived"}
DEFAULT_STATUS = "published"
DEFAULT_PINNED = False
DEFAULT_PIN_RANK = 1000


def normalize_status(value: str | None) -> str:
    status = (value or DEFAULT_STATUS).strip().lower()
    if status not in ALLOWED_STATUSES:
        return DEFAULT_STATUS
    return status


def normalize_editorial_state(raw: Dict[str, Any] | None) -> Dict[str, Any]:
    raw = raw or {}
    return {
        "status": normalize_status(str(raw.get("status", DEFAULT_STATUS))),
        "is_pinned": bool(raw.get("is_pinned", DEFAULT_PINNED)),
        "pin_rank": int(raw.get("pin_rank", DEFAULT_PIN_RANK)),
        "updated_at": raw.get("updated_at"),
    }


def apply_editorial_state(cards: List[Dict[str, Any]], editorial_states: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    decorated: List[Dict[str, Any]] = []

    for card in cards:
        card_id = str(card.get("id", ""))
        editorial = normalize_editorial_state(editorial_states.get(card_id, {}))

        updated = dict(card)
        updated["editorial"] = editorial
        updated["status"] = editorial["status"]
        updated["is_pinned"] = editorial["is_pinned"]
        updated["pin_rank"] = editorial["pin_rank"]

        decorated.append(updated)

    return decorated


def sort_for_public_feed(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        cards,
        key=lambda c: (
            0 if c.get("is_pinned") else 1,
            int(c.get("pin_rank", DEFAULT_PIN_RANK)),
            -float(c.get("score_total", 0)),
        ),
    )
