"""Persistence queries for tenant-scoped document aggregates."""
from __future__ import annotations
import uuid
from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.document import ProcessingJob, ProgressReport, UploadedFile
from app.repositories.base import BaseRepository

class UploadedFileRepository(BaseRepository[UploadedFile]):
    def __init__(self, db: Session) -> None: super().__init__(UploadedFile, db)
    def list_for_project(self, project_id: uuid.UUID, *, skip: int, limit: int) -> Sequence[UploadedFile]:
        return self.db.execute(select(UploadedFile).filter_by(project_id=project_id).order_by(UploadedFile.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    def count_for_project(self, project_id: uuid.UUID) -> int: return self.count(project_id=project_id)
class ProcessingJobRepository(BaseRepository[ProcessingJob]):
    def __init__(self, db: Session) -> None: super().__init__(ProcessingJob, db)
class ProgressReportRepository(BaseRepository[ProgressReport]):
    def __init__(self, db: Session) -> None: super().__init__(ProgressReport, db)
    def list_for_project(self, project_id: uuid.UUID, *, skip: int, limit: int) -> Sequence[ProgressReport]:
        return self.db.execute(select(ProgressReport).filter_by(project_id=project_id).order_by(ProgressReport.created_at.desc()).offset(skip).limit(limit)).scalars().all()
    def count_for_project(self, project_id: uuid.UUID) -> int: return self.count(project_id=project_id)
