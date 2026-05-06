import json
import re
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session, load_only

from app.db.models import (
    Community,
    CommunityComparison,
    CommunityMetrics,
    DimensionScore,
    ReviewPost,
)


def get_community(db: Session, community_id: str) -> Community | None:
    stmt = select(Community).where(Community.community_id == community_id)
    return db.execute(stmt).scalar_one_or_none()


def list_communities_with_metrics(
    db: Session,
) -> list[tuple[Community, CommunityMetrics | None]]:
    stmt = (
        select(Community, CommunityMetrics)
        .outerjoin(
            CommunityMetrics, CommunityMetrics.community_id == Community.community_id
        )
        .options(
            load_only(
                Community.community_id,
                Community.name,
                Community.city,
                Community.state,
                Community.center_lat,
                Community.center_lng,
                Community.updated_at,
            ),
            load_only(
                CommunityMetrics.community_id,
                CommunityMetrics.median_rent,
                CommunityMetrics.rent_2b2b,
                CommunityMetrics.rent_1b1b,
                CommunityMetrics.avg_sqft,
                CommunityMetrics.grocery_density_per_km2,
                CommunityMetrics.crime_rate_per_100k,
                CommunityMetrics.rent_trend_12m_pct,
                CommunityMetrics.night_activity_index,
                CommunityMetrics.noise_avg_db,
                CommunityMetrics.noise_p90_db,
                CommunityMetrics.commute_minutes,
                CommunityMetrics.parking_lot_density_per_km2,
                CommunityMetrics.parking_capacity_per_km2,
                CommunityMetrics.poi_demand_density_per_km2,
                CommunityMetrics.overall_confidence,
                CommunityMetrics.details_json,
                CommunityMetrics.updated_at,
            ),
        )
        .order_by(Community.name.asc())
    )
    return list(db.execute(stmt).all())


def get_community_by_name(db: Session, name: str) -> Community | None:
    normalized = name.strip()
    if not normalized:
        return None

    # Try exact match first.
    exact_stmt = select(Community).where(Community.name.ilike(normalized))
    exact = db.execute(exact_stmt).scalar_one_or_none()
    if exact:
        return exact

    # Fallback to fuzzy match for mild user input variation.
    fuzzy_stmt = select(Community).where(Community.name.ilike(f"%{normalized}%"))
    return db.execute(fuzzy_stmt).scalars().first()


def get_metrics(db: Session, community_id: str) -> CommunityMetrics | None:
    stmt = select(CommunityMetrics).where(CommunityMetrics.community_id == community_id)
    return db.execute(stmt).scalar_one_or_none()


def create_community(
    db: Session,
    name: str,
    city: str | None = None,
    state: str | None = None,
    center_lat: float | None = None,
    center_lng: float | None = None,
    boundary_geojson: str | None = None,
) -> Community:
    base_id = (
        _to_slug("-".join([p for p in [name, city, state] if p]).strip())
        or uuid4().hex[:12]
    )
    community_id = base_id
    suffix = 2
    while get_community(db, community_id) is not None:
        community_id = f"{base_id}-{suffix}"
        suffix += 1

    row = Community(
        community_id=community_id,
        name=name,
        city=city,
        state=state,
        center_lat=center_lat,
        center_lng=center_lng,
        boundary_geojson=boundary_geojson,
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
        row = DimensionScore(
            score_id=uuid4().hex, community_id=community_id, dimension=dimension
        )
        db.add(row)

    row.score_0_100 = score_0_100
    row.summary = summary
    row.details_json = json.dumps(details, ensure_ascii=True)
    row.data_origin = data_origin
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return row


def get_dimension_scores(db: Session, community_id: str) -> list[DimensionScore]:
    stmt = (
        select(DimensionScore)
        .where(DimensionScore.community_id == community_id)
        .order_by(DimensionScore.dimension.asc())
    )
    return list(db.execute(stmt).scalars().all())


def get_reviews_by_community(
    db: Session, community_id: str, limit: int = 50
) -> list[ReviewPost]:
    ensure_review_filter_cache_columns(db)
    stmt = (
        select(ReviewPost)
        .where(ReviewPost.community_id == community_id)
        .order_by(ReviewPost.posted_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


def ensure_review_filter_cache_columns(db: Session) -> None:
    statements = (
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_keep boolean",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_category varchar(32)",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_reason text",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_model varchar(64)",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_prompt_version varchar(32)",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_text_hash varchar(64)",
        "ALTER TABLE review_post ADD COLUMN IF NOT EXISTS ai_filter_checked_at timestamp",
        (
            "CREATE INDEX IF NOT EXISTS ix_review_post_ai_filter_hash "
            "ON review_post(ai_filter_text_hash, ai_filter_model, ai_filter_prompt_version)"
        ),
    )
    for statement in statements:
        db.execute(text(statement))
    db.commit()


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
    stmt = select(CommunityComparison).where(
        CommunityComparison.community_a_id == community_a_id,
        CommunityComparison.community_b_id == community_b_id,
    )
    row = db.execute(stmt).scalar_one_or_none()

    if row is None:
        row = CommunityComparison(
            comparison_id=uuid4().hex,
            community_a_id=community_a_id,
            community_b_id=community_b_id,
            created_at=now,
        )
        db.add(row)

    row.updated_at = now
    row.request_params_json = json.dumps(request_params, ensure_ascii=True)
    row.weights_used_json = json.dumps(weights_used, ensure_ascii=True)
    row.structured_diff_json = json.dumps(structured_diff, ensure_ascii=True)
    row.short_summary = short_summary
    row.tradeoffs_json = json.dumps(tradeoffs, ensure_ascii=True)
    row.status = status
    row.missing_fields_json = json.dumps(missing_fields or [], ensure_ascii=True)
    row.data_origin = data_origin

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
    ensure_review_filter_cache_columns(db)

    stmt = select(ReviewPost).where(
        ReviewPost.community_id == community_id,
        ReviewPost.platform == platform,
        ReviewPost.external_id.in_(incoming_ids),
    )
    existing_posts = {
        post.external_id: post for post in db.execute(stmt).scalars().all()
    }
    existing_ids = set(existing_posts)

    new_posts = []
    for r in reviews:
        existing_post = existing_posts.get(r["id"])
        if existing_post is not None:
            if not existing_post.url and r.get("url"):
                existing_post.url = r.get("url")
            if not existing_post.author_name and r.get("author_name"):
                existing_post.author_name = r.get("author_name")
            if existing_post.like_count is None and r.get("like_count") is not None:
                existing_post.like_count = r.get("like_count")
            if not existing_post.parent_id and r.get("parent_id"):
                existing_post.parent_id = r.get("parent_id")
        elif r["id"] not in existing_ids:
            # Parse datetime if available, else now
            posted_at = datetime.utcnow()
            if r.get("published_at"):
                try:
                    # YouTube returns ISO 8601 (e.g. 2023-01-01T12:00:00Z)
                    posted_at = datetime.fromisoformat(
                        r["published_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            post = ReviewPost(
                post_id=str(uuid4()),
                community_id=community_id,
                platform=platform,
                external_id=r["id"],
                url=r.get("url"),
                body_text=r["text"],
                posted_at=posted_at,
                author_name=r.get("author_name"),
                like_count=r.get("like_count"),
                parent_id=r.get("parent_id"),
            )
            new_posts.append(post)

    if new_posts:
        db.add_all(new_posts)
    db.commit()
    return len(new_posts)


def _to_slug(raw: str) -> str:
    value = raw.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value.strip("-")
