"""jobs, queue bus & scheduler (plan 05)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-10 02:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # ---- Queue Bus ------------------------------------------------------
    op.create_table(
        'queue_groups',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('owner_type', sa.String(length=32), nullable=False),
        sa.Column('owner_id', sa.String(length=128), nullable=True),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_queue_groups_slug', 'queue_groups', ['slug'], unique=True)

    op.create_table(
        'queues',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('group_id', sa.String(length=36), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['queue_groups.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'slug', name='uix_queue_group_slug'),
    )
    op.create_index('ix_queues_group_id', 'queues', ['group_id'], unique=False)
    op.create_index('ix_queues_slug', 'queues', ['slug'], unique=False)

    op.create_table(
        'queue_messages',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('queue_id', sa.String(length=36), nullable=False),
        sa.Column('group_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('visible_after', sa.DateTime(), nullable=False),
        sa.Column('invisible_until', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['group_id'], ['queue_groups.id'], ),
        sa.ForeignKeyConstraint(['queue_id'], ['queues.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_queue_messages_queue_id', 'queue_messages', ['queue_id'], unique=False)
    op.create_index('ix_queue_messages_group_id', 'queue_messages', ['group_id'], unique=False)
    op.create_index('ix_queue_messages_status', 'queue_messages', ['status'], unique=False)
    op.create_index('ix_queue_messages_priority', 'queue_messages', ['priority'], unique=False)
    op.create_index('ix_queue_messages_visible_after', 'queue_messages', ['visible_after'], unique=False)
    op.create_index('ix_queue_messages_invisible_until', 'queue_messages', ['invisible_until'], unique=False)
    op.create_index('ix_queue_messages_created_at', 'queue_messages', ['created_at'], unique=False)

    # ---- Jobs -----------------------------------------------------------
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('owner_type', sa.String(length=40), nullable=True),
        sa.Column('owner_id', sa.String(length=64), nullable=True),
        sa.Column('scheduled_job_id', sa.Integer(), nullable=True),
        sa.Column('correlation_id', sa.String(length=64), nullable=True),
        sa.Column('queue_message_id', sa.String(length=36), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_jobs_kind', 'jobs', ['kind'], unique=False)
    op.create_index('ix_jobs_status', 'jobs', ['status'], unique=False)
    op.create_index('ix_jobs_owner_type', 'jobs', ['owner_type'], unique=False)
    op.create_index('ix_jobs_owner_id', 'jobs', ['owner_id'], unique=False)
    op.create_index('ix_jobs_scheduled_job_id', 'jobs', ['scheduled_job_id'], unique=False)
    op.create_index('ix_jobs_correlation_id', 'jobs', ['correlation_id'], unique=False)
    op.create_index('ix_jobs_created_at', 'jobs', ['created_at'], unique=False)

    op.create_table(
        'scheduled_jobs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('kind', sa.String(length=80), nullable=False),
        sa.Column('schedule_kind', sa.String(length=20), nullable=False),
        sa.Column('interval_seconds', sa.Integer(), nullable=True),
        sa.Column('cron', sa.String(length=120), nullable=True),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('owner_type', sa.String(length=40), nullable=True),
        sa.Column('owner_id', sa.String(length=64), nullable=True),
        sa.Column('next_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_job_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index('ix_scheduled_jobs_owner_type', 'scheduled_jobs', ['owner_type'], unique=False)
    op.create_index('ix_scheduled_jobs_owner_id', 'scheduled_jobs', ['owner_id'], unique=False)
    op.create_index('ix_scheduled_jobs_next_run_at', 'scheduled_jobs', ['next_run_at'], unique=False)


def downgrade():
    op.drop_table('scheduled_jobs')
    op.drop_table('jobs')
    op.drop_table('queue_messages')
    op.drop_table('queues')
    op.drop_table('queue_groups')
