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
    {
        "community_id": "northwood",
        "name": "Northwood",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.7081,
        "center_lng": -117.7739,
    },
    {
        "community_id": "costa-mesa-border",
        "name": "Costa Mesa Border",
        "city": "Costa Mesa",  # Providing closest city helps the search logic
        "state": "CA",
        "center_lat": 33.6412,
        "center_lng": -117.9184,
    },
    {
        "community_id": "portola-springs",
        "name": "Portola Springs",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6974,
        "center_lng": -117.7156,
    },
    {
        "community_id": "great-park",
        "name": "Great Park",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6673,
        "center_lng": -117.7243,
    },
    {
        "community_id": "quail-hill",
        "name": "Quail Hill",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6495,
        "center_lng": -117.7750,
    },
    {
        "community_id": "oak-creek",
        "name": "Oak Creek",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6719,
        "center_lng": -117.7754,
    },
    {
        "community_id": "woodbury",
        "name": "Woodbury",
        "city": "Irvine",
        "state": "CA",
        "center_lat": 33.6973,
        "center_lng": -117.7505,
    },
]


def main() -> None:
    # Drop all tables to ensure schema matches current models
    Base.metadata.drop_all(bind=engine)
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
