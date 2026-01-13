from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass
class AnalysisResult:
    market_fit: int | None
    recommendations: list[str]
    raw: Any
    prompt_used: str


def _extract_json_object(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    candidate = match.group(0)
    try:
        data = json.loads(candidate)
        if isinstance(data, dict):
            return data
        return None
    except json.JSONDecodeError:
        return None


def _as_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _json_default(obj: Any):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def analyze_app(*, app_id: str, meta: dict[str, Any], scenario: str, user_context: str | None) -> AnalysisResult:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY is not set")

    client = OpenAI(api_key=api_key, base_url="https://api.perplexity.ai")

    prompt = (
        "You are a product analyst. Return JSON only (no markdown, no code fences). "
        "Schema: {\"market_fit\": int 0..10, \"recommendations\": [string], \"notes\": string}. "
        f"Scenario: {scenario}. "
        f"User context: {user_context or ''}. "
        f"App id: {app_id}. "
        "App data: "
        + json.dumps(meta, ensure_ascii=False, default=_json_default)
    )

    response = client.chat.completions.create(
        model=os.getenv("PERPLEXITY_MODEL") or "sonar-pro",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    content = (response.choices[0].message.content or "").strip()
    parsed = _extract_json_object(content)
    raw = {"content": content}
    if parsed is not None:
        raw = parsed

    market_fit = _as_int((parsed or {}).get("market_fit"))
    recs = (parsed or {}).get("recommendations")
    if not isinstance(recs, list):
        recs = []
    recs_str = [str(x) for x in recs if x is not None]

    return AnalysisResult(market_fit=market_fit, recommendations=recs_str, raw=raw, prompt_used=prompt)
