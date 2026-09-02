"""SQLAlchemy model registry.

Every model module must be imported here. Alembic's autogenerate walks
``Base.metadata``, and a model that is never imported is invisible to it --
which silently produces migrations that create nothing.
"""
from app.db.base import Base
from app.models.audit import AuditLog
from app.models.matching import ActivityMatch, ExtractedActivity
from app.models.project import Project, ProjectMembership
from app.models.user import RefreshToken, User
from app.models.schedule import Schedule, Activity, ActivityDependency
from app.models.document import ProcessingJob, ProgressReport, UploadedFile
from app.models.progress import ActualProgress

__all__ = [
    "Base",
    "ActualProgress",
    "ActivityMatch",
    "AuditLog",
    "ExtractedActivity",
    "Project",
    "ProjectMembership",
    "RefreshToken",
    "User",
    "Schedule",
    "Activity",
    "ActivityDependency",
    "UploadedFile",
    "ProcessingJob",
    "ProgressReport",
]
