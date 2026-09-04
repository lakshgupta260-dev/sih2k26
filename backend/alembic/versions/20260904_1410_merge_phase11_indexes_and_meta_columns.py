"""merge_phase11_indexes_and_meta_columns

Revision ID: f73aa946f6b7
Revises: 82904d0d199d, 5b67e650f985
Create Date: 2026-09-04 14:10:20.973827
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f73aa946f6b7'
down_revision: str | None = ('82904d0d199d', '5b67e650f985')
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
