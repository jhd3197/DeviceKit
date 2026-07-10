"""ai agent confirmation-gate audit trail (plan 13)

Revision ID: b13a1c0de13
Revises: f6a7b8c9d0e1
Create Date: 2026-07-10 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b13a1c0de13'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_audit_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('tool', sa.String(), nullable=False),
        sa.Column('args', sa.JSON(), nullable=True),
        sa.Column('is_write', sa.Boolean(), nullable=False),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('mode', sa.String(), nullable=True),
        sa.Column('decision', sa.String(), nullable=False),
        sa.Column('approver', sa.String(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('resolved_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_audit_log_device_id', 'agent_audit_log', ['device_id'])
    op.create_index('ix_agent_audit_log_decision', 'agent_audit_log', ['decision'])
    op.create_index('ix_agent_audit_log_created_at', 'agent_audit_log', ['created_at'])


def downgrade():
    op.drop_index('ix_agent_audit_log_created_at', table_name='agent_audit_log')
    op.drop_index('ix_agent_audit_log_decision', table_name='agent_audit_log')
    op.drop_index('ix_agent_audit_log_device_id', table_name='agent_audit_log')
    op.drop_table('agent_audit_log')
