"""Database engine and session lifecycle.

Synchronous SQLAlchemy is used deliberately. FastAPI runs sync dependencies in
a worker threadpool, and the same Session factory is then reusable from Celery
workers without maintaining a second async engine. Given that the heavy work in
this platform (PDF parsing, embeddings, model inference) is CPU-bound and lives
in workers rather than in the request path, async DB access would add moving
parts without buying throughput.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _build_engine() -> Engine:
    return create_engine(
        settings.sqlalchemy_database_uri,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        echo=settings.DB_ECHO,
        future=True,
    )


engine: Engine = _build_engine()

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that always closes.

    The session is *not* committed here. Services own transaction boundaries so
    that a multi-step operation either lands completely or not at all.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> bool:
    """Cheap liveness probe used by the readiness endpoint."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        logger.warning("database_unreachable", extra={"error": str(exc)})
        return False
