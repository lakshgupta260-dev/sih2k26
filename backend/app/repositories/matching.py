"""Extraction and match persistence."""
from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.constants import MatchStatus
from app.models.matching import ActivityMatch, ExtractedActivity
from app.repositories.base import BaseRepository


class ExtractedActivityRepository(BaseRepository[ExtractedActivity]):
    def __init__(self, db: Session) -> None:
        super().__init__(ExtractedActivity, db)

    def list_for_report(self, report_id: uuid.UUID) -> Sequence[ExtractedActivity]:
        stmt = (
            select(ExtractedActivity)
            .where(ExtractedActivity.progress_report_id == report_id)
            .order_by(ExtractedActivity.source_ref)
        )
        return self.db.execute(stmt).scalars().all()

    def count_for_report(self, report_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(ExtractedActivity)
            .where(ExtractedActivity.progress_report_id == report_id)
        )
        return int(self.db.execute(stmt).scalar_one())

    def delete_for_report(self, report_id: uuid.UUID) -> int:
        """Used when reprocessing a report, so items are replaced not duplicated."""
        rows = self.list_for_report(report_id)
        for row in rows:
            self.db.delete(row)
        self.db.flush()
        return len(rows)


class ActivityMatchRepository(BaseRepository[ActivityMatch]):
    def __init__(self, db: Session) -> None:
        super().__init__(ActivityMatch, db)

    def get_with_extracted(self, match_id: uuid.UUID) -> ActivityMatch | None:
        stmt = (
            select(ActivityMatch)
            .options(joinedload(ActivityMatch.extracted_activity))
            .where(ActivityMatch.id == match_id)
        )
        return self.db.execute(stmt).unique().scalar_one_or_none()

    def list_for_project(
        self,
        project_id: uuid.UUID,
        *,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[ActivityMatch]:
        stmt = (
            select(ActivityMatch)
            .options(joinedload(ActivityMatch.extracted_activity))
            .where(ActivityMatch.project_id == project_id)
        )
        if status:
            stmt = stmt.where(ActivityMatch.status == status)
        # Highest score first inside the review queue: the near-misses are the
        # ones a reviewer can clear fastest.
        stmt = (
            stmt.order_by(ActivityMatch.score.desc(), ActivityMatch.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.execute(stmt).unique().scalars().all()

    def count_for_project(self, project_id: uuid.UUID, *, status: str | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(ActivityMatch)
            .where(ActivityMatch.project_id == project_id)
        )
        if status:
            stmt = stmt.where(ActivityMatch.status == status)
        return int(self.db.execute(stmt).scalar_one())

    def status_counts(self, project_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(ActivityMatch.status, func.count())
            .where(ActivityMatch.project_id == project_id)
            .group_by(ActivityMatch.status)
        )
        return {status: count for status, count in self.db.execute(stmt).all()}

    def auto_review_agreement(self, project_id: uuid.UUID) -> tuple[int, int]:
        """(upheld, reviewed) among links the machine proposed automatically.

        Only rows whose ``auto_status`` was AUTO_MATCHED and which a human has
        since ruled on. This is the matcher's measured precision, not an
        estimate.
        """
        stmt = (
            select(ActivityMatch.status, func.count())
            .where(
                ActivityMatch.project_id == project_id,
                ActivityMatch.auto_status == MatchStatus.AUTO_MATCHED,
                ActivityMatch.status.in_(
                    [MatchStatus.MANUALLY_CONFIRMED, MatchStatus.MANUALLY_REJECTED]
                ),
            )
            .group_by(ActivityMatch.status)
        )
        counts = {status: count for status, count in self.db.execute(stmt).all()}
        upheld = counts.get(MatchStatus.MANUALLY_CONFIRMED, 0)
        reviewed = upheld + counts.get(MatchStatus.MANUALLY_REJECTED, 0)
        return upheld, reviewed

    def delete_for_extracted(self, extracted_ids: list[uuid.UUID]) -> None:
        if not extracted_ids:
            return
        rows = (
            self.db.execute(
                select(ActivityMatch).where(
                    ActivityMatch.extracted_activity_id.in_(extracted_ids)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            self.db.delete(row)
        self.db.flush()
