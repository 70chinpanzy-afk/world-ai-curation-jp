"""Load and validate source settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "sources.yaml"


@dataclass
class SourceDefinition:
    name: str
    kind: str
    tier: str
    url: str
    is_active: bool = True
    params: Dict[str, Any] | None = None


@dataclass
class SourceSettings:
    policy: Dict[str, Any]
    sources: List[SourceDefinition]


def _to_source_definition(item: Dict[str, Any]) -> SourceDefinition:
    return SourceDefinition(
        name=str(item["name"]),
        kind=str(item["kind"]),
        tier=str(item["tier"]),
        url=str(item["url"]),
        is_active=bool(item.get("is_active", True)),
        params=item.get("params"),
    )


def load_source_settings(config_path: Path | None = None) -> SourceSettings:
    path = config_path or DEFAULT_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    policy = raw.get("policy", {})
    source_items = raw.get("sources", [])

    sources = [_to_source_definition(item) for item in source_items]
    return SourceSettings(policy=policy, sources=sources)
