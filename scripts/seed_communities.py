from datetime import datetime

from app.db.database import Base, SessionLocal, engine
from app.db.models import Community

SEED_ROWS = [
    {
        "community_id": "irvine-spectrum",
        "name": "Irvine Spectrum",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6506,
        "center_lng": -117.7439,
    },
    {
        "community_id": "woodbridge",
        "name": "Woodbridge",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6770,
        "center_lng": -117.7989,
    },
    {
        "community_id": "university-town-center",
        "name": "University Town Center",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6492,
        "center_lng": -117.8427,
    },
    {
        "community_id": "turtle-rock",
        "name": "Turtle Rock",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6381,
        "center_lng": -117.8107,
    },
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for row in SEED_ROWS:
            existing = db.get(Community, row["community_id"])
            if existing:
                continue
            db.add(Community(**row, updated_at=datetime.utcnow()))
        db.commit()
        print("Seed completed")
    finally:
        db.close()


if __name__ == "__main__":
    main()
