"""add profile fields and billing tables

Revision ID: 002add_profile_billing
Revises: 81c0d46884bb
Create Date: 2026-05-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002add_profile_billing"
down_revision: Union[str, Sequence[str], None] = "81c0d46884bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Add first_name/last_name to users if not present (SQLite-safe)
    existing_cols = {row[1] for row in bind.execute(sa.text("PRAGMA table_info(users)"))}
    if "first_name" not in existing_cols:
        op.add_column("users", sa.Column("first_name", sa.String(), nullable=True))
    if "last_name" not in existing_cols:
        op.add_column("users", sa.Column("last_name", sa.String(), nullable=True))

    tables = {row[0] for row in bind.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}

    if "token_wallets" not in tables:
        op.create_table(
            "token_wallets",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, unique=True, index=True),
            sa.Column("balance_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("total_granted_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("total_purchased_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("total_consumed_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if "token_usage_logs" not in tables:
        op.create_table(
            "token_usage_logs",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("chat_message_id", sa.Integer(), sa.ForeignKey("chat_messages.id"), nullable=True),
            sa.Column("provider", sa.String(), nullable=True),
            sa.Column("model", sa.String(), nullable=True),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("completion_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("total_tokens", sa.Integer(), nullable=False, default=0),
            sa.Column("balance_before", sa.Integer(), nullable=False, default=0),
            sa.Column("balance_after", sa.Integer(), nullable=False, default=0),
            sa.Column("reason", sa.String(), nullable=False, default="chat"),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if "token_purchases" not in tables:
        op.create_table(
            "token_purchases",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("kind", sa.String(), nullable=False),
            sa.Column("plan_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("amount_toman", sa.BigInteger(), nullable=False),
            sa.Column("tokens_added", sa.Integer(), nullable=False, default=0),
            sa.Column("status", sa.String(), nullable=False, default="mock_paid"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
        )

    if "user_subscriptions" not in tables:
        op.create_table(
            "user_subscriptions",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("plan_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, default="active"),
            sa.Column("starts_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("monthly_token_quota", sa.Integer(), nullable=False, default=0),
            sa.Column("tokens_granted", sa.Integer(), nullable=False, default=0),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade() -> None:
    op.drop_table("user_subscriptions")
    op.drop_table("token_purchases")
    op.drop_table("token_usage_logs")
    op.drop_table("token_wallets")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
