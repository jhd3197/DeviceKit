"""agent version negotiation columns (plan 25 part 2)

Revision ID: e8f9a0b1c002
Revises: d7e8f9a0b001
Create Date: 2026-07-12 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f9a0b1c002'
down_revision = 'd7e8f9a0b001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_devices', sa.Column('agent_version', sa.String(), nullable=True))
    op.add_column('agent_devices', sa.Column('agent_version_code', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('agent_devices', 'agent_version_code')
    op.drop_column('agent_devices', 'agent_version')
