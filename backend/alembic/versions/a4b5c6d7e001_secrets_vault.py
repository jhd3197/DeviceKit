"""encrypted secrets vault (plan 20 part 5)

Revision ID: a4b5c6d7e001
Revises: f3a4b5c6d001
Create Date: 2026-07-11 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e001'
down_revision = 'f3a4b5c6d001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vaults',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_vaults_slug', 'vaults', ['slug'], unique=True)
    op.create_index('ix_vaults_workspace_id', 'vaults', ['workspace_id'])

    op.create_table(
        'vault_secrets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('vault_id', sa.String(), nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.Float(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('vault_id', 'key', name='uq_vault_secret_key'),
    )
    op.create_index('ix_vault_secrets_vault_id', 'vault_secrets', ['vault_id'])


def downgrade():
    op.drop_index('ix_vault_secrets_vault_id', table_name='vault_secrets')
    op.drop_table('vault_secrets')
    op.drop_index('ix_vaults_workspace_id', table_name='vaults')
    op.drop_index('ix_vaults_slug', table_name='vaults')
    op.drop_table('vaults')
