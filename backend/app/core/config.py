"""Application configuration.

All environment-specific values are loaded from the environment (or a local
``.env`` file). Nothing in this module may contain a real secret, hostname or
credential -- see ``.env.example`` for the contract.
"""
from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    PostgresDsn,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------------------------------------------------------------- general
    PROJECT_NAME: str = "SIH26122 Progress Intelligence Platform"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Environment = "local"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = False

    # ---------------------------------------------------------------- security
    # Never ship a default in a real deployment; validated below.
    SECRET_KEY: str = Field(default="", min_length=0)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    BCRYPT_ROUNDS: int = 12

    # ---------------------------------------------------------------- database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "sih26122"
    # Explicit override wins over the assembled parts (used by CI / Docker).
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True
    DB_ECHO: bool = False

    # ---------------------------------------------------------------- redis
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # ---------------------------------------------------------------- cors
    # NoDecode: pydantic-settings JSON-decodes complex types inside the env
    # source, before field validators run. Opting out lets _split_csv accept
    # the comma-separated form that is natural in a .env file.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ---------------------------------------------------------------- storage
    UPLOAD_DIR: str = "uploads"
    GENERATED_REPORTS_DIR: str = "generated_reports"
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_UPLOAD_EXTENSIONS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            ".pdf", ".xlsx", ".xls", ".csv", ".txt",
            ".png", ".jpg", ".jpeg", ".xer", ".xml",
        ]
    )

    # ------------------------------------------------- pluggable providers
    # Provider names are read from configuration so an implementation can be
    # swapped without touching any call site.
    #   LLM_PROVIDER       : "none" | "anthropic" | "openai"
    #   EMBEDDING_PROVIDER : "tfidf" | "sentence_transformer"
    #   OCR_PROVIDER       : "noop"
    LLM_PROVIDER: str = "none"
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_MAX_LINES_PER_CALL: int = 40

    EMBEDDING_PROVIDER: str = "tfidf"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    OCR_PROVIDER: str = "noop"

    # ------------------------------------------------- matching thresholds
    # A candidate scoring at or above AUTO is linked automatically; at or above
    # REVIEW it is queued for a human; below that it is recorded as unmatched.
    # Deliberately configurable: the right cut-off depends on how much manual
    # review a project is willing to absorb.
    MATCH_AUTO_THRESHOLD: float = Field(default=0.82, ge=0.0, le=1.0)
    MATCH_REVIEW_THRESHOLD: float = Field(default=0.55, ge=0.0, le=1.0)
    # How many candidates to keep per extracted line for review and audit.
    MATCH_MAX_CANDIDATES: int = Field(default=5, ge=1, le=50)
    # Candidate generation cap before scoring, to bound cost on big schedules.
    MATCH_BLOCKING_LIMIT: int = Field(default=400, ge=10, le=10000)

    # Signal weights. Normalised at use, so these are relative, not absolute.
    MATCH_WEIGHT_EXACT_CODE: float = 1.00
    MATCH_WEIGHT_KEYWORD: float = 0.55
    MATCH_WEIGHT_FUZZY: float = 0.80
    MATCH_WEIGHT_EMBEDDING: float = 0.70
    MATCH_WEIGHT_DISCIPLINE: float = 0.35
    MATCH_WEIGHT_LOCATION: float = 0.60
    MATCH_WEIGHT_HIERARCHY: float = 0.25

    @field_validator("CORS_ORIGINS", "ALLOWED_UPLOAD_EXTENSIONS", mode="before")
    @classmethod
    def _split_csv(cls, v: Any) -> Any:
        """Allow comma-separated strings in .env as well as JSON lists."""
        if isinstance(v, str) and not v.startswith("["):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def _validate_secret(self) -> "Settings":
        if not self.SECRET_KEY:
            if self.ENVIRONMENT in ("production", "staging"):
                raise ValueError(
                    "SECRET_KEY must be set explicitly outside local development."
                )
            # Ephemeral key so local dev works out of the box. Tokens issued by
            # one process will not validate in another -- that is intentional.
            object.__setattr__(self, "SECRET_KEY", secrets.token_urlsafe(48))
        elif len(self.SECRET_KEY) < 32 and self.ENVIRONMENT in ("production", "staging"):
            raise ValueError("SECRET_KEY must be at least 32 characters.")
        return self

    @model_validator(mode="after")
    def _validate_thresholds(self) -> "Settings":
        if self.MATCH_REVIEW_THRESHOLD > self.MATCH_AUTO_THRESHOLD:
            raise ValueError(
                "MATCH_REVIEW_THRESHOLD cannot exceed MATCH_AUTO_THRESHOLD; "
                "nothing would ever be queued for review."
            )
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sqlalchemy_database_uri(self) -> str:
        """Full SQLAlchemy URL, from DATABASE_URL or the POSTGRES_* parts."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return str(
            PostgresDsn.build(
                scheme="postgresql+psycopg",
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                path=self.POSTGRES_DB,
            )
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_broker(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def celery_backend(self) -> str:
        return self.CELERY_RESULT_BACKEND or self.REDIS_URL

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor -- the single entry point for configuration."""
    return Settings()


settings = get_settings()
