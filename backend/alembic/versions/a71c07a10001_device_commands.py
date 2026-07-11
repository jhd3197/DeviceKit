"""device command audit trail (plan 07 phase 1)

Revision ID: a71c07a10001
Revises: e5f6a7b8c9d0
Create Date: 2026-07-10 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c07a10001'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'device_commands',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('command', sa.String(), nullable=False),
        sa.Column('args', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('started_at', sa.Float(), nullable=True),
        sa.Column('completed_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_commands_device_id', 'device_commands', ['device_id'])
    op.create_index('ix_device_commands_status', 'device_commands', ['status'])


def downgrade():
    op.drop_index('ix_device_commands_status', table_name='device_commands')
    op.drop_index('ix_device_commands_device_id', table_name='device_commands')
    op.drop_table('device_commands')
