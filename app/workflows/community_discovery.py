from __future__ import annotations

import json
from datetime import datetime
from urllib.parse import urlparse

from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.agents.dimension_planner import plan_dimension_followup
from app.core.config import Settings
from app.db import crud
from app.schemas.agent import (
    AgentToolCall,
    AgentTraceStep,
    CommunityDiscoveryResponse,
    DimensionEstimate,
    DiscoveredCommunityProfile,
)
from app.schemas.insight import CommunityWebSource
from app.services.fetchers.geocoding import geocode_community
from app.services.scoring_service import PREFERENCE_DIMENSIONS, compute_preference_scores
from app.tools.community_dimension_tools import (
    DimensionToolResult,
    fetch_all_dimension_tools_async,
    fetch_selected_dimension_tools_async,
)

_DIMENSIONS = ["safety", "transit", "convenience", "parking", "environment"]

_DISCOVERY_SYSTEM_PROMPT = """You create provisional neighborhood discovery profiles for renters.
Use web search to gather stable public information about the requested community.

Return only a valid JSON object. Do not include markdown.

Rules:
1. Treat all dimension scores as estimates, not verified metrics.
2. Prefer cautious language when evidence is weak.
3. Do not invent exact crime rates, rent prices, commute times, or parking availability.
4. If a dimension has weak evidence, set score_0_100 to null and confidence to "low".
5. Focus on renter-useful basics: location, nearby amenities, transportation context, parks/green space, neighborhood character, and repeated public signals."""

_DISCOVERY_SCHEMA = {
    "type": "object",
    "properties": {
        "profile": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "city": {"type": ["string", "null"]},
                "state": {"type": ["string", "null"]},
            },
            "required": ["name", "city", "state"],
            "additionalProperties": False,
        },
        "summary": {"type": "string"},
        "dimensions": {
            "type": "object",
            "properties": {
                dimension: {
                    "type": "object",
                    "properties": {
                        "score_0_100": {"type": ["number", "null"]},
                        "summary": {"type": "string"},
                        "confidence": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                    },
                    "required": ["score_0_100", "summary", "confidence"],
                    "additionalProperties": False,
                }
                for dimension in _DIMENSIONS
            },
            "required": _DIMENSIONS,
            "additionalProperties": False,
        },
        "overall_confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "missing_fields": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "profile",
        "summary",
        "dimensions",
        "overall_confidence",
        "missing_fields",
    ],
    "additionalProperties": False,
}


async def run_community_discovery_workflow(
    db: Session,
    community_name: str,
    settings: Settings,
    city: str | None = None,
    state: str | None = None,
) -> CommunityDiscoveryResponse:
    normalized_query = _normalize_query(
        ", ".join(part for part in [community_name, city, state] if part)
    )
    tool_calls: list[AgentToolCall] = []
    trace: list[AgentTraceStep] = []

    geocoded = geocode_community(normalized_query)
    tool_calls.append(
        AgentToolCall(
            name="geocode_community",
            status="success" if geocoded else "failed",
            detail=None if geocoded else "No coordinates returned.",
        )
    )
    trace.append(
        AgentTraceStep(
            step="geocode",
            status="success" if geocoded else "failed",
            message=(
                "Resolved the community to coordinates."
                if geocoded
                else "Could not resolve coordinates for this community."
            ),
            detail={
                "query": normalized_query,
                "lat": geocoded.get("lat") if geocoded else None,
                "lng": geocoded.get("lng") if geocoded else None,
            },
        )
    )
    fallback_profile = _build_profile(
        community_name=community_name,
        city=city,
        state=state,
        geocoded=geocoded,
    )
    community = _get_or_create_discovered_community(db, fallback_profile)
    tool_calls.append(
        AgentToolCall(
            name="create_or_reuse_community",
            status="success",
            detail=community.community_id,
        )
    )
    trace.append(
        AgentTraceStep(
            step="community_record",
            status="success",
            message="Created or reused a community record for discovery.",
            detail={"community_id": community.community_id},
        )
    )

    dimension_tool_results = await fetch_all_dimension_tools_async(
        settings=settings,
        name=community.name,
        city=community.city,
        state=community.state,
        center_lat=community.center_lat,
        center_lng=community.center_lng,
    )
    tool_calls.extend(_dimension_tool_calls(dimension_tool_results))
    trace.append(_dimension_fetch_trace(dimension_tool_results))
    agent_decisions = await plan_dimension_followup(
        settings=settings,
        community_name=community.name,
        city=community.city,
        state=community.state,
        tool_results=dimension_tool_results,
    )
    tool_calls.append(
        AgentToolCall(
            name="llm_plan_dimension_followup",
            status="success" if settings.openai_api_key else "skipped",
            detail=_agent_decision_detail(agent_decisions),
        )
    )
    trace.append(
        AgentTraceStep(
            step="llm_followup_decision",
            status="success" if settings.openai_api_key else "skipped",
            message=(
                "LLM reviewed tool observations and selected follow-up actions."
                if settings.openai_api_key
                else "LLM planner was skipped because no OpenAI API key is configured."
            ),
            detail={
                "decisions": [
                    {
                        "dimension": decision.dimension,
                        "action": decision.action,
                        "reason": decision.reason,
                    }
                    for decision in agent_decisions
                ]
            },
        )
    )

    retry_dimensions = [
        decision.dimension
        for decision in agent_decisions
        if decision.action == "retry"
    ]
    if retry_dimensions:
        trace.append(
            AgentTraceStep(
                step="dimension_retry",
                status="partial",
                message="Retrying dimensions selected by the LLM planner.",
                detail={"dimensions": retry_dimensions},
            )
        )
        retry_results = await fetch_selected_dimension_tools_async(
            settings=settings,
            dimensions=retry_dimensions,
            name=community.name,
            city=community.city,
            state=community.state,
            center_lat=community.center_lat,
            center_lng=community.center_lng,
        )
        tool_calls.extend(_dimension_tool_calls(retry_results, prefix="retry_"))
        dimension_tool_results = _merge_retry_results(
            dimension_tool_results,
            retry_results,
        )
    else:
        trace.append(
            AgentTraceStep(
                step="dimension_retry",
                status="skipped",
                message="No dimensions were selected for retry.",
                detail={"dimensions": []},
            )
        )

    metrics_payload = _build_metrics_payload(dimension_tool_results)
    crud.upsert_metrics(db, community.community_id, metrics_payload)
    metrics = crud.get_metrics(db, community.community_id)
    tool_calls.append(
        AgentToolCall(
            name="upsert_dimension_metrics",
            status="success" if metrics else "failed",
            detail=None if metrics else "No metrics row was produced.",
        )
    )
    trace.append(
        AgentTraceStep(
            step="metrics_persistence",
            status="success" if metrics else "failed",
            message=(
                "Persisted collected dimension metrics."
                if metrics
                else "Failed to persist collected dimension metrics."
            ),
            detail={"community_id": community.community_id},
        )
    )

    dimensions = _build_api_dimension_estimates(metrics, dimension_tool_results)
    _upsert_dimension_scores(
        db=db,
        community_id=community.community_id,
        dimensions=dimensions,
        metrics=metrics,
        tool_results=dimension_tool_results,
    )
    tool_calls.append(
        AgentToolCall(
            name="compute_preference_scores",
            status="success" if dimensions else "failed",
            detail=None if dimensions else "No dimension scores were produced.",
        )
    )
    trace.append(
        AgentTraceStep(
            step="score_dimensions",
            status="success" if dimensions else "failed",
            message=(
                "Computed standardized RentWise dimension scores."
                if dimensions
                else "Could not compute dimension scores."
            ),
            detail={"dimension_count": len(dimensions)},
        )
    )

    web_result = await _generate_web_discovery(
        settings=settings,
        community_name=community_name,
        city=city or fallback_profile.city,
        state=state or fallback_profile.state,
        geocoded=geocoded,
    )
    tool_calls.append(
        AgentToolCall(
            name="web_search_summary",
            status="success" if web_result else "skipped",
            detail=None if web_result else "Used only as a fallback/enrichment source.",
        )
    )
    trace.append(
        AgentTraceStep(
            step="web_summary",
            status="success" if web_result else "skipped",
            message=(
                "Used web search to enrich the community summary."
                if web_result
                else "Web summary enrichment was skipped or unavailable."
            ),
            detail={"source_count": len(web_result["sources"]) if web_result else 0},
        )
    )

    if dimensions:
        web_profile = web_result["profile"] if web_result else None
        profile = web_profile or fallback_profile
        missing_fields = _metrics_missing_fields(metrics, dimension_tool_results)
        if web_result:
            missing_fields.extend(
                field
                for field in web_result["missing_fields"]
                if field not in missing_fields
            )
        trace.append(
            AgentTraceStep(
                step="finalize_discovery",
                status="partial" if missing_fields else "success",
                message=(
                    "Discovery completed with missing or low-confidence fields."
                    if missing_fields
                    else "Discovery completed with all five dimensions populated."
                ),
                detail={"missing_fields": missing_fields},
            )
        )
        return CommunityDiscoveryResponse(
            status="partial" if missing_fields else "discovered",
            query=community_name,
            normalized_query=normalized_query,
            source="api",
            profile=DiscoveredCommunityProfile(
                name=profile.name or fallback_profile.name,
                city=profile.city or fallback_profile.city,
                state=profile.state or fallback_profile.state,
                display_name=fallback_profile.display_name,
                center_lat=fallback_profile.center_lat,
                center_lng=fallback_profile.center_lng,
            ),
            summary=web_result["summary"] if web_result else _api_summary(profile.name),
            dimensions=dimensions,
            overall_confidence=_overall_confidence(metrics),
            missing_fields=missing_fields,
            sources=web_result["sources"] if web_result else [],
            matched_community_id=community.community_id,
            tool_calls=tool_calls,
            agent_decisions=agent_decisions,
            agent_trace=trace,
        )

    fallback = _fallback_discovery_response(
        query=community_name,
        normalized_query=normalized_query,
        profile=fallback_profile,
        source="geocoding" if geocoded else "fallback",
    )
    fallback.matched_community_id = community.community_id
    fallback.tool_calls = tool_calls
    fallback.agent_decisions = agent_decisions
    fallback.agent_trace = trace
    return fallback


def _get_or_create_discovered_community(db: Session, profile: DiscoveredCommunityProfile):
    existing = crud.get_community_by_name(db, profile.name)
    if existing:
        return existing

    return crud.create_community(
        db=db,
        name=profile.name,
        city=profile.city,
        state=profile.state,
        center_lat=profile.center_lat,
        center_lng=profile.center_lng,
    )


def _dimension_tool_calls(
    results: list[DimensionToolResult],
    prefix: str = "",
) -> list[AgentToolCall]:
    return [
        AgentToolCall(
            name=f"{prefix}fetch_{result.dimension}_dimension",
            status="success" if result.status == "success" else "failed",
            detail=_tool_call_detail(result),
        )
        for result in results
    ]


def _dimension_fetch_trace(results: list[DimensionToolResult]) -> AgentTraceStep:
    success_count = sum(1 for result in results if result.status == "success")
    missing_dimensions = [
        result.dimension for result in results if result.status != "success"
    ]
    return AgentTraceStep(
        step="parallel_dimension_fetch",
        status=(
            "success"
            if success_count == len(results)
            else "partial"
            if success_count > 0
            else "failed"
        ),
        message=f"Fetched {success_count} of {len(results)} dimensions using parallel tools.",
        detail={
            "success_count": success_count,
            "total": len(results),
            "missing_dimensions": missing_dimensions,
        },
    )


def _agent_decision_detail(decisions) -> str:
    return "; ".join(
        f"{decision.dimension}:{decision.action}" for decision in decisions
    )


def _merge_retry_results(
    initial_results: list[DimensionToolResult],
    retry_results: list[DimensionToolResult],
) -> list[DimensionToolResult]:
    retry_by_dimension = {result.dimension: result for result in retry_results}
    merged = []
    for result in initial_results:
        retry = retry_by_dimension.get(result.dimension)
        if retry is None:
            merged.append(result)
        elif retry.status == "success" or result.status != "success":
            merged.append(retry)
        else:
            merged.append(result)
    return merged


def _tool_call_detail(result: DimensionToolResult) -> str:
    parts = [f"source={result.source}", f"confidence={result.confidence}"]
    if result.missing_fields:
        parts.append(f"missing={','.join(result.missing_fields)}")
    if result.detail:
        parts.append(result.detail)
    return "; ".join(parts)


def _build_metrics_payload(results: list[DimensionToolResult]) -> dict:
    metrics: dict[str, float | None] = {
        "updated_at": datetime.utcnow(),
        "overall_confidence": _numeric_confidence(results),
    }
    sources: dict[str, str | bool | list[str]] = {}

    for result in results:
        metrics.update(result.metrics)
        sources[f"{result.dimension}_tool"] = result.source
        sources[f"{result.dimension}_success"] = result.status == "success"
        if result.missing_fields:
            sources[f"{result.dimension}_missing_fields"] = result.missing_fields

    metrics["details_json"] = json.dumps(
        {
            "sources": sources,
            "agent_dimension_tools": [
                {
                    "dimension": result.dimension,
                    "status": result.status,
                    "source": result.source,
                    "confidence": result.confidence,
                    "missing_fields": result.missing_fields,
                }
                for result in results
            ],
        },
        ensure_ascii=True,
    )
    return metrics


def _numeric_confidence(results: list[DimensionToolResult]) -> float:
    if not results:
        return 0.0
    success_count = sum(1 for result in results if result.status == "success")
    return round(success_count / len(results), 2)


def _build_api_dimension_estimates(
    metrics,
    tool_results: list[DimensionToolResult],
) -> list[DimensionEstimate]:
    if metrics is None:
        return []

    score_input = _metrics_score_input(metrics)
    scores = compute_preference_scores(score_input)
    missing = set(_metrics_missing_fields(metrics, tool_results))
    result_by_dimension = {result.dimension: result for result in tool_results}

    dimensions = [
        DimensionEstimate(
            dimension=dimension,
            score_0_100=scores.get(dimension),
            summary=_dimension_summary(
                dimension,
                scores.get(dimension),
                missing,
                result_by_dimension.get(dimension),
            ),
            confidence=_dimension_confidence(
                dimension,
                missing,
                result_by_dimension.get(dimension),
            ),
            data_origin="api",
        )
        for dimension in PREFERENCE_DIMENSIONS
    ]
    return dimensions


def _upsert_dimension_scores(
    db: Session,
    community_id: str,
    dimensions: list[DimensionEstimate],
    metrics,
    tool_results: list[DimensionToolResult],
) -> None:
    if metrics is None:
        return

    score_input = _metrics_score_input(metrics)
    result_by_dimension = {result.dimension: result for result in tool_results}
    for dimension in dimensions:
        result = result_by_dimension.get(dimension.dimension)
        crud.upsert_dimension_score(
            db=db,
            community_id=community_id,
            dimension=dimension.dimension,
            score_0_100=dimension.score_0_100 or 0.0,
            summary=dimension.summary,
            details={
                "score_input": score_input,
                "tool": {
                    "status": result.status if result else "unknown",
                    "source": result.source if result else "unknown",
                    "confidence": result.confidence if result else dimension.confidence,
                    "missing_fields": result.missing_fields if result else [],
                },
            },
            data_origin=dimension.data_origin,
        )


def _metrics_score_input(metrics) -> dict[str, float | None]:
    return {
        "crime_rate_per_100k": metrics.crime_rate_per_100k,
        "commute_minutes": metrics.commute_minutes,
        "grocery_density_per_km2": metrics.grocery_density_per_km2,
        "noise_avg_db": metrics.noise_avg_db,
        "night_activity_index": metrics.night_activity_index,
        "parking_lot_density_per_km2": metrics.parking_lot_density_per_km2,
        "parking_capacity_per_km2": metrics.parking_capacity_per_km2,
        "poi_demand_density_per_km2": metrics.poi_demand_density_per_km2,
    }


def _metrics_missing_fields(
    metrics,
    tool_results: list[DimensionToolResult] | None = None,
) -> list[str]:
    if metrics is None:
        return [*_DIMENSIONS]

    missing = set()
    if metrics.crime_rate_per_100k is None:
        missing.add("safety")
    if metrics.commute_minutes is None:
        missing.add("transit")
    if metrics.grocery_density_per_km2 is None:
        missing.add("convenience")
    if (
        metrics.parking_lot_density_per_km2 is None
        and metrics.parking_capacity_per_km2 is None
        and metrics.poi_demand_density_per_km2 is None
    ):
        missing.add("parking")
    if metrics.noise_avg_db is None and metrics.night_activity_index is None:
        missing.add("environment")
    for result in tool_results or []:
        if result.status != "success":
            missing.add(result.dimension)
    return sorted(missing)


def _dimension_confidence(
    dimension: str,
    missing_fields: set[str],
    tool_result: DimensionToolResult | None,
) -> str:
    if dimension in missing_fields:
        return "low"
    if tool_result and tool_result.confidence in {"high", "medium", "low"}:
        return tool_result.confidence
    return "medium"


def _dimension_summary(
    dimension: str,
    score: float | None,
    missing_fields: set[str],
    tool_result: DimensionToolResult | None,
) -> str:
    if dimension in missing_fields:
        detail = tool_result.detail if tool_result and tool_result.detail else None
        if detail:
            return f"Structured source data is incomplete for this dimension: {detail}"
        return "This score uses default fallbacks because structured source data is incomplete."

    label = {
        "safety": "crime signal",
        "transit": "commute signal",
        "convenience": "nearby grocery and amenity signal",
        "parking": "mapped parking and demand-pressure signal",
        "environment": "noise and night-activity signal",
    }.get(dimension, "structured source data")
    if score is None:
        return "Not enough structured source data is available for this dimension yet."
    source = f" via {tool_result.source}" if tool_result else ""
    return f"Estimated from the project's standard {label} pipeline{source}."


def _overall_confidence(metrics) -> str:
    if metrics is None or metrics.overall_confidence is None:
        return "low"
    if metrics.overall_confidence >= 0.75:
        return "high"
    if metrics.overall_confidence >= 0.4:
        return "medium"
    return "low"


def _api_summary(name: str) -> str:
    return (
        f"{name} was added through the standard RentWise data pipeline. "
        "The dimension scores come from structured API and local-source metrics where available."
    )


async def _generate_web_discovery(
    settings: Settings,
    community_name: str,
    city: str | None,
    state: str | None,
    geocoded: dict | None,
) -> dict | None:
    if not settings.openai_api_key:
        return None

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_web_search_timeout_sec,
    )
    if not hasattr(client, "responses"):
        return None

    search_tool = {"type": "web_search"}
    user_location = _build_user_location(city, state)
    if user_location:
        search_tool["user_location"] = user_location

    user_prompt = json.dumps(
        {
            "community": {
                "name": community_name,
                "city": city,
                "state": state,
                "geocoded": geocoded or {},
            },
            "dimensions": _DIMENSIONS,
            "task": "Discover a provisional renter-focused profile and estimate the five dimensions.",
        },
        ensure_ascii=True,
    )

    try:
        response = await client.responses.create(
            model=settings.openai_web_search_model,
            input=[
                {"role": "system", "content": _DISCOVERY_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            tools=[search_tool],
            tool_choice="auto",
            include=["web_search_call.action.sources"],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "community_discovery",
                    "strict": True,
                    "schema": _DISCOVERY_SCHEMA,
                }
            },
            max_output_tokens=900,
        )
        data = json.loads(_extract_response_text(response))
    except Exception:
        return None

    sources = _extract_web_sources(response)
    if not sources:
        return None

    profile_data = data.get("profile") or {}
    dimensions_data = data.get("dimensions") or {}
    dimensions = [
        _build_dimension_estimate(dimension, dimensions_data.get(dimension) or {})
        for dimension in _DIMENSIONS
    ]
    missing_fields = _clean_string_list(data.get("missing_fields"))
    missing_fields.extend(
        dimension.dimension
        for dimension in dimensions
        if dimension.score_0_100 is None and dimension.dimension not in missing_fields
    )

    return {
        "profile": DiscoveredCommunityProfile(
            name=_clean_text(profile_data.get("name")) or community_name.strip(),
            city=_clean_text(profile_data.get("city")),
            state=_clean_text(profile_data.get("state")),
        ),
        "summary": _clean_text(data.get("summary"))
        or "A provisional community profile was created from public web signals.",
        "dimensions": dimensions,
        "overall_confidence": _clean_confidence(data.get("overall_confidence")),
        "missing_fields": missing_fields,
        "sources": sources,
    }


def _fallback_discovery_response(
    query: str,
    normalized_query: str,
    profile: DiscoveredCommunityProfile,
    source: str,
) -> CommunityDiscoveryResponse:
    missing_fields = _DIMENSIONS if source == "fallback" else [*_DIMENSIONS, "web_sources"]
    return CommunityDiscoveryResponse(
        status="partial",
        query=query,
        normalized_query=normalized_query,
        source=source,
        profile=profile,
        summary=(
            "A provisional profile was created from geocoding only; dimension estimates "
            "need web discovery or richer source data."
            if source == "geocoding"
            else "Not enough source data was available to create a full community profile."
        ),
        dimensions=[
            DimensionEstimate(
                dimension=dimension,
                score_0_100=None,
                summary="Not enough verified evidence is available for this dimension yet.",
                confidence="low",
            )
            for dimension in _DIMENSIONS
        ],
        overall_confidence="low",
        missing_fields=missing_fields,
        sources=[],
    )


def _build_profile(
    community_name: str,
    city: str | None,
    state: str | None,
    geocoded: dict | None,
) -> DiscoveredCommunityProfile:
    if geocoded:
        return DiscoveredCommunityProfile(
            name=str(geocoded.get("name") or community_name.strip()),
            city=_clean_text(geocoded.get("city")) or city,
            state=_clean_text(geocoded.get("state")) or state,
            display_name=_clean_text(geocoded.get("display_name")),
            center_lat=_as_float(geocoded.get("lat")),
            center_lng=_as_float(geocoded.get("lng")),
        )

    return DiscoveredCommunityProfile(
        name=community_name.strip(),
        city=city,
        state=state,
    )


def _build_dimension_estimate(dimension: str, payload: dict) -> DimensionEstimate:
    return DimensionEstimate(
        dimension=dimension,
        score_0_100=_clean_score(payload.get("score_0_100")),
        summary=_clean_text(payload.get("summary"))
        or "Not enough evidence is available for this dimension yet.",
        confidence=_clean_confidence(payload.get("confidence")),
    )


def _normalize_query(value: str) -> str:
    return " ".join(value.strip().split())


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    return text or None


def _clean_string_list(value, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = _clean_text(item)
        if text and text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _clean_score(value) -> float | None:
    try:
        if value is None:
            return None
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return None


def _clean_confidence(value) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"high", "medium", "low"} else "low"


def _as_float(value) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_user_location(city: str | None, state: str | None) -> dict | None:
    if not city and not state:
        return None

    payload = {"type": "approximate", "country": "US"}
    if city:
        payload["city"] = city
    if state:
        payload["region"] = state
    return payload


def _extract_response_text(response) -> str:
    output_text = _obj_get(response, "output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    chunks: list[str] = []
    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "message":
            continue
        for content_item in _obj_get(output_item, "content", []) or []:
            text = _obj_get(content_item, "text")
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
    return "\n".join(chunks).strip()


def _extract_web_sources(response, limit: int = 6) -> list[CommunityWebSource]:
    titles_by_url = _extract_citation_titles(response)
    seen: set[str] = set()
    sources: list[CommunityWebSource] = []

    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "web_search_call":
            continue
        action = _obj_get(output_item, "action", {})
        for source in _obj_get(action, "sources", []) or []:
            url = _obj_get(source, "url")
            if not isinstance(url, str) or not url or url in seen:
                continue
            seen.add(url)
            sources.append(
                CommunityWebSource(
                    url=url,
                    domain=_extract_domain(url),
                    title=titles_by_url.get(url),
                )
            )
            if len(sources) >= limit:
                return sources
    return sources


def _extract_citation_titles(response) -> dict[str, str]:
    titles: dict[str, str] = {}

    for output_item in _obj_get(response, "output", []) or []:
        if _obj_get(output_item, "type") != "message":
            continue
        for content_item in _obj_get(output_item, "content", []) or []:
            for annotation in _obj_get(content_item, "annotations", []) or []:
                ann_type = _obj_get(annotation, "type")
                if ann_type == "url_citation":
                    url = _obj_get(annotation, "url")
                    title = _obj_get(annotation, "title")
                else:
                    citation = _obj_get(annotation, "url_citation", {})
                    url = _obj_get(citation, "url")
                    title = _obj_get(citation, "title")
                if isinstance(url, str) and url and isinstance(title, str) and title.strip():
                    titles[url] = title.strip()

    return titles


def _extract_domain(url: str) -> str | None:
    netloc = urlparse(url).netloc.strip().lower()
    return netloc or None


def _obj_get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
