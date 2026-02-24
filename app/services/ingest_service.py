import hashlib
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import crud
from app.services.fetchers.irvine_crime import fetch_crime_rate_per_100k_with_source
from app.services.fetchers.google_maps import (
    fetch_commute_minutes as fetch_google_commute_minutes,
)
from app.services.fetchers.nasa_viirs import fetch_viirs_night_activity_index
from app.services.fetchers.openrouteservice import (
    fetch_commute_minutes as fetch_ors_commute_minutes,
)
from app.services.fetchers.overpass_osm import (
    fetch_grocery_density,
    fetch_noise_proxy,
)
from app.services.fetchers.youtube import fetch_comments, search_videos
from app.services.fetchers.zillow_zori import read_zori_rows
from app.services.scoring_service import compute_dimension_scores
from app.utils.time import is_expired


def ensure_metrics_fresh(
    db: Session, community_id: str, ttl_hours: int | None = None
) -> None:
    ensure_metrics_fresh_with_options(
        db, community_id, ttl_hours=ttl_hours, skip_external=False
    )


def ensure_metrics_fresh_with_options(
    db: Session,
    community_id: str,
    ttl_hours: int | None = None,
    skip_external: bool = False,
) -> None:
    settings = get_settings()
    effective_ttl = ttl_hours if ttl_hours is not None else settings.metrics_ttl_hours
    existing = crud.get_metrics(db, community_id)
    if (
        existing
        and existing.updated_at
        and not is_expired(existing.updated_at, effective_ttl)
    ):
        return

    community = crud.get_community(db, community_id)
    if community is None:
        return

    # ZORI (local CSV for rent baseline)
    zori_rows = read_zori_rows()
    match = next(
        (row for row in zori_rows if row.get("community_id") == community_id), None
    )
    grocery_density = None
    night_activity_index = None
    night_activity_source = "none"
    noise_avg_db = None
    noise_p90_db = None
    commute_minutes = None
    if (
        not skip_external
        and community.center_lat is not None
        and community.center_lng is not None
    ):
        grocery_density = fetch_grocery_density(
            community.center_lat, community.center_lng, radius_km=1.2
        )
        # Night activity metric is sourced ONLY from local VIIRS raster files.
        night_activity_index = fetch_viirs_night_activity_index(
            community.center_lat, community.center_lng
        )
        if night_activity_index is not None:
            night_activity_source = "local_viirs"
        noise_avg_db, noise_p90_db = fetch_noise_proxy(
            community.center_lat, community.center_lng
        )
        commute_minutes = _fetch_commute_minutes_with_fallback(
            community.center_lat, community.center_lng
        )

    # Keep night metric stable: fallback to previous cached value, then 0.0.
    if (
        night_activity_index is None
        and existing
        and existing.night_activity_index is not None
    ):
        night_activity_index = existing.night_activity_index
        night_activity_source = "cached"
    if night_activity_index is None:
        night_activity_index = 0.0
        if night_activity_source == "none":
            night_activity_source = "default"

    crime_rate = None
    crime_source = "skipped" if skip_external else "missing"
    if not skip_external:
        crime_rate, crime_source = fetch_crime_rate_per_100k_with_source(
            community.city,
            center_lat=community.center_lat,
            center_lng=community.center_lng,
        )

    # YouTube fetching is enabled for testing when YOUTUBE_API_KEY is set.
    youtube_video_ids = []
    youtube_comments = []

    # Check if we already have video IDs saved (to avoid search API cost)
    if existing and existing.youtube_video_ids:
        try:
            youtube_video_ids = json.loads(existing.youtube_video_ids)
        except json.JSONDecodeError:
            youtube_video_ids = []

    # If no IDs found in DB, try multiple search strategies to find videos WITH comments
    if not youtube_video_ids:
        # Strategies to cover different aspects: reviews, lifestyle, vlogs
        search_templates = [
            f"{community.name} {community.city or 'Irvine'} apartments review",
            f"{community.name} {community.city or 'Irvine'} living",
            f"{community.name} {community.city or 'Irvine'} tour",
            f"Living in {community.name} {community.city or 'Irvine'}",
        ]

        # Use a set to avoid duplicate video IDs across different search queries
        found_ids_set = set()

        for query in search_templates:
            # Search for videos
            # We limit main results to 3 per query to avoid hitting quota limits too fast,
            # but since we run multiple queries, we'll get a good mix.
            ids = search_videos(query, max_results=3)
            if ids:
                found_ids_set.update(ids)

        # Convert back to list
        youtube_video_ids = list(found_ids_set)

    # Fetch comments for all unique videos found
    if youtube_video_ids:
        for vid in youtube_video_ids:
            # Limit per video to control quota/size
            comments = fetch_comments(vid, max_results=10)
            if comments:
                youtube_comments.extend(comments)

    payload: dict = {
        "updated_at": datetime.utcnow(),
        "grocery_density_per_km2": grocery_density,
        "crime_rate_per_100k": crime_rate,
        # Save list of IDs and aggregated comments as JSON strings
        "youtube_video_ids": (
            json.dumps(youtube_video_ids) if youtube_video_ids else None
        ),
        "youtube_comments": json.dumps(youtube_comments) if youtube_comments else None,
        "night_activity_index": night_activity_index,
        "noise_avg_db": noise_avg_db,
        "noise_p90_db": noise_p90_db,
        "overall_confidence": 0.5,
        "details_json": "{}",
    }
    if match:
        payload.update(
            {
                "median_rent": _to_float(match.get("median_rent")),
                "rent_2b2b": _to_float(match.get("rent_2b2b")),
                "rent_1b1b": _to_float(match.get("rent_1b1b")),
                "avg_sqft": _to_float(match.get("avg_sqft")),
                "rent_trend_12m_pct": _to_float(match.get("rent_trend_12m_pct")),
                "overall_confidence": 0.7,
            }
        )
    required_keys = [
        "median_rent",
        "grocery_density_per_km2",
        "crime_rate_per_100k",
        "rent_trend_12m_pct",
        "night_activity_index",
        "noise_avg_db",
    ]
    available = sum(1 for key in required_keys if payload.get(key) is not None)
    payload["overall_confidence"] = round(available / len(required_keys), 2)

    payload["details_json"] = json.dumps(
        {
            "sources": {
                "zori_csv": bool(match),
                "overpass_grocery": grocery_density is not None,
                "overpass_night_activity": False,
                "overpass_noise": noise_avg_db is not None,
                "irvine_crime": crime_rate is not None,
                "irvine_crime_source": crime_source,
                "youtube_video": bool(youtube_video_ids),
                "commute_minutes": commute_minutes,
                "viirs_night_activity": night_activity_source == "local_viirs",
                "night_activity_source": night_activity_source,
            }
        },
        ensure_ascii=True,
    )

    metrics = crud.upsert_metrics(db, community_id, payload)
    score_input = {
        "median_rent": metrics.median_rent,
        "commute_minutes": commute_minutes,
        "grocery_density_per_km2": metrics.grocery_density_per_km2,
        "crime_rate_per_100k": metrics.crime_rate_per_100k,
        "rent_trend_12m_pct": metrics.rent_trend_12m_pct,
        "noise_avg_db": metrics.noise_avg_db,
        "night_activity_index": metrics.night_activity_index,
        "review_signal_score": None,
    }
    scores = compute_dimension_scores(score_input)
    for dimension, value in scores.items():
        crud.upsert_dimension_score(
            db=db,
            community_id=community_id,
            dimension=dimension,
            score_0_100=value,
            summary=f"{dimension} score auto-generated by ingest pipeline",
            details=score_input,
            data_origin="api",
        )


def ensure_reviews_fresh(db: Session, community_id: str) -> None:
    """
    Ensures that the ReviewPost table is populated from the aggregated
    comments stored in CommunityMetrics (fetched during ingestion).
    """
    # 1. Check if we already have structured posts
    existing_count = crud.get_reviews_count(db, community_id)
    if existing_count > 0:
        return

    # 2. Get metrics to find the raw cached comments
    metrics = crud.get_metrics(db, community_id)
    if not metrics or not metrics.youtube_comments:
        # If no metrics or no comments cached, we can't do much.
        # The main ingestion pipeline (ensure_metrics_fresh) is responsible for fetching.
        # We could trigger it here, but typically /communities/{id} is called before /reviews
        return

    # 3. Parse cached comments and insert into ReviewPost table
    try:
        raw_comments = json.loads(metrics.youtube_comments)
    except json.JSONDecodeError:
        return

    if not raw_comments:
        return

    # Convert simple string comments to the dict format expected by upsert_review_posts
    # Since we only stored strings, we'll generate IDs and dummy dates
    review_dicts = []
    for i, text in enumerate(raw_comments):
        # Create a deterministic ID based on content hash or index to avoid dupes?
        # For now, crud.upsert_review_posts uses external_id to dedup.
        # We don't have real external IDs or dates stored in the simple list[str].
        # We'll use a simple hash of the text as the ID.
        text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        review_dicts.append(
            {
                "id": f"yt-{text_hash}",
                "text": text,
                "published_at": None,  # We lost the date in the simple fetch, that's fine for now
            }
        )

    crud.upsert_review_posts(db, community_id, "youtube", review_dicts)


def _to_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _fetch_commute_minutes_with_fallback(
    origin_lat: float, origin_lng: float
) -> int | None:
    settings = get_settings()
    origin = (origin_lat, origin_lng)
    destination = (settings.commute_destination_lat, settings.commute_destination_lng)
    if settings.prefer_google_commute:
        minutes = fetch_google_commute_minutes(origin, destination)
        if minutes is not None:
            return minutes
        return fetch_ors_commute_minutes(origin, destination)

    minutes = fetch_ors_commute_minutes(origin, destination)
    if minutes is not None:
        return minutes
    return fetch_google_commute_minutes(origin, destination)
