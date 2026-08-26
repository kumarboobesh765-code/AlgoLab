"""optimization_runs.config JSON (initial capital for background executor)

Revision ID: 0005_run_config
Revises: 0004_optimization
Create Date: 2026-08-26
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_run_config"
down_revision: str = "0004_optimization"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "optimization_runs",
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("optimization_runs", "config")
