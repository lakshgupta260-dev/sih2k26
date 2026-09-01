"""Configuration contract tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.constants import UserRole


def test_database_uri_is_assembled_from_parts() -> None:
    settings = Settings(
        SECRET_KEY="x" * 40,
        POSTGRES_USER="u",
        POSTGRES_PASSWORD="p",
        POSTGRES_HOST="h",
        POSTGRES_PORT=5433,
        POSTGRES_DB="d",
        DATABASE_URL=None,
    )
    uri = settings.sqlalchemy_database_uri
    assert uri.startswith("postgresql+psycopg://")
    assert "h:5433" in uri and uri.endswith("/d")


def test_explicit_database_url_overrides_parts() -> None:
    explicit = "postgresql+psycopg://a:b@c:5432/e"
    settings = Settings(SECRET_KEY="x" * 40, DATABASE_URL=explicit)
    assert settings.sqlalchemy_database_uri == explicit


def test_cors_origins_accept_comma_separated_string() -> None:
    settings = Settings(SECRET_KEY="x" * 40, CORS_ORIGINS="http://a.test,http://b.test")
    assert settings.CORS_ORIGINS == ["http://a.test", "http://b.test"]


def test_production_requires_explicit_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", SECRET_KEY="")


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", SECRET_KEY="tooshort")


def test_local_generates_ephemeral_secret_when_absent() -> None:
    settings = Settings(ENVIRONMENT="local", SECRET_KEY="")
    assert len(settings.SECRET_KEY) >= 32


def test_roles_are_exactly_the_three_specified() -> None:
    assert {r.value for r in UserRole} == {
        "ADMIN",
        "PROJECT_MANAGER",
        "SITE_SUPERVISOR",
    }


def test_max_upload_bytes_derives_from_megabytes() -> None:
    settings = Settings(SECRET_KEY="x" * 40, MAX_UPLOAD_SIZE_MB=7)
    assert settings.max_upload_bytes == 7 * 1024 * 1024
