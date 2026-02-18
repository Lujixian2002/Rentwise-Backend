import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Community, CommunityComparison, CommunityMetrics, DimensionScore


def get_community(db: Session, community_id: str) -> Community | None:
    stmt = select(Community).where(Community.community_id == community_id)
    return db.execute(stmt).scalar_one_or_none()


def get_metrics(db: Session, community_id: str) -> CommunityMetrics | None:
    stmt = select(CommunityMetrics).where(CommunityMetrics.community_id == community_id)
    return db.execute(stmt).scalar_one_or_none()


def upsert_metrics(db: Session, community_id: str, payload: dict) -> CommunityMetrics:
    metrics = get_metrics(db, community_id)
    if metrics is None:
        metrics = CommunityMetrics(community_id=community_id)
        db.add(metrics)

    for key, value in payload.items():
        if hasattr(metrics, key):
            setattr(metrics, key, value)
    metrics.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(metrics)
    return metrics


def upsert_dimension_score(
    db: Session,
    community_id: str,
    dimension: str,
    score_0_100: float,
    summary: str,
    details: dict,
    data_origin: str = "mixed",
) -> DimensionScore:
    stmt = select(DimensionScore).where(
        DimensionScore.community_id == community_id,
        DimensionScore.dimension == dimension,
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = DimensionScore(score_id=uuid4().hex, community_id=community_id, dimension=dimension)
        db.add(row)

    row.score_0_100 = score_0_100
    row.summary = summary
    row.details_json = json.dumps(details, ensure_ascii=True)
    row.data_origin = data_origin
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return row


def create_comparison(
    db: Session,
    community_a_id: str,
    community_b_id: str,
    request_params: dict,
    weights_used: dict,
    structured_diff: dict,
    short_summary: str,
    tradeoffs: dict,
    status: str = "ready",
    missing_fields: list[str] | None = None,
    data_origin: str = "mixed",
) -> CommunityComparison:
    now = datetime.utcnow()
    row = CommunityComparison(
        comparison_id=uuid4().hex,
        community_a_id=community_a_id,
        community_b_id=community_b_id,
        created_at=now,
        updated_at=now,
        request_params_json=json.dumps(request_params, ensure_ascii=True),
        weights_used_json=json.dumps(weights_used, ensure_ascii=True),
        structured_diff_json=json.dumps(structured_diff, ensure_ascii=True),
        short_summary=short_summary,
        tradeoffs_json=json.dumps(tradeoffs, ensure_ascii=True),
        status=status,
        missing_fields_json=json.dumps(missing_fields or [], ensure_ascii=True),
        data_origin=data_origin,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
