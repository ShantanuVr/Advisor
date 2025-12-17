"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Snapshots table
    op.create_table(
        'snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('timeframe', sa.String(5), nullable=False),
        sa.Column('captured_at', sa.DateTime(), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_snapshots_id', 'snapshots', ['id'])
    op.create_index('ix_snapshots_symbol', 'snapshots', ['symbol'])

    # Economic events table
    op.create_table(
        'economic_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_time_utc', sa.DateTime(), nullable=False),
        sa.Column('currency', sa.String(5), nullable=False),
        sa.Column('impact', sa.String(10), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('forecast', sa.String(100), nullable=True),
        sa.Column('previous', sa.String(100), nullable=True),
        sa.Column('actual', sa.String(100), nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_economic_events_id', 'economic_events', ['id'])
    op.create_index('ix_economic_events_event_time_utc', 'economic_events', ['event_time_utc'])
    op.create_index('ix_economic_events_currency', 'economic_events', ['currency'])

    # News items table
    op.create_table(
        'news_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(100), nullable=False),
        sa.Column('title', sa.String(1000), nullable=False),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('stance', sa.String(20), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('url')
    )
    op.create_index('ix_news_items_id', 'news_items', ['id'])
    op.create_index('ix_news_items_published_at', 'news_items', ['published_at'])

    # TA signals table
    op.create_table(
        'ta_signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('timeframe', sa.String(5), nullable=True),
        sa.Column('bias', sa.String(20), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('levels_json', sa.JSON(), nullable=True),
        sa.Column('ict_notes', sa.Text(), nullable=True),
        sa.Column('turtle_soup_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_ta_signals_id', 'ta_signals', ['id'])
    op.create_index('ix_ta_signals_date', 'ta_signals', ['date'])
    op.create_index('ix_ta_signals_symbol', 'ta_signals', ['symbol'])

    # Daily reports table
    op.create_table(
        'daily_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('symbol', sa.String(10), nullable=False),
        sa.Column('report_json', sa.JSON(), nullable=False),
        sa.Column('primary_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['primary_snapshot_id'], ['snapshots.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_daily_reports_id', 'daily_reports', ['id'])
    op.create_index('ix_daily_reports_date', 'daily_reports', ['date'])
    op.create_index('ix_daily_reports_symbol', 'daily_reports', ['symbol'])


def downgrade() -> None:
    op.drop_table('daily_reports')
    op.drop_table('ta_signals')
    op.drop_table('news_items')
    op.drop_table('economic_events')
    op.drop_table('snapshots')
