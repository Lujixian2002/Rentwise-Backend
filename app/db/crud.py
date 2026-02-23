import json
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Community, CommunityComparison, CommunityMetrics, DimensionScore, ReviewPost


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


def get_reviews_by_community(
    db: Session, community_id: str, limit: int = 50
) -> list[ReviewPost]:
    stmt = (
        select(ReviewPost)
        .where(ReviewPost.community_id == community_id)
        .order_by(ReviewPost.posted_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def get_reviews_count(db: Session, community_id: str) -> int:
    stmt = select(ReviewPost.post_id).where(ReviewPost.community_id == community_id)
    return len(db.execute(stmt).scalars().all())


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


def upsert_review_posts(
    db: Session, community_id: str, platform: str, reviews: list[dict]
) -> int:
    """
    reviews: list of dicts with 'id', 'text', 'published_at'
    Returns count of new insertions.
    """
    incoming_ids = [r["id"] for r in reviews]
    if not incoming_ids:
        return 0

    stmt = select(ReviewPost.external_id).where(
        ReviewPost.community_id == community_id,
        ReviewPost.platform == platform,
        ReviewPost.external_id.in_(incoming_ids),
    )
    existing_ids = set(db.execute(stmt).scalars().all())

    new_posts = []
    for r in reviews:
        if r["id"] not in existing_ids:
            # Parse datetime if available, else now
            posted_at = datetime.utcnow()
            if r.get("published_at"):
                try:
                    # YouTube returns ISO 8601 (e.g. 2023-01-01T12:00:00Z)
                    posted_at = datetime.fromisoformat(r["published_at"].replace("Z", "+00:00"))
                except ValueError:
                    pass

            post = ReviewPost(
                post_id=str(uuid4()),
                community_id=community_id,
                platform=platform,
                external_id=r["id"],
                body_text=r["text"],
                posted_at=posted_at,
            )
            new_posts.append(post)

    if new_posts:
        db.add_all(new_posts)
        db.commit()
    return len(new_posts)
