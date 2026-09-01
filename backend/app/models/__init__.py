"""SQLAlchemy model registry.

Every model module must be imported here. Alembic's autogenerate walks
``Base.metadata``, and a model that is never imported is invisible to it --
which silently produces migrations that create nothing.
"""
from app.db.base import Base
from app.models.audit import AuditLog
from app.models.project import Project, ProjectMembership
from app.models.user import RefreshToken, User
from app.models.schedule import Schedule, Activity, ActivityDependency

__all__ = [
    "Base",
    "AuditLog",
    "Project",
    "ProjectMembership",
    "RefreshToken",
    "User",
    "Schedule",
    "Activity",
    "ActivityDependency",
]
