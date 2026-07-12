"""backups: DeviceKit's own-state backup + drill records (plan 25 part 6)

Revision ID: c2d3e4f50006
Revises: b1c2d3e4f005
Create Date: 2026-07-12 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2d3e4f50006'
down_revision = 'b1c2d3e4f005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'backups',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('manifest_path', sa.String(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('verify_level', sa.String(), nullable=False),
        sa.Column('verify_detail', sa.JSON(), nullable=True),
        sa.Column('drill_status', sa.String(), nullable=True),
        sa.Column('drill_detail', sa.JSON(), nullable=True),
        sa.Column('drilled_at', sa.Float(), nullable=True),
        sa.Column('chain_prev', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('backups')
