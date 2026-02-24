import argparse

from sqlalchemy import select

from app.db.database import Base, SessionLocal, engine
from app.db.models import Community, CommunityMetrics, DimensionScore
from app.services.ingest_service import ensure_metrics_fresh_with_options
from scripts.seed_communities import SEED_ROWS


def main() -> None:
    args = _parse_args()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_communities(db)
        db.commit()

        selected_ids = [row["community_id"] for row in SEED_ROWS]
        if args.community_id:
            selected_ids = args.community_id

        ttl_hours = 0 if args.force_refresh else None
        for community_id in selected_ids:
            ensure_metrics_fresh_with_options(
                db,
                community_id,
                ttl_hours=ttl_hours,
                skip_external=args.skip_external,
            )

        _print_summary(db)
    finally:
        db.close()


def _parse_args():
    parser = argparse.ArgumentParser(description="Fetch and upsert Irvine sample community data.")
    parser.add_argument(
        "--community-id",
        action="append",
        help="Only ingest the given community_id (can be specified multiple times).",
    )
    parser.add_argument(
        "--skip-external",
        action="store_true",
        help="Skip external API fetchers (Overpass/Socrata/YouTube), keep local CSV ingest.",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Ignore TTL by forcing refresh (equivalent to ttl_hours=0).",
    )
    return parser.parse_args()


def _seed_communities(db) -> None:
    for row in SEED_ROWS:
        existing = db.get(Community, row["community_id"])
        if existing:
            continue
        db.add(Community(**row))


def _print_summary(db) -> None:
    metrics_rows = db.execute(select(CommunityMetrics)).scalars().all()
    print("Ingested community_metrics rows:", len(metrics_rows))
    for m in metrics_rows:
        print(
            f"- {m.community_id}: rent={m.median_rent}, grocery_density={m.grocery_density_per_km2}, "
            f"crime_rate={m.crime_rate_per_100k}, noise_avg={m.noise_avg_db}, confidence={m.overall_confidence}"
        )

    score_rows = db.execute(select(DimensionScore)).scalars().all()
    print("Ingested dimension_score rows:", len(score_rows))


if __name__ == "__main__":
    main()
