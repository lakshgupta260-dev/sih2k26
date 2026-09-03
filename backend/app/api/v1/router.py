"""Aggregate router for API v1.

Routers are registered here and nowhere else, so ``main.py`` never grows a
list of imports and a new module is one line to wire in.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    activities,
    analytics,
    auth,
    documents,
    generated_reports,
    health,
    matching,
    notifications,
    prediction,
    progress,
    projects,
    reports,
    schedules,
    users,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(projects.router)
api_router.include_router(schedules.router)
api_router.include_router(activities.router)
api_router.include_router(documents.router)
api_router.include_router(documents.jobs_router)
api_router.include_router(reports.router)
api_router.include_router(generated_reports.router)
api_router.include_router(notifications.router)
api_router.include_router(notifications.project_notifications_router)
api_router.include_router(matching.router)
api_router.include_router(progress.router)
api_router.include_router(analytics.router)
api_router.include_router(prediction.router)

from app.api.v1.integrations import meta
api_router.include_router(meta.router)

from app.api.v1.integrations import vapi
api_router.include_router(vapi.router)

from app.api.v1 import assistant
api_router.include_router(assistant.router)

# Registered in later phases:
#   risks, admin
