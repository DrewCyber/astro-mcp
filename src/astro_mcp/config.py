"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All configurable parameters for astro-mcp."""

    ephe_path: str = Field(default="./ephe", alias="EPHE_PATH")
    geocoding_provider: str = Field(default="nominatim", alias="GEOCODING_PROVIDER")
    opencage_api_key: str = Field(default="", alias="OPENCAGE_API_KEY")
    geocoding_user_agent: str = Field(default="astro-mcp/1.0", alias="GEOCODING_USER_AGENT")
    geocode_cache_size: int = Field(default=512, alias="GEOCODE_CACHE_SIZE")
    default_house_system: str = Field(default="P", alias="DEFAULT_HOUSE_SYSTEM")
    default_orb_factor: float = Field(default=1.0, alias="DEFAULT_ORB_FACTOR")
    log_level: str = Field(default="WARNING", alias="LOG_LEVEL")

    model_config = {"populate_by_name": True, "env_file": ".env", "extra": "ignore"}


# Singleton instance
settings = Settings()
