"""desired-state fleet policies (plan 23 part 2)

Revision ID: d7e8f9a0b001
Revises: c6d7e8f9a001
Create Date: 2026-07-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7e8f9a0b001'
down_revision = 'c6d7e8f9a001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fleet_policies',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('target_kind', sa.String(), nullable=False),
        sa.Column('target_value', sa.String(), nullable=False),
        sa.Column('raw_yaml', sa.Text(), nullable=False),
        sa.Column('normalized', sa.JSON(), nullable=False),
        sa.Column('policy_hash', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('status_detail', sa.JSON(), nullable=True),
        sa.Column('auto_apply', sa.Boolean(), nullable=False),
        sa.Column('source', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.Column('applied_at', sa.Float(), nullable=True),
        sa.Column('applied_hash', sa.String(), nullable=True),
        sa.Column('last_checked_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fleet_policies_workspace_id', 'fleet_policies', ['workspace_id'])
    op.create_index('ix_fleet_policies_status', 'fleet_policies', ['status'])


def downgrade():
    op.drop_index('ix_fleet_policies_status', table_name='fleet_policies')
    op.drop_index('ix_fleet_policies_workspace_id', table_name='fleet_policies')
    op.drop_table('fleet_policies')
