"""invitations + user TOTP columns (plan 20 part 6)

Revision ID: b5c6d7e8f001
Revises: a4b5c6d7e001
Create Date: 2026-07-11 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c6d7e8f001'
down_revision = 'a4b5c6d7e001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'invitations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.Column('workspace_role', sa.String(), nullable=True),
        sa.Column('invited_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=True),
        sa.Column('accepted_at', sa.Float(), nullable=True),
        sa.Column('accepted_user_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invitations_token_hash', 'invitations', ['token_hash'], unique=True)

    op.add_column('users', sa.Column('totp_secret', sa.String(), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False,
                                     server_default=sa.false()))
    op.add_column('users', sa.Column('backup_codes', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('users', 'backup_codes')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
    op.drop_index('ix_invitations_token_hash', table_name='invitations')
    op.drop_table('invitations')
