"""Shared FastAPI dependencies.

Authentication and project-authorization dependencies are added in Phase 2;
this module is the single place routers import them from, so their signatures
can change without touching every router.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import PaginationParams

DbSession = Annotated[Session, Depends(get_db)]


def pagination_params(skip: int = 0, limit: int = 50) -> PaginationParams:
    """Validated offset/limit, shared by every collection endpoint."""
    return PaginationParams(skip=skip, limit=limit)


Pagination = Annotated[PaginationParams, Depends(pagination_params)]
