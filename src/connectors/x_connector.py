"""X (Twitter) API connector for secondary signal ingestion."""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from ..curation_pipeline import SourceItem
from ..source_config import SourceDefinition


def _to_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(tz=timezone.utc)

    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return datetime.now(tz=timezone.utc)


def _recency_novelty(published_at: datetime) -> float:
    age_days = (datetime.now(tz=timezone.utc) - published_at).total_seconds() / 86400.0
    if age_days <= 1:
        return 0.9
    if age_days <= 3:
        return 0.75
    if age_days <= 7:
        return 0.6
    return 0.45


def _impact_hint(text: str) -> float:
    lowered = text.lower()
    if any(term in lowered for term in ["release", "launch", "benchmark", "open source", "funding"]):
        return 0.75
    if any(term in lowered for term in ["update", "new model", "paper", "demo"]):
        return 0.6
    return 0.45


def _actionability_hint(text: str) -> float:
    lowered = text.lower()
    if any(term in lowered for term in ["api", "sdk", "github", "code", "tutorial", "example"]):
        return 0.65
    if any(term in lowered for term in ["guide", "how to", "prompt"]):
        return 0.55
    return 0.4


def _normalize_queries(source: SourceDefinition) -> List[str]:
    raw_queries: List[str] = []
    params = source.params or {}

    if isinstance(params.get("queries"), list):
        for query in params["queries"]:
            if isinstance(query, str) and query.strip():
                raw_queries.append(query.strip())

    env_queries = os.getenv("X_SEARCH_QUERIES", "")
    if env_queries:
        for query in env_queries.split("||"):
            if query.strip():
                raw_queries.append(query.strip())

    if not raw_queries:
        raw_queries = ["AI OR LLM (launch OR release OR benchmark) -is:retweet lang:en"]

    deduped: List[str] = []
    seen = set()
    for query in raw_queries:
        if query in seen:
            continue
        seen.add(query)
        deduped.append(query)
    return deduped


def _request_json(url: str, token: str) -> Dict:
    req = urllib.request.Request(
        url=url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    timeout_seconds = int(os.getenv("X_HTTP_TIMEOUT_SECONDS", "15"))
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        payload = response.read().decode("utf-8")
    return json.loads(payload)


def fetch_x_items(source: SourceDefinition, limit: int = 20) -> Tuple[List[SourceItem], str | None]:
    token = os.getenv("X_BEARER_TOKEN")
    if not token:
        return [], None

    queries = _normalize_queries(source)
    max_per_query = max(10, min(limit, 100))

    seen_tweet_ids = set()
    items: List[SourceItem] = []
    errors: List[str] = []

    base_url = source.url.rstrip("/")

    for query in queries:
        encoded_query = urllib.parse.quote(query)
        endpoint = (
            f"{base_url}/2/tweets/search/recent"
            f"?query={encoded_query}"
            f"&max_results={max_per_query}"
            "&tweet.fields=created_at,lang,author_id,public_metrics"
        )

        try:
            data = _request_json(endpoint, token=token)
        except Exception as exc:  # pragma: no cover
            errors.append(f"X query failed ({query}): {exc}")
            continue

        for tweet in data.get("data", []):
            tweet_id = str(tweet.get("id", "")).strip()
            if not tweet_id or tweet_id in seen_tweet_ids:
                continue

            seen_tweet_ids.add(tweet_id)
            text = str(tweet.get("text", "")).strip()
            if not text:
                continue

            published_at = _to_datetime(tweet.get("created_at"))
            novelty = _recency_novelty(published_at)
            impact = _impact_hint(text)
            actionability = _actionability_hint(text)

            short = text.replace("\n", " ")
            title = short[:110] + ("..." if len(short) > 110 else "")
            url = f"https://x.com/i/web/status/{tweet_id}"

            items.append(
                SourceItem(
                    source_name=source.name,
                    source_tier=source.tier,
                    title=title,
                    url=url,
                    published_at=published_at,
                    language=str(tweet.get("lang") or "en"),
                    summary=text[:500],
                    novelty_hint=novelty,
                    impact_hint=impact,
                    actionability_hint=actionability,
                )
            )

    error_message = "; ".join(errors) if errors else None
    return items[:limit], error_message
