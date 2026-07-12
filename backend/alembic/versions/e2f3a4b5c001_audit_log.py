"""user-attributed audit log (plan 20 part 3)

Revision ID: e2f3a4b5c001
Revises: d1e2f3a4b001
Create Date: 2026-07-11 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c001'
down_revision = 'd1e2f3a4b001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('username', sa.String(), nullable=True),
        sa.Column('principal_kind', sa.String(), nullable=True),
        sa.Column('target_type', sa.String(), nullable=True),
        sa.Column('target_id', sa.String(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('status', sa.Integer(), nullable=True),
        sa.Column('ip', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])
    op.create_index('ix_audit_log_user_id', 'audit_log', ['user_id'])
    op.create_index('ix_audit_log_target_type', 'audit_log', ['target_type'])
    op.create_index('ix_audit_log_target_id', 'audit_log', ['target_id'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])


def downgrade():
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_index('ix_audit_log_target_id', table_name='audit_log')
    op.drop_index('ix_audit_log_target_type', table_name='audit_log')
    op.drop_index('ix_audit_log_user_id', table_name='audit_log')
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_table('audit_log')
