"""notification preferences + recipient settings (plan 06.3)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-10 06:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notification_preferences',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('recipient', sa.String(length=80), nullable=True),
        sa.Column('event_key', sa.String(length=100), nullable=False),
        sa.Column('channel', sa.String(length=30), nullable=True),
        sa.Column('muted', sa.Boolean(), nullable=True),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recipient', 'event_key', 'channel', name='uix_notif_pref'),
    )
    op.create_index('ix_notification_preferences_recipient', 'notification_preferences',
                    ['recipient'], unique=False)
    op.create_index('ix_notification_preferences_event_key', 'notification_preferences',
                    ['event_key'], unique=False)

    op.create_table(
        'notification_recipient_settings',
        sa.Column('recipient', sa.String(length=80), nullable=False),
        sa.Column('quiet_hours_enabled', sa.Boolean(), nullable=True),
        sa.Column('quiet_start', sa.Integer(), nullable=True),
        sa.Column('quiet_end', sa.Integer(), nullable=True),
        sa.Column('quiet_allow_critical', sa.Boolean(), nullable=True),
        sa.Column('digest_enabled', sa.Boolean(), nullable=True),
        sa.Column('digest_window_minutes', sa.Integer(), nullable=True),
        sa.Column('digest_events', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('recipient'),
    )


def downgrade():
    op.drop_table('notification_recipient_settings')
    op.drop_table('notification_preferences')
