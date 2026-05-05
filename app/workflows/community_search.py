from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.agent import AgentTraceStep, CommunitySearchResponse
from app.workflows.community_discovery import run_community_discovery_workflow
from app.workflows.community_intake import run_community_intake_workflow


async def run_community_search_workflow(
    db: Session,
    community_name: str,
    settings: Settings,
    city: str | None = None,
    state: str | None = None,
) -> CommunitySearchResponse:
    intake = run_community_intake_workflow(db=db, community_name=community_name)
    trace = [
        AgentTraceStep(
            step="database_lookup",
            status="success" if intake.status == "found" else "partial",
            message=(
                "Community was found in the local database."
                if intake.status == "found"
                else "Community was not found in the local database; discovery is needed."
            ),
            detail={
                "query": intake.normalized_query,
                "matched_community_id": intake.matched_community_id,
            },
        )
    ]

    if intake.status == "found":
        return CommunitySearchResponse(
            status="found",
            source="database",
            next_step="use_existing_data",
            query=community_name,
            matched_community_id=intake.matched_community_id,
            intake=intake,
            discovery=None,
            community=intake.community,
            agent_trace=trace,
        )

    discovery = await run_community_discovery_workflow(
        db=db,
        community_name=community_name,
        city=city,
        state=state,
        settings=settings,
    )
    trace.extend(discovery.agent_trace)
    return CommunitySearchResponse(
        status=discovery.status,
        source="discovery",
        next_step="review_discovery_result",
        query=community_name,
        matched_community_id=discovery.matched_community_id,
        intake=intake,
        discovery=discovery,
        community=None,
        agent_trace=trace,
    )
