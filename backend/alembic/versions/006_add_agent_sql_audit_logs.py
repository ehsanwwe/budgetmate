"""add agent sql audit logs

Revision ID: 006add_agent_sql_audit_logs
Revises: 005add_user_monthly_income
Create Date: 2026-06-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006add_agent_sql_audit_logs"
down_revision: Union[str, Sequence[str], None] = "005add_user_monthly_income"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_sql_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("intent", sa.String(), nullable=True),
        sa.Column("operation_type", sa.String(), nullable=False),
        sa.Column("table_name", sa.String(), nullable=True),
        sa.Column("planned_sql", sa.Text(), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("validation_status", sa.String(), nullable=False),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("executed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("result_summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_sql_audit_logs_id"), "agent_sql_audit_logs", ["id"], unique=False)
    op.create_index(op.f("ix_agent_sql_audit_logs_user_id"), "agent_sql_audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_agent_sql_audit_logs_user_id"), table_name="agent_sql_audit_logs")
    op.drop_index(op.f("ix_agent_sql_audit_logs_id"), table_name="agent_sql_audit_logs")
    op.drop_table("agent_sql_audit_logs")
