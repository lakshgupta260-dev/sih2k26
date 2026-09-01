"""Shared pytest fixtures."""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Settings are read at import time, so the test environment must be set before
# the application package is imported anywhere.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-any-real-deployment")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_application  # noqa: E402


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_application()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
