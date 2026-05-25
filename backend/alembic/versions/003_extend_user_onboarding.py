"""extend user onboarding fields

Revision ID: 003extend_user_onboarding
Revises: 002add_profile_billing
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003extend_user_onboarding"
down_revision: Union[str, Sequence[str], None] = "002add_profile_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing_cols = {row[1] for row in bind.execute(sa.text("PRAGMA table_info(users)"))}

    new_columns = [
        ("family_name", sa.String(), True),
        ("birthdate", sa.Date(), True),
        ("province", sa.String(), True),
        ("city", sa.String(), True),
        ("income_range", sa.String(), True),
        ("agreement_accepted_at", sa.DateTime(), True),
        ("agreement_version", sa.String(), True),
        ("onboarding_completed", sa.Boolean(), True),
        ("onboarding_completed_at", sa.DateTime(), True),
    ]

    for col_name, col_type, nullable in new_columns:
        if col_name not in existing_cols:
            op.add_column("users", sa.Column(col_name, col_type, nullable=nullable))

    # Set default False for onboarding_completed on existing rows
    bind.execute(sa.text("UPDATE users SET onboarding_completed = 0 WHERE onboarding_completed IS NULL"))


def downgrade() -> None:
    # SQLite doesn't support DROP COLUMN in older versions — skip for dev
    pass
