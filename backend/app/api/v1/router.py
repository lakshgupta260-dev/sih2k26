"""Aggregate router for API v1.

Routers are registered here and nowhere else, so ``main.py`` never grows a
list of imports and a new module is one line to wire in.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()

api_router.include_router(health.router)

# Registered in later phases:
#   auth, users, projects, schedules, activities, reports, documents,
#   matching, progress, analytics, risks, ml, assistant, notifications,
#   admin, integrations.meta, integrations.vapi
