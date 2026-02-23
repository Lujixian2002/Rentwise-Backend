from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Community(Base):
    __tablename__ = "community"

    community_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(128))
    state: Mapped[str | None] = mapped_column(String(64))
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lng: Mapped[float | None] = mapped_column(Float)
    boundary_geojson: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class CommunityMetrics(Base):
    __tablename__ = "community_metrics"

    community_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    median_rent: Mapped[float | None] = mapped_column(Float)
    rent_2b2b: Mapped[float | None] = mapped_column(Float)
    rent_1b1b: Mapped[float | None] = mapped_column(Float)
    avg_sqft: Mapped[float | None] = mapped_column(Float)

    grocery_density_per_km2: Mapped[float | None] = mapped_column(Float)
    crime_rate_per_100k: Mapped[float | None] = mapped_column(Float)
    rent_trend_12m_pct: Mapped[float | None] = mapped_column(Float)
    night_activity_index: Mapped[float | None] = mapped_column(Float)
    noise_avg_db: Mapped[float | None] = mapped_column(Float)
    noise_p90_db: Mapped[float | None] = mapped_column(Float)

    youtube_video_id: Mapped[str | None] = mapped_column(String(255))
    overall_confidence: Mapped[float | None] = mapped_column(Float)
    details_json: Mapped[str | None] = mapped_column(Text)


class DimensionScore(Base):
    __tablename__ = "dimension_score"

    score_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    community_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    dimension: Mapped[str | None] = mapped_column(String(32))
    score_0_100: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text)
    details_json: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)


class CommunityComparison(Base):
    __tablename__ = "community_comparison"

    comparison_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    community_a_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    community_b_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    request_params_json: Mapped[str | None] = mapped_column(Text)
    weights_used_json: Mapped[str | None] = mapped_column(Text)

    structured_diff_json: Mapped[str | None] = mapped_column(Text)
    short_summary: Mapped[str | None] = mapped_column(Text)
    tradeoffs_json: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str | None] = mapped_column(String(16))
    missing_fields_json: Mapped[str | None] = mapped_column(Text)
    data_origin: Mapped[str | None] = mapped_column(String(16))


class ReviewPost(Base):
    __tablename__ = "review_post"

    post_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    community_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)  # 'youtube'
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)  # video_id
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
