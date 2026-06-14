"""add goal status and future commitments

Revision ID: 009_add_goal_status_and_future_commitments
Revises: 008_add_personal_cfo_phase3_tables
Create Date: 2026-06-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "009_add_goal_status_and_future_commitments"
down_revision = "008_add_personal_cfo_phase3_tables"
branch_labels = None
depends_on = None


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    goal_columns = _columns("goals")

    with op.batch_alter_table("goals") as batch_op:
        if "status" not in goal_columns:
            batch_op.add_column(sa.Column("status", sa.String(), nullable=False, server_default="active"))
        if "is_active" not in goal_columns:
            batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        if "notes_json" not in goal_columns:
            batch_op.add_column(sa.Column("notes_json", sa.JSON(), nullable=True))
        if "created_at" not in goal_columns:
            batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()))
        if "updated_at" not in goal_columns:
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()))

    if "status" not in goal_columns:
        op.create_index("ix_goals_status", "goals", ["status"])
    if "is_active" not in goal_columns:
        op.create_index("ix_goals_is_active", "goals", ["is_active"])

    if not inspector.has_table("future_commitments"):
        op.create_table(
            "future_commitments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("amount", sa.BigInteger(), nullable=False),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("due_month", sa.String(), nullable=True),
            sa.Column("category_id", sa.Integer(), nullable=True),
            sa.Column("related_transaction_id", sa.Integer(), nullable=True),
            sa.Column("related_goal_id", sa.Integer(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(), nullable=False, server_default="pending"),
            sa.Column("source", sa.String(), nullable=False, server_default="chat"),
            sa.Column("metadata_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
            sa.ForeignKeyConstraint(["related_goal_id"], ["goals.id"]),
            sa.ForeignKeyConstraint(["related_transaction_id"], ["transactions.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_future_commitments_id", "future_commitments", ["id"])
        op.create_index("ix_future_commitments_user_id", "future_commitments", ["user_id"])
        op.create_index("ix_future_commitments_due_date", "future_commitments", ["due_date"])
        op.create_index("ix_future_commitments_due_month", "future_commitments", ["due_month"])
        op.create_index("ix_future_commitments_status", "future_commitments", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("future_commitments"):
        op.drop_index("ix_future_commitments_status", table_name="future_commitments")
        op.drop_index("ix_future_commitments_due_month", table_name="future_commitments")
        op.drop_index("ix_future_commitments_due_date", table_name="future_commitments")
        op.drop_index("ix_future_commitments_user_id", table_name="future_commitments")
        op.drop_index("ix_future_commitments_id", table_name="future_commitments")
        op.drop_table("future_commitments")

    goal_columns = _columns("goals")
    if "is_active" in goal_columns:
        op.drop_index("ix_goals_is_active", table_name="goals")
    if "status" in goal_columns:
        op.drop_index("ix_goals_status", table_name="goals")
    with op.batch_alter_table("goals") as batch_op:
        for column in ("updated_at", "created_at", "notes_json", "is_active", "status"):
            if column in goal_columns:
                batch_op.drop_column(column)
