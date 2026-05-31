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


class LLMProvider(StrEnum):
    """Which LLM backend the platform uses for RCA, fix generation, RAG synth.

    `null` is the safe default: it returns deterministic stub completions so
    the rest of the platform runs without an API key (useful in CI and for
    new contributors).
    """

    NULL = "null"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class EmbedderKind(StrEnum):
    """Which embedder RAG uses to vectorize failure profiles.

    `hashing` is deterministic, zero-dep, no model download — the default so
    CI and fresh installs stay fast. `semantic` switches to a real
    sentence-embedding model (bge-small-en-v1.5 by default) via fastembed.
    """

    HASHING = "hashing"
    SEMANTIC = "semantic"


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

    # --- LLM -------------------------------------------------------------
    # Provider + model selection. Provider-specific credentials are read only
    # when that provider is selected, so the foundation runs key-less.
    llm_provider: LLMProvider = LLMProvider.NULL
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    # Per-request and reliability knobs.
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=3, ge=0)
    llm_max_output_tokens: int = Field(default=4096, gt=0)
    # Circuit breaker: open after N consecutive failures, half-open after cooldown.
    llm_circuit_failure_threshold: int = Field(default=5, ge=1)
    llm_circuit_cooldown_seconds: float = Field(default=30.0, gt=0)
    # Soft per-process daily token budget. Hitting it raises before the call,
    # so a runaway loop can't burn the API bill in unattended workflows.
    llm_daily_token_budget: int = Field(default=1_000_000, ge=0)

    # --- RAG embedder ----------------------------------------------------
    # Hashing by default (zero-dep, deterministic). `semantic` uses fastembed.
    rag_embedder: EmbedderKind = EmbedderKind.HASHING
    rag_embedder_model: str = "BAAI/bge-small-en-v1.5"
    # Where the model file gets cached. None lets fastembed pick its default
    # (~/.cache/fastembed). Set this in containerized envs to point at a
    # mounted volume so the model isn't re-downloaded every container start.
    rag_embedder_cache_dir: str | None = None

    # --- ML anomaly detectors --------------------------------------------
    # Master switch: when off, the platform runs the deterministic detectors
    # only (the zero-dep default). When on, the observability service also
    # fetches recent run history and runs the configured ML detectors.
    ml_detectors_enabled: bool = False
    ml_detector_isolation_forest: bool = True
    ml_detector_timeseries: bool = True
    ml_detector_log_template: bool = True
    # How many recent runs the service fetches as ML context.
    ml_detector_history_limit: int = Field(default=100, ge=10)

    # --- GitHub remediation pipeline -------------------------------------
    # Token is read here but only used by the pipeline when it actually
    # opens a PR or pushes a branch. Dry-run mode bypasses both.
    github_token: str | None = None
    github_api_url: str = "https://api.github.com"
    git_user_name: str = "DataForge Bot"
    git_user_email: str = "bot@dataforge.ai"

    @property
    def is_local(self) -> bool:
        return self.environment == Environment.LOCAL


@lru_cache
def get_settings() -> Settings:
    """Return cached settings. Cached so we parse the environment once."""
    return Settings()
