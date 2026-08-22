"""market data: instrument_master + candle tables (+ TimescaleDB hypertables)

Revision ID: 0002_market_data
Revises: 0001_initial
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_market_data"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _candle_columns() -> list[sa.Column]:
    return [
        sa.Column("instrument_id", sa.String(50), primary_key=True),
        sa.Column("interval", sa.String(5), primary_key=True),
        sa.Column("time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("oi", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "instrument_master",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("security_id", sa.String(50), nullable=False, index=True),
        sa.Column("exchange", sa.String(10), nullable=False),
        sa.Column("segment", sa.String(20), nullable=False, index=True),
        sa.Column("exchange_segment", sa.String(20), nullable=True),
        sa.Column("symbol", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=True),
        sa.Column("underlying", sa.String(100), nullable=True, index=True),
        sa.Column("instrument_type", sa.String(20), nullable=True),
        sa.Column("expiry_code", sa.Integer(), nullable=True),
        sa.Column("expiry", sa.Date(), nullable=True, index=True),
        sa.Column("strike", sa.Float(), nullable=True),
        sa.Column("option_type", sa.String(4), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tick_size", sa.Float(), nullable=False, server_default="0.05"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("exchange", "segment", "security_id", name="uq_instrument_identity"),
    )

    for table_name in ("index_candles", "equity_candles", "futures_candles", "options_candles"):
        op.create_table(table_name, *_candle_columns())

    # TimescaleDB hypertables (only when the extension is present)
    if op.get_bind().dialect.name == "postgresql":
        for table_name in ("index_candles", "equity_candles", "futures_candles", "options_candles"):
            op.execute(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                        PERFORM create_hypertable(
                            '{table_name}', 'time',
                            chunk_time_interval => INTERVAL '7 days',
                            if_not_exists => TRUE
                        );
                    END IF;
                END $$;
                """
            )


def downgrade() -> None:
    op.drop_table("options_candles")
    op.drop_table("futures_candles")
    op.drop_table("equity_candles")
    op.drop_table("index_candles")
    op.drop_table("instrument_master")
