"""metrics history — raw/hourly/daily tiers + threshold alert rules (plan 08)

Revision ID: a8d1c07f80001
Revises: a71c07a40004
Create Date: 2026-07-10 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8d1c07f80001'
down_revision = 'a71c07a40004'
branch_labels = None
depends_on = None


def _sample_columns():
    return [
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('ts', sa.Float(), nullable=False),
        sa.Column('battery_pct', sa.Float(), nullable=True),
        sa.Column('battery_temp', sa.Float(), nullable=True),
        sa.Column('cpu_load', sa.Float(), nullable=True),
        sa.Column('mem_free', sa.Float(), nullable=True),
        sa.Column('storage_free', sa.Float(), nullable=True),
        sa.Column('network_type', sa.String(), nullable=True),
        sa.Column('screen_on', sa.Boolean(), nullable=True),
        sa.Column('extra', sa.JSON(), nullable=True),
    ]


def upgrade():
    # --- raw tier ---
    op.create_table(
        'device_metrics_raw',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        *_sample_columns(),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_metrics_raw_device_id', 'device_metrics_raw',
                    ['device_id'], unique=False)
    op.create_index('ix_device_metrics_raw_ts', 'device_metrics_raw', ['ts'], unique=False)
    op.create_index('ix_device_metrics_raw_device_ts', 'device_metrics_raw',
                    ['device_id', 'ts'], unique=False)

    # --- hourly tier ---
    op.create_table(
        'device_metrics_hourly',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        *_sample_columns(),
        sa.Column('samples', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_metrics_hourly_device_id', 'device_metrics_hourly',
                    ['device_id'], unique=False)
    op.create_index('ix_device_metrics_hourly_ts', 'device_metrics_hourly', ['ts'], unique=False)
    op.create_index('ix_device_metrics_hourly_device_ts', 'device_metrics_hourly',
                    ['device_id', 'ts'], unique=True)

    # --- daily tier ---
    op.create_table(
        'device_metrics_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        *_sample_columns(),
        sa.Column('samples', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_device_metrics_daily_device_id', 'device_metrics_daily',
                    ['device_id'], unique=False)
    op.create_index('ix_device_metrics_daily_ts', 'device_metrics_daily', ['ts'], unique=False)
    op.create_index('ix_device_metrics_daily_device_ts', 'device_metrics_daily',
                    ['device_id', 'ts'], unique=True)

    # --- threshold alert rules ---
    op.create_table(
        'metric_alert_rules',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('metric', sa.String(), nullable=False),
        sa.Column('op', sa.String(), nullable=False),
        sa.Column('value', sa.Float(), nullable=False),
        sa.Column('event_key', sa.String(), nullable=False),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('device_id', sa.String(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('cooldown_seconds', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_metric_alert_rules_device_id', 'metric_alert_rules',
                    ['device_id'], unique=False)


def downgrade():
    op.drop_table('metric_alert_rules')
    op.drop_table('device_metrics_daily')
    op.drop_table('device_metrics_hourly')
    op.drop_table('device_metrics_raw')
