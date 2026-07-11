"""add source_message_id chat provenance to transactions and future_commitments

Revision ID: 016_add_transaction_chat_provenance
Revises: 015_financial_status_array
Create Date: 2026-07-11 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "016_add_transaction_chat_provenance"
down_revision = "015_financial_status_array"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tx_columns = {col["name"] for col in inspector.get_columns("transactions")}
    if "source_message_id" not in tx_columns:
        with op.batch_alter_table("transactions") as batch_op:
            batch_op.add_column(
                sa.Column("source_message_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_transactions_source_message_id",
                "chat_messages",
                ["source_message_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_transactions_source_message_id",
            "transactions",
            ["source_message_id"],
        )

    fc_columns = {col["name"] for col in inspector.get_columns("future_commitments")}
    if "source_message_id" not in fc_columns:
        with op.batch_alter_table("future_commitments") as batch_op:
            batch_op.add_column(
                sa.Column("source_message_id", sa.Integer(), nullable=True)
            )
            batch_op.create_foreign_key(
                "fk_future_commitments_source_message_id",
                "chat_messages",
                ["source_message_id"],
                ["id"],
                ondelete="SET NULL",
            )
        op.create_index(
            "ix_future_commitments_source_message_id",
            "future_commitments",
            ["source_message_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "ix_future_commitments_source_message_id" in {
        idx["name"] for idx in inspector.get_indexes("future_commitments")
    }:
        op.drop_index(
            "ix_future_commitments_source_message_id",
            table_name="future_commitments",
        )
    fc_columns = {col["name"] for col in inspector.get_columns("future_commitments")}
    if "source_message_id" in fc_columns:
        with op.batch_alter_table("future_commitments") as batch_op:
            batch_op.drop_constraint(
                "fk_future_commitments_source_message_id", type_="foreignkey"
            )
            batch_op.drop_column("source_message_id")

    if "ix_transactions_source_message_id" in {
        idx["name"] for idx in inspector.get_indexes("transactions")
    }:
        op.drop_index(
            "ix_transactions_source_message_id",
            table_name="transactions",
        )
    tx_columns = {col["name"] for col in inspector.get_columns("transactions")}
    if "source_message_id" in tx_columns:
        with op.batch_alter_table("transactions") as batch_op:
            batch_op.drop_constraint(
                "fk_transactions_source_message_id", type_="foreignkey"
            )
            batch_op.drop_column("source_message_id")
