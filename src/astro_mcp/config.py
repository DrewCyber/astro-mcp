"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All configurable parameters for astro-mcp."""

    ephe_path: str = Field(default="./ephe", alias="EPHE_PATH")
    geocoding_provider: str = Field(default="nominatim", alias="GEOCODING_PROVIDER")
    opencage_api_key: str = Field(default="", alias="OPENCAGE_API_KEY")
    geocoding_user_agent: str = Field(default="astro-mcp/1.0", alias="GEOCODING_USER_AGENT")
    geocode_cache_size: int = Field(default=512, alias="GEOCODE_CACHE_SIZE")
    default_house_system: Literal["P", "W", "K"] = Field(default="P", alias="DEFAULT_HOUSE_SYSTEM")
    default_orb_factor: float = Field(default=1.0, ge=0.1, le=3.0, alias="DEFAULT_ORB_FACTOR")
    node_type: Literal["true", "mean"] = Field(default="true", alias="NODE_TYPE")
    log_level: str = Field(default="WARNING", alias="LOG_LEVEL")

    model_config = {"populate_by_name": True, "env_file": ".env", "extra": "ignore"}

    @field_validator("ephe_path")
    @classmethod
    def _absolutise_ephe_path(cls, value: str) -> str:
        """Resolve the ephemeris path against the CWD *at startup*.

        MCP clients launch the server from an arbitrary working directory, so a
        relative default such as ``./ephe`` would otherwise resolve differently
        (and usually to nothing) depending on who spawned the process.  Pinning
        it once here means the rest of the codebase only ever sees an absolute
        path.
        """
        return str(Path(value).expanduser().resolve())

    @property
    def use_mean_node(self) -> bool:
        return self.node_type == "mean"


# Singleton instance
settings = Settings()
