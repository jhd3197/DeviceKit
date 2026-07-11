"""installed extensions (plan 03)

Revision ID: a1b2c3d4e5f6
Revises: f71bdf167605
Create Date: 2026-07-10 01:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f71bdf167605'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'installed_extensions',
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('display_name', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('url_prefix', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('sha256', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('installed_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('slug'),
    )


def downgrade():
    op.drop_table('installed_extensions')
