"""add extraction and matching models

Creates the Phase 5 tables: extracted_activities (candidate events pulled out
of progress reports) and activity_matches (their proposed or confirmed links to
plan activities, with per-signal scores and review state).

Revision ID: b839d30e73b7
Revises: 578f2312b604
Create Date: 2026-09-02 09:08:00.146896
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = 'b839d30e73b7'
down_revision: str | None = '578f2312b604'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'extracted_activities',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('progress_report_id', sa.UUID(), nullable=False),
        sa.Column('source_ref', sa.String(length=200), nullable=False),
        sa.Column('raw_text', sa.Text(), nullable=False),
        sa.Column('event_type', sa.String(length=32), nullable=False),
        sa.Column('activity_code', sa.String(length=100), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('discipline', sa.String(length=50), nullable=True),
        sa.Column('event_date', sa.Date(), nullable=True),
        sa.Column('percent_complete', sa.Float(), nullable=True),
        sa.Column('quantity', sa.Float(), nullable=True),
        sa.Column('uom', sa.String(length=50), nullable=True),
        sa.Column('chainage_from_m', sa.Float(), nullable=True),
        sa.Column('chainage_to_m', sa.Float(), nullable=True),
        sa.Column('joint_from', sa.Integer(), nullable=True),
        sa.Column('joint_to', sa.Integer(), nullable=True),
        sa.Column('extraction_confidence', sa.Float(), nullable=False),
        sa.Column('extractor', sa.String(length=50), nullable=False),
        sa.Column('notes', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'percent_complete IS NULL OR (percent_complete >= 0 AND percent_complete <= 100)',
            name=op.f('ck_extracted_activities_pct_range'),
        ),
        sa.ForeignKeyConstraint(
            ['progress_report_id'], ['progress_reports.id'],
            name=op.f('fk_extracted_activities_progress_report_id_progress_reports'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'],
            name=op.f('fk_extracted_activities_project_id_projects'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_extracted_activities')),
    )
    op.create_index(op.f('ix_extracted_activities_activity_code'), 'extracted_activities', ['activity_code'], unique=False)
    op.create_index(op.f('ix_extracted_activities_discipline'), 'extracted_activities', ['discipline'], unique=False)
    op.create_index(op.f('ix_extracted_activities_event_type'), 'extracted_activities', ['event_type'], unique=False)
    op.create_index(op.f('ix_extracted_activities_progress_report_id'), 'extracted_activities', ['progress_report_id'], unique=False)
    op.create_index(op.f('ix_extracted_activities_project_id'), 'extracted_activities', ['project_id'], unique=False)
    op.create_index('ix_extracted_activities_report_event', 'extracted_activities', ['progress_report_id', 'event_type'], unique=False)

    op.create_table(
        'activity_matches',
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('extracted_activity_id', sa.UUID(), nullable=False),
        sa.Column('activity_id', sa.UUID(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('auto_status', sa.String(length=32), nullable=False),
        sa.Column('method', sa.String(length=32), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('signals', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('candidates', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('embedding_provider', sa.String(length=50), nullable=True),
        sa.Column('reviewed_by_id', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "status <> 'AUTO_MATCHED' OR activity_id IS NOT NULL",
            name=op.f('ck_activity_matches_matched_requires_activity'),
        ),
        sa.CheckConstraint('score >= 0 AND score <= 1', name=op.f('ck_activity_matches_score_range')),
        sa.ForeignKeyConstraint(
            ['activity_id'], ['activities.id'],
            name=op.f('fk_activity_matches_activity_id_activities'), ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['extracted_activity_id'], ['extracted_activities.id'],
            name=op.f('fk_activity_matches_extracted_activity_id_extracted_activities'),
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['project_id'], ['projects.id'],
            name=op.f('fk_activity_matches_project_id_projects'), ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['reviewed_by_id'], ['users.id'],
            name=op.f('fk_activity_matches_reviewed_by_id_users'), ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_activity_matches')),
    )
    op.create_index(op.f('ix_activity_matches_activity_id'), 'activity_matches', ['activity_id'], unique=False)
    op.create_index(op.f('ix_activity_matches_extracted_activity_id'), 'activity_matches', ['extracted_activity_id'], unique=False)
    op.create_index(op.f('ix_activity_matches_project_id'), 'activity_matches', ['project_id'], unique=False)
    op.create_index('ix_activity_matches_project_status', 'activity_matches', ['project_id', 'status'], unique=False)
    op.create_index(op.f('ix_activity_matches_status'), 'activity_matches', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_activity_matches_status'), table_name='activity_matches')
    op.drop_index('ix_activity_matches_project_status', table_name='activity_matches')
    op.drop_index(op.f('ix_activity_matches_project_id'), table_name='activity_matches')
    op.drop_index(op.f('ix_activity_matches_extracted_activity_id'), table_name='activity_matches')
    op.drop_index(op.f('ix_activity_matches_activity_id'), table_name='activity_matches')
    op.drop_table('activity_matches')
    op.drop_index('ix_extracted_activities_report_event', table_name='extracted_activities')
    op.drop_index(op.f('ix_extracted_activities_project_id'), table_name='extracted_activities')
    op.drop_index(op.f('ix_extracted_activities_progress_report_id'), table_name='extracted_activities')
    op.drop_index(op.f('ix_extracted_activities_event_type'), table_name='extracted_activities')
    op.drop_index(op.f('ix_extracted_activities_discipline'), table_name='extracted_activities')
    op.drop_index(op.f('ix_extracted_activities_activity_code'), table_name='extracted_activities')
    op.drop_table('extracted_activities')
