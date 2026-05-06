from __future__ import annotations

import json

from openai import AsyncOpenAI

from app.core.config import Settings
from app.schemas.agent import AgentDecision
from app.tools.community_dimension_tools import DimensionToolResult

_DIMENSIONS = ["safety", "transit", "convenience", "parking", "environment"]

_PLANNER_SYSTEM_PROMPT = """You are the RentWise agent planner.
You inspect observations from deterministic data tools and decide whether each dimension should be accepted, retried once, or marked failed.

Return only a valid JSON object:
{
  "decisions": [
    {"dimension": "safety", "action": "accept|retry|fail", "reason": "..."}
  ]
}

Rules:
1. Never invent metric values.
2. Accept successful tool results unless the observation says important fields are missing.
3. Retry only when a repeat request might reasonably help, such as transient API failure, timeout, flaky Overpass/source failure, or partial missing fields.
4. Fail instead of retry when coordinates are missing, required API keys appear unavailable, or the failure is not recoverable by repeating the same request.
5. Include exactly one decision for each of the five dimensions."""


async def plan_dimension_followup(
    settings: Settings,
    community_name: str,
    city: str | None,
    state: str | None,
    tool_results: list[DimensionToolResult],
) -> list[AgentDecision]:
    if not settings.openai_api_key:
        return _fallback_decisions(tool_results)

    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=20.0)
    observations = [
        {
            "dimension": result.dimension,
            "status": result.status,
            "source": result.source,
            "confidence": result.confidence,
            "missing_fields": result.missing_fields,
            "detail": result.detail,
            "metrics_returned": sorted(result.metrics.keys()),
        }
        for result in tool_results
    ]
    prompt = json.dumps(
        {
            "community": {
                "name": community_name,
                "city": city,
                "state": state,
            },
            "tool_observations": observations,
        },
        ensure_ascii=True,
    )

    try:
        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=500,
        )
        raw = completion.choices[0].message.content or ""
        data = json.loads(raw)
    except Exception:
        return _fallback_decisions(tool_results)

    return _sanitize_decisions(data.get("decisions"), tool_results)


def _sanitize_decisions(
    payload,
    tool_results: list[DimensionToolResult],
) -> list[AgentDecision]:
    by_dimension = {result.dimension: result for result in tool_results}
    raw_by_dimension = {}
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            dimension = str(item.get("dimension") or "").strip().lower()
            if dimension in _DIMENSIONS:
                raw_by_dimension[dimension] = item

    decisions = []
    for dimension in _DIMENSIONS:
        result = by_dimension.get(dimension)
        raw = raw_by_dimension.get(dimension, {})
        action = str(raw.get("action") or "").strip().lower()
        if action not in {"accept", "retry", "fail"}:
            action = _fallback_action(result)
        reason = str(raw.get("reason") or "").strip()
        if not reason:
            reason = _fallback_reason(result, action)
        decisions.append(
            AgentDecision(
                dimension=dimension,
                action=action,
                reason=reason,
            )
        )
    return decisions


def _fallback_decisions(tool_results: list[DimensionToolResult]) -> list[AgentDecision]:
    by_dimension = {result.dimension: result for result in tool_results}
    return [
        AgentDecision(
            dimension=dimension,
            action=_fallback_action(by_dimension.get(dimension)),
            reason=_fallback_reason(
                by_dimension.get(dimension),
                _fallback_action(by_dimension.get(dimension)),
            ),
        )
        for dimension in _DIMENSIONS
    ]


def _fallback_action(result: DimensionToolResult | None) -> str:
    if result is None:
        return "fail"
    if result.status == "success" and not result.missing_fields:
        return "accept"
    return "fail"


def _fallback_reason(result: DimensionToolResult | None, action: str) -> str:
    if result is None:
        return "No tool observation was available for this dimension."
    if action == "accept":
        return "The deterministic tool returned the required metric fields."
    if action == "retry":
        return "The tool result looked transient or incomplete, so one retry is allowed."
    return result.detail or "The deterministic tool did not return enough data."
