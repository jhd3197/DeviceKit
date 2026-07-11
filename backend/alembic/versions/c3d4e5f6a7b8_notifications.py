"""notification bus — notifications + deliveries (plan 06.1)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-10 04:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('event_key', sa.String(length=100), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('severity', sa.String(length=20), nullable=True),
        sa.Column('category', sa.String(length=40), nullable=True),
        sa.Column('deep_link', sa.String(length=500), nullable=True),
        sa.Column('subject_type', sa.String(length=40), nullable=True),
        sa.Column('subject_id', sa.String(length=128), nullable=True),
        sa.Column('recipient', sa.String(length=80), nullable=True),
        sa.Column('data', sa.JSON(), nullable=True),
        sa.Column('read', sa.Boolean(), nullable=True),
        sa.Column('read_at', sa.Float(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notifications_event_key', 'notifications', ['event_key'], unique=False)
    op.create_index('ix_notifications_severity', 'notifications', ['severity'], unique=False)
    op.create_index('ix_notifications_subject_id', 'notifications', ['subject_id'], unique=False)
    op.create_index('ix_notifications_recipient', 'notifications', ['recipient'], unique=False)
    op.create_index('ix_notifications_read', 'notifications', ['read'], unique=False)
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'], unique=False)
    op.create_index('ix_notifications_recipient_read', 'notifications', ['recipient', 'read'], unique=False)

    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('notification_id', sa.String(length=36), nullable=False),
        sa.Column('channel', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('target', sa.String(length=500), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('job_id', sa.String(length=36), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=True),
        sa.Column('sent_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notification_deliveries_notification_id', 'notification_deliveries',
                    ['notification_id'], unique=False)
    op.create_index('ix_notification_deliveries_channel', 'notification_deliveries',
                    ['channel'], unique=False)
    op.create_index('ix_notification_deliveries_status', 'notification_deliveries',
                    ['status'], unique=False)


def downgrade():
    op.drop_table('notification_deliveries')
    op.drop_table('notifications')
