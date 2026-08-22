"""forward testing: paper_orders, paper_positions, forward_test_runs

Revision ID: 0003_forward_testing
Revises: 0002_market_data
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_forward_testing"
down_revision: str = "0002_market_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_positions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("entry_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stop_price", sa.Numeric(18, 4)),
        sa.Column("target_price", sa.Numeric(18, 4)),
        sa.Column("trail_pct", sa.Numeric(7, 3)),
        sa.Column("trailed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extreme", sa.Numeric(18, 4)),
        sa.Column("status", sa.String(10), nullable=False, server_default="open", index=True),
        sa.Column("exit_price", sa.Numeric(18, 4)),
        sa.Column("exit_time", sa.DateTime(timezone=True)),
        sa.Column("exit_reason", sa.String(20)),
        sa.Column("realized_pnl", sa.Numeric(18, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "paper_orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id", ondelete="SET NULL"),
            index=True,
        ),
        sa.Column("position_id", sa.Uuid()),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("filled_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("signal_time", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "forward_test_runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
        ),
        sa.Column(
            "strategy_id",
            sa.Uuid(),
            sa.ForeignKey("strategies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("paper_accounts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running", index=True),
        sa.Column("last_bar_time", sa.DateTime(timezone=True)),
        sa.Column("pending_action", sa.String(12)),
        sa.Column("last_message", sa.String(500)),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("forward_test_runs")
    op.drop_table("paper_orders")
    op.drop_table("paper_positions")
