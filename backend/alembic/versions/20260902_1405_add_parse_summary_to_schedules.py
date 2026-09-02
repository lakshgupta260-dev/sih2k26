"""Add parse_summary to schedules.

Records what a schedule import actually did -- rows read, activities created,
and every row, date and dependency the parser could not use. Previously those
were dropped silently, so a schedule could report COMPLETED with a third of
its dependency network missing and nothing anywhere said so.

Backfilled to an empty object, which reads correctly as "imported before this
was recorded".

Revision ID: 533f361c3eaa
Revises: 94a858ee6650
Create Date: 2026-09-02 14:05:05.461991
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '533f361c3eaa'
down_revision: str | None = '94a858ee6650'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('schedules', sa.Column('parse_summary', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))


def downgrade() -> None:
    op.drop_column('schedules', 'parse_summary')
