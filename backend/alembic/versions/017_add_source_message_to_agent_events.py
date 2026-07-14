"""add source_message_id to agent_operation_events for deterministic chat rollback

Revision ID: 017_add_source_msg_to_events
Revises: 016_add_transaction_chat_provenance
Create Date: 2026-07-14 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "017_add_source_msg_to_events"
down_revision = "016_add_transaction_chat_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("agent_operation_events"):
        return

    columns = {col["name"] for col in inspector.get_columns("agent_operation_events")}
    if "source_message_id" not in columns:
        with op.batch_alter_table("agent_operation_events") as batch_op:
            batch_op.add_column(
                sa.Column("source_message_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_agent_op_events_source_message_id",
                "chat_messages",
                ["source_message_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_agent_op_events_source_message_id",
            "agent_operation_events",
            ["source_message_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("agent_operation_events"):
        return

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("agent_operation_events")}
    if "ix_agent_op_events_source_message_id" in existing_indexes:
        op.drop_index(
            "ix_agent_op_events_source_message_id",
            table_name="agent_operation_events",
        )

    columns = {col["name"] for col in inspector.get_columns("agent_operation_events")}
    if "source_message_id" in columns:
        with op.batch_alter_table("agent_operation_events") as batch_op:
            try:
                batch_op.drop_constraint(
                    "fk_agent_op_events_source_message_id", type_="foreignkey"
                )
            except Exception:
                pass
            batch_op.drop_column("source_message_id")
