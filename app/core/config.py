from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./rentwise.db"
    app_env: str = "dev"
    metrics_ttl_hours: int = 24

    # Routing / commute APIs
    google_maps_api_key: str | None = None
    openrouteservice_api_key: str | None = None
    commute_destination_lat: float = 33.6405  # UCI default
    commute_destination_lng: float = -117.8443
    prefer_google_commute: bool = True

    # Open data / external providers
    socrata_app_token: str | None = None
    crime_enable_fallback: bool = False
    crime_fallback_per_100k: float = 280.0
    yelp_api_key: str | None = None
    youtube_api_key: str | None = None
    nasa_earthdata_token: str | None = None
    viirs_days_back: int = 30
    viirs_bbox_radius_km: float = 10.0
    viirs_local_radiance_tif: str = "data/viirs_nightlights_2025-12_tile_00N060W/avg_radiance.tif"
    viirs_sample_radius_km: float = 2.0
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache

def get_settings() -> Settings:
    return Settings()
