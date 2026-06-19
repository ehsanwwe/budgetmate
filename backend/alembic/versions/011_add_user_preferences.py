"""add user preferred_currency

Revision ID: 011_add_user_preferences
Revises: 010_add_agent_idempotency_and_pending_intents
Create Date: 2026-06-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "011_add_user_preferences"
down_revision = "010_add_agent_idempotency_and_pending_intents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("preferred_currency", sa.String(), nullable=True, server_default="IRT"))


def downgrade() -> None:
    op.drop_column("users", "preferred_currency")
