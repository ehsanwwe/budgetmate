"""add current_financial_status to users

Revision ID: 013_add_current_financial_status
Revises: 012_add_translation_entries
Create Date: 2026-06-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "013_add_current_financial_status"
down_revision = "012_add_translation_entries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("current_financial_status", sa.String(), nullable=True, server_default=None)
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("current_financial_status")
