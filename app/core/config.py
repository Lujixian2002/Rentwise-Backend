from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./rentwise.db"
    app_env: str = "dev"
    metrics_ttl_hours: int = 24

    # Routing / commute APIs
    google_maps_api_key: str | None = None
    openrouteservice_api_key: str | None = None

    # Open data / external providers
    socrata_app_token: str | None = None
    yelp_api_key: str | None = None
    youtube_api_key: str | None = None
    nasa_earthdata_token: str | None = None
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache

def get_settings() -> Settings:
    return Settings()
