"""optimization: optimization_runs, optimization_results

Revision ID: 0004_optimization
Revises: 0003_forward_testing
Create Date: 2026-08-21
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_optimization"
down_revision: str = "0003_forward_testing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
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
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("param_ranges", sa.JSON(), nullable=False),
        sa.Column("start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("train_pct", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("target_metric", sa.String(30), nullable=False, server_default="sharpe_ratio"),
        sa.Column("costs_pct", sa.Float(), nullable=False, server_default="0.03"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending", index=True),
        sa.Column("total_combinations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_combinations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("best_params", sa.JSON()),
        sa.Column("best_metrics", sa.JSON()),
        sa.Column("error", sa.String(500)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "optimization_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "run_id",
            sa.Uuid(),
            sa.ForeignKey("optimization_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("rank", sa.Integer()),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("net_pnl", sa.Float()),
        sa.Column("return_pct", sa.Float()),
        sa.Column("win_rate", sa.Float()),
        sa.Column("profit_factor", sa.Float()),
        sa.Column("max_drawdown_pct", sa.Float()),
        sa.Column("sharpe_ratio", sa.Float()),
        sa.Column("total_trades", sa.Integer()),
        sa.Column("train_sharpe", sa.Float()),
        sa.Column("test_sharpe", sa.Float()),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("optimization_results")
    op.drop_table("optimization_runs")
