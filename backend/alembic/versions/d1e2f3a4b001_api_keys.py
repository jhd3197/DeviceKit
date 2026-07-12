"""scoped api keys (plan 20 part 2)

Revision ID: d1e2f3a4b001
Revises: c0d0a1b2e001
Create Date: 2026-07-11 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1e2f3a4b001'
down_revision = 'c0d0a1b2e001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_keys',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('prefix', sa.String(), nullable=False),
        sa.Column('key_hash', sa.String(), nullable=False),
        sa.Column('scopes', sa.JSON(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=True),
        sa.Column('revoked_at', sa.Float(), nullable=True),
        sa.Column('last_used_at', sa.Float(), nullable=True),
        sa.Column('last_used_ip', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_keys_prefix', 'api_keys', ['prefix'])
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'], unique=True)


def downgrade():
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_index('ix_api_keys_prefix', table_name='api_keys')
    op.drop_table('api_keys')
