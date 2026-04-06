"""Simple JSON snapshot storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT_DIR / "data" / "cards_cache.json"


def load_snapshot(cache_path: Path | None = None) -> Dict[str, Any]:
    path = cache_path or CACHE_PATH
    if not path.exists():
        return {"generated_at": None, "cards": [], "errors": []}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(snapshot: Dict[str, Any], cache_path: Path | None = None) -> None:
    path = cache_path or CACHE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
