from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.comparison import CompareRequest, CompareResponse
from app.services.compare_service import compare_communities
from app.services.community_resolver import resolve_community
from app.services.ingest_service import ensure_metrics_fresh

router = APIRouter()


@router.post("", response_model=CompareResponse)
def compare(req: CompareRequest, db: Session = Depends(get_db)) -> CompareResponse:
    community_a = resolve_community(
        db, community_id=req.community_a_id, community_name=req.community_a_name
    )
    community_b = resolve_community(
        db, community_id=req.community_b_id, community_name=req.community_b_name
    )

    if community_a is None:
        raise HTTPException(status_code=404, detail="Community A not found by provided id/name")
    if community_b is None:
        raise HTTPException(status_code=404, detail="Community B not found by provided id/name")

    if community_a.community_id == community_b.community_id:
        raise HTTPException(status_code=400, detail="community_a_id and community_b_id must be different")

    ensure_metrics_fresh(db, community_a.community_id)
    ensure_metrics_fresh(db, community_b.community_id)

    row, structured_diff, tradeoffs = compare_communities(
        db=db,
        community_a_id=community_a.community_id,
        community_b_id=community_b.community_id,
        weights=req.weights,
    )

    return CompareResponse(
        comparison_id=row.comparison_id,
        community_a_id=row.community_a_id,
        community_b_id=row.community_b_id,
        created_at=row.created_at,
        status=row.status or "error",
        short_summary=row.short_summary or "",
        structured_diff=structured_diff,
        tradeoffs=tradeoffs,
    )
