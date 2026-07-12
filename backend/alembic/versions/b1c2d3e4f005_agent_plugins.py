"""agent-plugin manifest contract (plan 25 part 5)

Revision ID: b1c2d3e4f005
Revises: a0b1c2d3e004
Create Date: 2026-07-12 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f005'
down_revision = 'a0b1c2d3e004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agent_plugins',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('manifest', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.Column('workspace_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_plugins_name', 'agent_plugins', ['name'], unique=True)
    op.create_index('ix_agent_plugins_workspace_id', 'agent_plugins', ['workspace_id'])


def downgrade():
    op.drop_index('ix_agent_plugins_workspace_id', table_name='agent_plugins')
    op.drop_index('ix_agent_plugins_name', table_name='agent_plugins')
    op.drop_table('agent_plugins')
