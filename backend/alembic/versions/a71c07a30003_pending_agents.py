"""pending-agent enrollment rows (plan 07 phase 3, pairing flow)

Revision ID: a71c07a30003
Revises: a71c07a20002
Create Date: 2026-07-10 12:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c07a30003'
down_revision = 'a71c07a20002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pending_agents',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('info', sa.JSON(), nullable=True),
        sa.Column('serial', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('claimed', sa.Boolean(), nullable=True),
        sa.Column('issued_secret', sa.String(), nullable=True),
        sa.Column('last_ip', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pending_agents_code', 'pending_agents', ['code'])


def downgrade():
    op.drop_index('ix_pending_agents_code', table_name='pending_agents')
    op.drop_table('pending_agents')
