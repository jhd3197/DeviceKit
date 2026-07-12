"""OTA agent updates: releases, rollouts, per-device update state (plan 25 part 3)

Revision ID: f9a0b1c2d003
Revises: e8f9a0b1c002
Create Date: 2026-07-12 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a0b1c2d003'
down_revision = 'e8f9a0b1c002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_releases',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('version_name', sa.String(), nullable=False),
        sa.Column('version_code', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('signature', sa.String(), nullable=False),
        sa.Column('public_key', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'agent_rollouts',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('release_id', sa.String(), nullable=False),
        sa.Column('target_kind', sa.String(), nullable=False),
        sa.Column('target_value', sa.String(), nullable=True),
        sa.Column('stage', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('stage_entered_at', sa.Float(), nullable=True),
        sa.Column('rollback_of', sa.String(), nullable=True),
        sa.Column('status_detail', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_rollouts_release_id', 'agent_rollouts', ['release_id'])
    op.create_index('ix_agent_rollouts_status', 'agent_rollouts', ['status'])
    op.create_index('ix_agent_rollouts_workspace_id', 'agent_rollouts', ['workspace_id'])
    op.create_table(
        'agent_update_states',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('rollout_id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('release_id', sa.String(), nullable=False),
        sa.Column('target_version_code', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rollout_id', 'device_id', name='uq_update_rollout_device'),
    )
    op.create_index('ix_agent_update_states_rollout_id', 'agent_update_states', ['rollout_id'])
    op.create_index('ix_agent_update_states_device_id', 'agent_update_states', ['device_id'])


def downgrade():
    op.drop_index('ix_agent_update_states_device_id', table_name='agent_update_states')
    op.drop_index('ix_agent_update_states_rollout_id', table_name='agent_update_states')
    op.drop_table('agent_update_states')
    op.drop_index('ix_agent_rollouts_workspace_id', table_name='agent_rollouts')
    op.drop_index('ix_agent_rollouts_status', table_name='agent_rollouts')
    op.drop_index('ix_agent_rollouts_release_id', table_name='agent_rollouts')
    op.drop_table('agent_rollouts')
    op.drop_table('agent_releases')
