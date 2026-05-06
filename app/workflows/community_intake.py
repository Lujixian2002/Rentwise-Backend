from __future__ import annotations

from sqlalchemy.orm import Session

from app.db import crud
from app.schemas.agent import CommunityIntakeResponse
from app.schemas.community import CommunityResponse


def run_community_intake_workflow(
    db: Session,
    community_name: str,
) -> CommunityIntakeResponse:
    normalized_query = _normalize_query(community_name)
    community = crud.get_community_by_name(db, normalized_query)

    if community is None:
        return CommunityIntakeResponse(
            status="not_found",
            query=community_name,
            normalized_query=normalized_query,
            matched_community_id=None,
            community=None,
            next_step="needs_disco",
        )

    return CommunityIntakeResponse(
        status="found",
        query=community_name,
        normalized_query=normalized_query,
        matched_community_id=community.community_id,
        community=CommunityResponse(
            community_id=community.community_id,
            name=community.name,
            city=community.city,
            state=community.state,
            center_lat=community.center_lat,
            center_lng=community.center_lng,
            updated_at=community.updated_at,
        ),
        next_step="use_existing_data",
    )


def _normalize_query(value: str) -> str:
    return " ".join(value.strip().split())
