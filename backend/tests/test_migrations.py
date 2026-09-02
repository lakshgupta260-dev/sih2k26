"""Migration-chain guards.

``conftest.py`` builds the schema with ``Base.metadata.create_all()``, which is
fast and correct for testing application behaviour -- but it means the ordinary
test suite never executes Alembic. A broken migration chain therefore passes
every other test and only fails at deploy time, when docker-compose runs
``alembic upgrade head``.

These tests close that gap. They are cheap and they catch the two mistakes that
actually happen when several people add migrations in parallel: a second head,
and a migration that drifts from the models.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  (registers every model on Base.metadata)

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def test_exactly_one_head() -> None:
    """Two heads make ``alembic upgrade head`` abort.

    This happens whenever two branches each add a migration whose
    ``down_revision`` is the same parent. Fix by pointing the newer migration's
    ``down_revision`` at the other one, or with ``alembic merge``.
    """
    heads = ScriptDirectory.from_config(_alembic_config()).get_heads()
    assert len(heads) == 1, (
        f"expected a single migration head, found {len(heads)}: {heads}. "
        "'alembic upgrade head' cannot run until this is resolved."
    )


def test_every_revision_is_reachable() -> None:
    """No orphan revisions: walking back from the head must reach every file."""
    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_heads()[0]
    reachable = {rev.revision for rev in script.walk_revisions(base="base", head=head)}
    on_disk = {rev.revision for rev in script.walk_revisions()}
    assert on_disk == reachable, f"unreachable revisions: {on_disk - reachable}"


def test_migrations_produce_the_model_schema() -> None:
    """Upgrading a fresh database must leave zero drift against the models.

    Drift means a model changed without a migration, so the deployed schema and
    the ORM disagree.

    Alembic is driven in a subprocess with ``DATABASE_URL`` set, because
    ``alembic/env.py`` deliberately reads the URL from application settings and
    ignores ``sqlalchemy.url`` passed via the Config object. Running it this way
    exercises exactly the command docker-compose runs on boot.
    """
    import os
    import subprocess
    import sys

    url = make_url(settings.sqlalchemy_database_uri).set(database="sih_migration_check")
    try:
        admin = create_engine(str(url.set(database="postgres")), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n"
                ),
                {"n": url.database},
            )
            conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}"'))
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL not reachable for the migration check: {exc}")

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env={**os.environ, "DATABASE_URL": str(url)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"'alembic upgrade head' failed:\n{result.stdout}\n{result.stderr}"
    )

    engine = create_engine(str(url))
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    # Constraint and index names are compared by name; the naming convention in
    # app/db/base.py makes those deterministic, so any entry here is real drift.
    assert diff == [], (
        "schema drift between migrations and models:\n"
        + "\n".join(f"  - {d[0]}: {d[1:]}"[:200] for d in diff)
    )
