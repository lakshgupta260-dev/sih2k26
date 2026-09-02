"""Add constraints to schedule models

Revision ID: 578f2312b604
Revises: d93681770df1
Create Date: 2026-09-02 08:12:16.869721
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '578f2312b604'
down_revision: str | None = 'd93681770df1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint('uq_activity_code_per_schedule', 'activities', ['schedule_id', 'activity_code'])
    op.create_check_constraint('ck_activities_level_range', 'activities', 'level >= 1 AND level <= 6')
    op.create_check_constraint('ck_activity_dependencies_no_self', 'activity_dependencies', 'predecessor_id != successor_id')


def downgrade() -> None:
    op.drop_constraint('ck_activity_dependencies_no_self', 'activity_dependencies', type_='check')
    op.drop_constraint('ck_activities_level_range', 'activities', type_='check')
    op.drop_constraint('uq_activity_code_per_schedule', 'activities', type_='unique')
