"""add user chat mode

Revision ID: 004add_user_chat_mode
Revises: 003extend_user_onboarding
Create Date: 2026-05-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "004add_user_chat_mode"
down_revision: Union[str, Sequence[str], None] = "003extend_user_onboarding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_cols = {row[1] for row in bind.execute(sa.text("PRAGMA table_info(users)"))}
    if "chat_mode" not in existing_cols:
        op.add_column("users", sa.Column("chat_mode", sa.String(), nullable=True))
    bind.execute(sa.text("UPDATE users SET chat_mode = 'normal' WHERE chat_mode IS NULL"))


def downgrade() -> None:
    pass
