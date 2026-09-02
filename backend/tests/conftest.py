"""Shared pytest fixtures.

Database strategy
-----------------
Tests run against a real PostgreSQL database (the models use PostgreSQL types
such as JSONB and UUID, so SQLite is not a usable stand-in). Each test runs
inside an outer transaction that is rolled back afterwards, with the session
joined via ``create_savepoint`` so that ``commit()`` calls inside services --
which are real and necessary -- become savepoint releases instead of durable
writes. Tests are therefore fully isolated and no cleanup code is needed.

If no database is reachable, database-backed tests skip with a clear reason
rather than failing, so ``pytest`` stays useful on a machine without Postgres.
"""
from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest

# Settings are read at import time; the environment must be set first.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-any-real-deployment")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Engine, make_url  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.constants import UserRole  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_application  # noqa: E402
from app.models.user import User  # noqa: E402

TEST_DB_SUFFIX = "_test"


def _test_database_url() -> str:
    """A dedicated test database, so a stray run can never touch dev data."""
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    url = make_url(settings.sqlalchemy_database_uri)
    return url.set(database=f"{url.database}{TEST_DB_SUFFIX}").render_as_string(hide_password=False)


def _ensure_database(url: str) -> None:
    """Create the test database if it does not exist."""
    target = make_url(url)
    admin_url = target.set(database="postgres")
    admin = create_engine(admin_url.render_as_string(hide_password=False), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": target.database},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    url = _test_database_url()
    try:
        _ensure_database(url)
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable for tests: {exc}")

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture(scope="session")
def app() -> FastAPI:
    return create_application()


@pytest.fixture
def client(app: FastAPI, db: Session) -> Iterator[TestClient]:
    """A client whose requests share the test's transaction."""

    def _override_get_db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def anon_client(app: FastAPI) -> Iterator[TestClient]:
    """A client with no database override, for tests that touch no data."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def run_task_with_test_session(db: Session, monkeypatch: pytest.MonkeyPatch):
    """Point a Celery task's own ``SessionLocal`` at this test's session.

    Tasks correctly open their own session -- a real worker is a separate
    process with no request context. Under the rollback-isolated fixture that
    session sits on a different connection and cannot see the test's
    uncommitted rows, so a task invoked synchronously would silently find
    nothing and no-op. This redirects it to the test session and neutralises
    ``close()``, so the fixture keeps ownership of the transaction.

    Usage::

        import app.tasks.document_tasks as document_tasks
        run_task_with_test_session(document_tasks)
        process_uploaded_file(job_id)
    """

    class _SessionProxy:
        def __getattr__(self, item):
            return getattr(db, item)

        def close(self) -> None:  # the fixture closes it, not the task
            pass

    def _patch(task_module) -> None:
        monkeypatch.setattr(task_module, "SessionLocal", lambda: _SessionProxy())

    return _patch


# --------------------------------------------------------------- user factory
DEFAULT_PASSWORD = "TestPass123"


@pytest.fixture
def make_user(db: Session):
    """Create a persisted user. Returns the ORM object."""

    def _make(
        role: UserRole = UserRole.SITE_SUPERVISOR,
        *,
        email: str | None = None,
        password: str = DEFAULT_PASSWORD,
        is_active: bool = True,
        full_name: str = "Test User",
    ) -> User:
        user = User(
            email=email or f"user-{uuid.uuid4().hex[:10]}@example.com",
            hashed_password=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture
def admin_user(make_user):
    return make_user(UserRole.ADMIN, full_name="Admin User")


@pytest.fixture
def manager_user(make_user):
    return make_user(UserRole.PROJECT_MANAGER, full_name="Manager User")


@pytest.fixture
def supervisor_user(make_user):
    return make_user(UserRole.SITE_SUPERVISOR, full_name="Supervisor User")


@pytest.fixture
def auth_headers(client: TestClient):
    """Log a user in through the real endpoint and return bearer headers.

    Going through /auth/login rather than minting a token directly means the
    tests exercise the same path production does.
    """

    def _headers(user: User, password: str = DEFAULT_PASSWORD) -> dict[str, str]:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": password},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _headers


@pytest.fixture
def test_project(client: TestClient, manager_user: User, auth_headers):
    """Create a project under the manager user and return (project_id, headers)."""
    headers = auth_headers(manager_user)
    response = client.post(
        "/api/v1/projects",
        json={
            "code": f"PROJ-{uuid.uuid4().hex[:6].upper()}",
            "name": "Test Project",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"], headers
