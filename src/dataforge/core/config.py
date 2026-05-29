"""Application settings.

All configuration is environment-driven (12-factor) and validated through
Pydantic so misconfiguration fails fast at startup rather than at runtime.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Typed application settings, sourced from environment / .env."""

    model_config = SettingsConfigDict(
        env_prefix="DATAFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- General ---------------------------------------------------------
    environment: Environment = Environment.LOCAL
    service_name: str = "dataforge"
    debug: bool = False
    log_level: str = "INFO"
    # JSON logs in deployed envs; pretty console logs locally.
    log_json: bool = True

    # --- HTTP ------------------------------------------------------------
    host: str = "0.0.0.0"  # noqa: S104  # nosec B104 - binds inside container network only
    port: int = 8000

    # --- Backing services (used as modules are implemented) --------------
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge",
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"

    # --- Observability ---------------------------------------------------
    otel_exporter_otlp_endpoint: str | None = None
    metrics_enabled: bool = True
    tracing_enabled: bool = True

    @property
    def is_local(self) -> bool:
        return self.environment == Environment.LOCAL


@lru_cache
def get_settings() -> Settings:
    """Return cached settings. Cached so we parse the environment once."""
    return Settings()
