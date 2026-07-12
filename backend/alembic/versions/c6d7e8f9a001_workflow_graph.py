"""workflow graph columns (plan 22): WorkflowDoc storage + webhook token + run kind

Revision ID: c6d7e8f9a001
Revises: b5c6d7e8f001
Create Date: 2026-07-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9a001'
down_revision = 'b5c6d7e8f001'
branch_labels = None
depends_on = None


def upgrade():
    # Nullable → existing rows stay linear automations; behavior is unchanged until a
    # graph is saved (the compat shim renders linear steps as a doc without storing it).
    op.add_column('automations', sa.Column('graph', sa.JSON(), nullable=True))
    op.add_column('automations', sa.Column('webhook_token', sa.String(), nullable=True))
    op.create_index('ix_automations_webhook_token', 'automations', ['webhook_token'],
                    unique=True)
    op.add_column('automation_runs',
                  sa.Column('kind', sa.String(), nullable=True, server_default='linear'))
    op.add_column('automation_runs', sa.Column('trigger', sa.JSON(), nullable=True))


def downgrade():
    op.drop_column('automation_runs', 'trigger')
    op.drop_column('automation_runs', 'kind')
    op.drop_index('ix_automations_webhook_token', table_name='automations')
    op.drop_column('automations', 'webhook_token')
    op.drop_column('automations', 'graph')
