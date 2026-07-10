"""per-device HMAC secret + key rotation columns (plan 07 phase 2)

Revision ID: a71c07a20002
Revises: a71c07a10001
Create Date: 2026-07-10 12:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c07a20002'
down_revision = 'a71c07a10001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_devices', sa.Column('secret', sa.String(), nullable=True))
    op.add_column('agent_devices', sa.Column('secret_pending', sa.String(), nullable=True))
    op.add_column('agent_devices', sa.Column('secret_rotated_at', sa.Float(), nullable=True))
    op.add_column('agent_devices', sa.Column('last_ip', sa.String(), nullable=True))


def downgrade():
    op.drop_column('agent_devices', 'last_ip')
    op.drop_column('agent_devices', 'secret_rotated_at')
    op.drop_column('agent_devices', 'secret_pending')
    op.drop_column('agent_devices', 'secret')
