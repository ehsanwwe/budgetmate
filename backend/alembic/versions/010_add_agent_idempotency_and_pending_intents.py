"""add agent idempotency events and pending agent intents

Revision ID: 010_add_agent_idempotency_and_pending_intents
Revises: 009_add_goal_status_and_future_commitments
Create Date: 2026-06-14 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "010_add_agent_idempotency_and_pending_intents"
down_revision = "009_add_goal_status_and_future_commitments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("agent_operation_events"):
        op.create_table(
            "agent_operation_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("operation_fingerprint", sa.String(64), nullable=False),
            sa.Column("operation_type", sa.String(20), nullable=False),
            sa.Column("table_name", sa.String(80), nullable=False),
            sa.Column("target_record_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="executed"),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_op_events_id", "agent_operation_events", ["id"])
        op.create_index("ix_agent_op_events_user_id", "agent_operation_events", ["user_id"])
        op.create_index("ix_agent_op_events_fingerprint", "agent_operation_events", ["operation_fingerprint"])
        op.create_index("ix_agent_op_events_created_at", "agent_operation_events", ["created_at"])
        op.create_index(
            "ix_agent_op_events_user_fp",
            "agent_operation_events",
            ["user_id", "operation_fingerprint"],
        )

    if not inspector.has_table("pending_agent_intents"):
        op.create_table(
            "pending_agent_intents",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("intent_type", sa.String(80), nullable=False),
            sa.Column("payload_json", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("source_message_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("consumed_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["source_message_id"], ["chat_messages.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_pending_agent_intents_id", "pending_agent_intents", ["id"])
        op.create_index("ix_pending_agent_intents_user_id", "pending_agent_intents", ["user_id"])
        op.create_index("ix_pending_agent_intents_status", "pending_agent_intents", ["status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("pending_agent_intents"):
        op.drop_index("ix_pending_agent_intents_status", table_name="pending_agent_intents")
        op.drop_index("ix_pending_agent_intents_user_id", table_name="pending_agent_intents")
        op.drop_index("ix_pending_agent_intents_id", table_name="pending_agent_intents")
        op.drop_table("pending_agent_intents")

    if inspector.has_table("agent_operation_events"):
        op.drop_index("ix_agent_op_events_user_fp", table_name="agent_operation_events")
        op.drop_index("ix_agent_op_events_created_at", table_name="agent_operation_events")
        op.drop_index("ix_agent_op_events_fingerprint", table_name="agent_operation_events")
        op.drop_index("ix_agent_op_events_user_id", table_name="agent_operation_events")
        op.drop_index("ix_agent_op_events_id", table_name="agent_operation_events")
        op.drop_table("agent_operation_events")
