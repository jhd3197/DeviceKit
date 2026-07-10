"""agent capability advertisement column (plan 07 phase 4)

Revision ID: a71c07a40004
Revises: a71c07a30003
Create Date: 2026-07-10 12:15:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a71c07a40004'
down_revision = 'a71c07a30003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('agent_devices', sa.Column('capabilities', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('agent_devices', 'capabilities')
