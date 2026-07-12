"""workspaces, membership, grants + born-in-workspace columns (plan 20 part 4)

Revision ID: f3a4b5c6d001
Revises: e2f3a4b5c001
Create Date: 2026-07-11 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a4b5c6d001'
down_revision = 'e2f3a4b5c001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workspaces',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='active'),
        sa.Column('max_devices', sa.Integer(), nullable=True),
        sa.Column('max_members', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_workspaces_slug', 'workspaces', ['slug'], unique=True)

    op.create_table(
        'workspace_members',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'user_id', name='uq_workspace_member'),
    )
    op.create_index('ix_workspace_members_workspace_id', 'workspace_members', ['workspace_id'])
    op.create_index('ix_workspace_members_user_id', 'workspace_members', ['user_id'])

    op.create_table(
        'resource_grants',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=False),
        sa.Column('resource_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('level', sa.String(), nullable=False, server_default='viewer'),
        sa.Column('granted_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('resource_type', 'resource_id', 'user_id', name='uq_resource_grant'),
    )
    op.create_index('ix_resource_grants_resource_type', 'resource_grants', ['resource_type'])
    op.create_index('ix_resource_grants_resource_id', 'resource_grants', ['resource_id'])
    op.create_index('ix_resource_grants_user_id', 'resource_grants', ['user_id'])

    # Born-in-workspace columns on existing tables. Nullable → existing rows are global (unscoped),
    # so behavior is unchanged until a resource is assigned to a workspace.
    op.add_column('agent_devices', sa.Column('workspace_id', sa.String(), nullable=True))
    op.add_column('automations', sa.Column('workspace_id', sa.String(), nullable=True))
    op.add_column('saved_queries', sa.Column('workspace_id', sa.String(), nullable=True))
    op.create_index('ix_agent_devices_workspace_id', 'agent_devices', ['workspace_id'])
    op.create_index('ix_automations_workspace_id', 'automations', ['workspace_id'])
    op.create_index('ix_saved_queries_workspace_id', 'saved_queries', ['workspace_id'])


def downgrade():
    op.drop_index('ix_saved_queries_workspace_id', table_name='saved_queries')
    op.drop_index('ix_automations_workspace_id', table_name='automations')
    op.drop_index('ix_agent_devices_workspace_id', table_name='agent_devices')
    op.drop_column('saved_queries', 'workspace_id')
    op.drop_column('automations', 'workspace_id')
    op.drop_column('agent_devices', 'workspace_id')
    op.drop_index('ix_resource_grants_user_id', table_name='resource_grants')
    op.drop_index('ix_resource_grants_resource_id', table_name='resource_grants')
    op.drop_index('ix_resource_grants_resource_type', table_name='resource_grants')
    op.drop_table('resource_grants')
    op.drop_index('ix_workspace_members_user_id', table_name='workspace_members')
    op.drop_index('ix_workspace_members_workspace_id', table_name='workspace_members')
    op.drop_table('workspace_members')
    op.drop_index('ix_workspaces_slug', table_name='workspaces')
    op.drop_table('workspaces')
