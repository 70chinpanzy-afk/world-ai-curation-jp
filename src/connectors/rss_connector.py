"""RSS connector for global AI source ingestion."""

from __future__ import annotations

import html
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from time import struct_time
from typing import List, Tuple

import feedparser

from ..curation_pipeline import SourceItem
from ..source_config import SourceDefinition


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_ANCHOR_RE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)


def _strip_html(text: str) -> str:
    no_tags = _HTML_TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", no_tags).strip()


def _clean_anchor_text(text: str) -> str:
    return html.unescape(_strip_html(text))


def _to_datetime(value: struct_time | None) -> datetime:
    if value is None:
        return datetime.now(tz=timezone.utc)
    return datetime(*value[:6], tzinfo=timezone.utc)


def _recency_novelty(published_at: datetime) -> float:
    age_days = (datetime.now(tz=timezone.utc) - published_at).total_seconds() / 86400.0
    if age_days <= 1:
        return 0.9
    if age_days <= 3:
        return 0.75
    if age_days <= 7:
        return 0.6
    return 0.45


def _keyword_score(text: str, high_terms: List[str], medium_terms: List[str], low_terms: List[str]) -> float:
    lowered = text.lower()
    if any(term in lowered for term in high_terms):
        return 0.9
    if any(term in lowered for term in medium_terms):
        return 0.7
    if any(term in lowered for term in low_terms):
        return 0.55
    return 0.5


def _impact_hint(title: str, summary: str) -> float:
    text = f"{title} {summary}"
    return _keyword_score(
        text,
        high_terms=["release", "launch", "open source", "benchmark", "state of the art", "funding"],
        medium_terms=["update", "roadmap", "expansion", "integration", "new model"],
        low_terms=["talk", "podcast", "opinion"],
    )


def _actionability_hint(title: str, summary: str) -> float:
    text = f"{title} {summary}"
    return _keyword_score(
        text,
        high_terms=["api", "sdk", "tutorial", "guide", "github", "code"],
        medium_terms=["documentation", "paper", "example", "dataset"],
        low_terms=["announcement", "future", "teaser"],
    )


def _normalize_link(base_url: str, href: str) -> str | None:
    raw = href.strip()
    if not raw or raw.startswith("#"):
        return None
    if raw.lower().startswith(("javascript:", "mailto:", "tel:")):
        return None

    absolute = urllib.parse.urljoin(base_url, raw)
    parsed = urllib.parse.urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    return absolute


def _looks_like_article_path(path: str) -> bool:
    normalized = path.strip().lower().rstrip("/")
    if not normalized or normalized in {"/", "/news"}:
        return False
    if normalized.count("/") < 2:
        return False
    tail = normalized.rsplit("/", 1)[-1]
    return len(tail) >= 6 and ("-" in tail or any(ch.isdigit() for ch in tail))


def _extract_website_article_links(html_text: str, base_url: str, limit: int) -> List[Tuple[str, str]]:
    base_parsed = urllib.parse.urlparse(base_url)
    base_host = base_parsed.netloc.lower()
    base_path = base_parsed.path.rstrip("/")

    links: List[Tuple[str, str]] = []
    seen_urls = set()

    for href, inner in _ANCHOR_RE.findall(html_text):
        url = _normalize_link(base_url, href)
        if not url:
            continue
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc.lower() != base_host:
            continue
        if parsed.path.rstrip("/") == base_path:
            continue
        if not _looks_like_article_path(parsed.path):
            continue

        title = _clean_anchor_text(inner)
        if len(title) < 8:
            continue
        if len(title) > 150:
            title = title[:150].rstrip() + "..."

        if url in seen_urls:
            continue
        seen_urls.add(url)
        links.append((url, title))
        if len(links) >= limit:
            break

    return links


def _fetch_website_items(source: SourceDefinition, limit: int = 20) -> Tuple[List[SourceItem], str | None]:
    req = urllib.request.Request(source.url, headers={"User-Agent": "Mozilla/5.0"})
    timeout_seconds = int(os.getenv("RSS_HTTP_TIMEOUT_SECONDS", "20"))
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8", "ignore")
    except Exception as exc:
        return [], f"Website fetch failed for {source.name}: {exc}"

    links = _extract_website_article_links(payload, source.url, limit)
    if not links:
        return [], f"Website parse failed for {source.name}: no article links found."

    now = datetime.now(tz=timezone.utc)
    items: List[SourceItem] = []
    for url, title in links:
        summary = title
        items.append(
            SourceItem(
                source_name=source.name,
                source_tier=source.tier,
                title=title,
                url=url,
                published_at=now,
                language="en",
                summary=summary[:500],
                novelty_hint=_recency_novelty(now),
                impact_hint=_impact_hint(title, summary),
                actionability_hint=_actionability_hint(title, summary),
            )
        )
    return items, None


def fetch_rss_items(source: SourceDefinition, limit: int = 20) -> Tuple[List[SourceItem], str | None]:
    timeout_seconds = int(os.getenv("RSS_HTTP_TIMEOUT_SECONDS", "8"))
    try:
        req = urllib.request.Request(source.url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read()
        parsed = feedparser.parse(payload)
    except Exception as exc:
        if source.kind == "website":
            website_items, website_err = _fetch_website_items(source, limit=limit)
            if website_items:
                return website_items, None
            if website_err:
                return [], f"RSS parse failed for {source.name}: {exc}; {website_err}"
        return [], f"RSS parse failed for {source.name}: {exc}"

    if getattr(parsed, "bozo", False):
        exc = getattr(parsed, "bozo_exception", None)
        if exc and not parsed.entries:
            if source.kind == "website":
                website_items, website_err = _fetch_website_items(source, limit=limit)
                if website_items:
                    return website_items, None
                if website_err:
                    return [], f"RSS parse failed for {source.name}: {exc}; {website_err}"
            return [], f"RSS parse failed for {source.name}: {exc}"

    feed_lang = str(getattr(parsed.feed, "language", "en") or "en")
    items: List[SourceItem] = []

    for entry in parsed.entries[:limit]:
        title = str(getattr(entry, "title", "(untitled)")).strip()
        url = str(getattr(entry, "link", source.url)).strip()
        summary_raw = str(getattr(entry, "summary", "") or getattr(entry, "description", ""))
        summary = _strip_html(summary_raw)[:500]
        published_struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
        published_at = _to_datetime(published_struct)

        novelty = _recency_novelty(published_at)
        impact = _impact_hint(title, summary)
        actionability = _actionability_hint(title, summary)

        items.append(
            SourceItem(
                source_name=source.name,
                source_tier=source.tier,
                title=title,
                url=url,
                published_at=published_at,
                language=feed_lang,
                summary=summary or "No summary available.",
                novelty_hint=novelty,
                impact_hint=impact,
                actionability_hint=actionability,
            )
        )

    return items, None
