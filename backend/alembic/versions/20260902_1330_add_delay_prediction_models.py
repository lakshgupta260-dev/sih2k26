"""Add delay prediction models (Phase 7).

Two tables. ``delay_model_versions`` is the registry of fitted, promoted
models with the cross-validated metrics behind each -- including
``baseline_roc_auc``, what the rule-based forecast scored on the same
activities, so the promotion decision stays checkable after the fact. Retired
rows are kept rather than deleted so an older prediction still resolves to the
artefact that produced it.

``delay_predictions`` holds the current forecast per activity, with the
method, inputs and explanation stored alongside, so a forecast a planner acted
on can still be reconstructed months later.

Revision ID: 94a858ee6650
Revises: 31186611e9b5
Create Date: 2026-09-02 13:30:20.872326
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '94a858ee6650'
down_revision: str | None = '31186611e9b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('delay_model_versions',
    sa.Column('project_id', sa.UUID(), nullable=True),
    sa.Column('version', sa.String(length=64), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('artefact_path', sa.String(length=500), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('training_samples', sa.Integer(), nullable=False),
    sa.Column('late_samples', sa.Integer(), nullable=False),
    sa.Column('on_time_samples', sa.Integer(), nullable=False),
    sa.Column('train_samples', sa.Integer(), nullable=False),
    sa.Column('test_samples', sa.Integer(), nullable=False),
    sa.Column('roc_auc', sa.Float(), nullable=True),
    sa.Column('accuracy', sa.Float(), nullable=True),
    sa.Column('precision', sa.Float(), nullable=True),
    sa.Column('recall', sa.Float(), nullable=True),
    sa.Column('f1', sa.Float(), nullable=True),
    sa.Column('brier', sa.Float(), nullable=True),
    sa.Column('baseline_roc_auc', sa.Float(), nullable=True),
    sa.Column('feature_names', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('feature_importances', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('hyperparameters', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('trained_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('roc_auc IS NULL OR (roc_auc >= 0 AND roc_auc <= 1)', name=op.f('ck_delay_model_versions_roc_auc_range')),
    sa.CheckConstraint('training_samples > 0', name=op.f('ck_delay_model_versions_training_samples_positive')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_delay_model_versions_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trained_by_id'], ['users.id'], name=op.f('fk_delay_model_versions_trained_by_id_users'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_delay_model_versions')),
    sa.UniqueConstraint('version', name='uq_delay_model_version')
    )
    op.create_index('ix_delay_model_project_active', 'delay_model_versions', ['project_id', 'is_active'], unique=False)
    op.create_index(op.f('ix_delay_model_versions_project_id'), 'delay_model_versions', ['project_id'], unique=False)
    op.create_table('delay_predictions',
    sa.Column('project_id', sa.UUID(), nullable=False),
    sa.Column('schedule_id', sa.UUID(), nullable=False),
    sa.Column('activity_id', sa.UUID(), nullable=False),
    sa.Column('method', sa.String(length=32), nullable=False),
    sa.Column('model_version_id', sa.UUID(), nullable=True),
    sa.Column('probability', sa.Float(), nullable=False),
    sa.Column('predicted_late', sa.Boolean(), nullable=False),
    sa.Column('risk_level', sa.String(length=16), nullable=False),
    sa.Column('planned_finish', sa.Date(), nullable=True),
    sa.Column('forecast_finish', sa.Date(), nullable=True),
    sa.Column('forecast_slip_days', sa.Integer(), nullable=True),
    sa.Column('as_of', sa.Date(), nullable=False),
    sa.Column('features', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('explanation', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('caveats', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
    sa.Column('generated_by_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('probability >= 0 AND probability <= 1', name=op.f('ck_delay_predictions_probability_range')),
    sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], name=op.f('fk_delay_predictions_activity_id_activities'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['generated_by_id'], ['users.id'], name=op.f('fk_delay_predictions_generated_by_id_users'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['model_version_id'], ['delay_model_versions.id'], name=op.f('fk_delay_predictions_model_version_id_delay_model_versions'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_delay_predictions_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['schedule_id'], ['schedules.id'], name=op.f('fk_delay_predictions_schedule_id_schedules'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_delay_predictions')),
    sa.UniqueConstraint('activity_id', name='uq_delay_prediction_activity')
    )
    op.create_index(op.f('ix_delay_predictions_activity_id'), 'delay_predictions', ['activity_id'], unique=False)
    op.create_index(op.f('ix_delay_predictions_as_of'), 'delay_predictions', ['as_of'], unique=False)
    op.create_index(op.f('ix_delay_predictions_method'), 'delay_predictions', ['method'], unique=False)
    op.create_index(op.f('ix_delay_predictions_model_version_id'), 'delay_predictions', ['model_version_id'], unique=False)
    op.create_index(op.f('ix_delay_predictions_project_id'), 'delay_predictions', ['project_id'], unique=False)
    op.create_index(op.f('ix_delay_predictions_risk_level'), 'delay_predictions', ['risk_level'], unique=False)
    op.create_index(op.f('ix_delay_predictions_schedule_id'), 'delay_predictions', ['schedule_id'], unique=False)
    op.create_index('ix_delay_predictions_schedule_risk', 'delay_predictions', ['schedule_id', 'risk_level'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_delay_predictions_schedule_risk', table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_schedule_id'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_risk_level'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_project_id'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_model_version_id'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_method'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_as_of'), table_name='delay_predictions')
    op.drop_index(op.f('ix_delay_predictions_activity_id'), table_name='delay_predictions')
    op.drop_table('delay_predictions')
    op.drop_index(op.f('ix_delay_model_versions_project_id'), table_name='delay_model_versions')
    op.drop_index('ix_delay_model_project_active', table_name='delay_model_versions')
    op.drop_table('delay_model_versions')
