"""Generic persistence layer.

The repository owns *how* rows are fetched and written; services own *why*.
Keeping that split means a service can be unit-tested against a fake repository,
and a query optimisation never leaks into business logic.
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """CRUD operations common to every aggregate."""

    def __init__(self, model: type[ModelT], db: Session) -> None:
        self.model = model
        self.db = db

    # ------------------------------------------------------------------ read
    def get(self, entity_id: uuid.UUID) -> ModelT | None:
        return self.db.get(self.model, entity_id)

    def get_by(self, **filters: Any) -> ModelT | None:
        stmt = select(self.model).filter_by(**filters).limit(1)
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
        **filters: Any,
    ) -> Sequence[ModelT]:
        stmt = select(self.model).filter_by(**filters)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(skip).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def count(self, **filters: Any) -> int:
        stmt = select(func.count()).select_from(self.model).filter_by(**filters)
        return int(self.db.execute(stmt).scalar_one())

    def exists(self, **filters: Any) -> bool:
        return self.count(**filters) > 0

    # ----------------------------------------------------------------- write
    def create(self, **values: Any) -> ModelT:
        instance = self.model(**values)
        self.db.add(instance)
        self.db.flush()
        return instance

    def update(self, instance: ModelT, **values: Any) -> ModelT:
        for key, value in values.items():
            if value is not None or hasattr(instance, key):
                setattr(instance, key, value)
        self.db.add(instance)
        self.db.flush()
        return instance

    def delete(self, instance: ModelT) -> None:
        """Hard delete. Prefer soft deletion for anything audited."""
        self.db.delete(instance)
        self.db.flush()
