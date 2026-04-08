"""Optional LLM-based variant enrichment."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, Tuple

from .curation_pipeline import CardVariants, SourceItem


def _extract_output_text(payload: Dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]

    outputs = payload.get("output", [])
    for output in outputs:
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                return content["text"]
    return ""


def _openai_enrich(item: SourceItem, base: CardVariants, score_breakdown: Dict[str, float]) -> Tuple[CardVariants, Dict[str, Any]]:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return base, {"enabled": False, "provider": "openai", "reason": "OPENAI_API_KEY is not set"}

    model = (os.getenv("OPENAI_MODEL", "gpt-5-mini") or "gpt-5-mini").strip()
    base_url = (os.getenv("OPENAI_BASE_URL", "https://api.openai.com") or "https://api.openai.com").strip()
    timeout_seconds = int(os.getenv("OPENAI_HTTP_TIMEOUT_SECONDS", "30"))

    prompt = (
        "あなたはAIニュース編集者です。以下の入力から日本語で3種類の本文をJSONだけで出力してください。\n"
        "必須キー: raw, vibe, builder。\n"
        "rawは事実中心、vibeは非エンジニア向け、builderは実装志向。\n"
        "誇張しない。根拠のない断定をしない。\n\n"
        f"title: {item.title}\n"
        f"summary: {item.summary}\n"
        f"source_name: {item.source_name}\n"
        f"source_tier: {item.source_tier}\n"
        f"url: {item.url}\n"
        f"score: {json.dumps(score_breakdown, ensure_ascii=False)}\n"
    )

    body = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
    }

    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/v1/responses",
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(body).encode("utf-8"),
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))

        text = _extract_output_text(payload)
        data = json.loads(text)
        enriched = CardVariants(
            raw=str(data.get("raw", base.raw)),
            vibe=str(data.get("vibe", base.vibe)),
            builder=str(data.get("builder", base.builder)),
        )
        return enriched, {"enabled": True, "provider": "openai", "model": model, "reason": "ok"}
    except Exception as exc:  # pragma: no cover
        return base, {"enabled": False, "provider": "openai", "model": model, "reason": f"fallback: {exc}"}


def enrich_variants(item: SourceItem, base: CardVariants, score_breakdown: Dict[str, float]) -> Tuple[CardVariants, Dict[str, Any]]:
    provider = (os.getenv("LLM_PROVIDER", "none") or "none").strip().lower()
    if provider == "openai":
        return _openai_enrich(item=item, base=base, score_breakdown=score_breakdown)

    return base, {"enabled": False, "provider": provider or "none", "reason": "LLM provider disabled"}
