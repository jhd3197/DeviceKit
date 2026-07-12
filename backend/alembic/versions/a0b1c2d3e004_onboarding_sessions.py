"""device onboarding state machine (plan 25 part 4)

Revision ID: a0b1c2d3e004
Revises: f9a0b1c2d003
Create Date: 2026-07-12 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a0b1c2d3e004'
down_revision = 'f9a0b1c2d003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'onboarding_sessions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('serial', sa.String(), nullable=True),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('started_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.Column('completed_at', sa.Float(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_onboarding_sessions_device_id', 'onboarding_sessions', ['device_id'])
    op.create_index('ix_onboarding_sessions_state', 'onboarding_sessions', ['state'])
    op.create_index('ix_onboarding_sessions_workspace_id', 'onboarding_sessions', ['workspace_id'])


def downgrade():
    op.drop_index('ix_onboarding_sessions_workspace_id', table_name='onboarding_sessions')
    op.drop_index('ix_onboarding_sessions_state', table_name='onboarding_sessions')
    op.drop_index('ix_onboarding_sessions_device_id', table_name='onboarding_sessions')
    op.drop_table('onboarding_sessions')
