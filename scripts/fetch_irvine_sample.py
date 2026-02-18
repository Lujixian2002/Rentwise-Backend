from sqlalchemy import select

from app.db.database import Base, SessionLocal, engine
from app.db.models import Community, CommunityMetrics, DimensionScore
from app.services.ingest_service import ensure_metrics_fresh
from scripts.seed_communities import SEED_ROWS


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        _seed_communities(db)
        db.commit()

        for row in SEED_ROWS:
            ensure_metrics_fresh(db, row["community_id"], ttl_hours=0)

        _print_summary(db)
    finally:
        db.close()


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
