"""webhook_endpoints and webhook_deliveries tables

Revision ID: 0005_webhooks
Revises: 0004_optimization
Create Date: 2026-08-25
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_webhooks"
down_revision: str | None = "0005_run_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("strategy_id", sa.String(36), sa.ForeignKey("strategies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("secret", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("endpoint_id", sa.String(36), sa.ForeignKey("webhook_endpoints.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("action", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("forward_test_id", sa.String(36), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
