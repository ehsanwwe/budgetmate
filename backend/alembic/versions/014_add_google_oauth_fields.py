"""add Google OAuth fields to users

Revision ID: 014_add_google_oauth_fields
Revises: 013_add_current_financial_status
Create Date: 2026-06-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "014_add_google_oauth_fields"
down_revision = "013_add_current_financial_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("phone", existing_type=sa.String(), nullable=True)
        batch_op.add_column(sa.Column("email", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column("auth_provider", sa.String(), nullable=False, server_default="local")
        )
        batch_op.add_column(sa.Column("google_sub", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("avatar_url", sa.String(), nullable=True))
        batch_op.create_unique_constraint("uq_users_email", ["email"])
        batch_op.create_unique_constraint("uq_users_google_sub", ["google_sub"])
        batch_op.create_index("ix_users_email", ["email"], unique=False)
        batch_op.create_index("ix_users_google_sub", ["google_sub"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_google_sub")
        batch_op.drop_index("ix_users_email")
        batch_op.drop_constraint("uq_users_google_sub", type_="unique")
        batch_op.drop_constraint("uq_users_email", type_="unique")
        batch_op.drop_column("avatar_url")
        batch_op.drop_column("google_sub")
        batch_op.drop_column("auth_provider")
        batch_op.drop_column("email")
        batch_op.alter_column("phone", existing_type=sa.String(), nullable=False)
