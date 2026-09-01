"""SQLAlchemy model registry.

Every model module must be imported here. Alembic's autogenerate walks
``Base.metadata``, and a model that is never imported is invisible to it --
which silently produces migrations that drop nothing and create nothing.

Models are introduced from Phase 2 onward.
"""
from app.db.base import Base

__all__ = ["Base"]
