"""add user monthly_income field

Revision ID: 005add_user_monthly_income
Revises: 004add_user_chat_mode
Create Date: 2026-05-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "005add_user_monthly_income"
down_revision: Union[str, Sequence[str], None] = "004add_user_chat_mode"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("monthly_income", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "monthly_income")
