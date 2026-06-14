"""add personal cfo phase3 tables

Revision ID: 008_add_personal_cfo_phase3_tables
Revises: 007_add_personal_cfo_foundation
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa


revision = "008_add_personal_cfo_phase3_tables"
down_revision = "007_add_personal_cfo_foundation"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return {row[0] for row in bind.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)

    if "financial_facts" not in tables:
        op.create_table(
            "financial_facts",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("fact_type", sa.String(), nullable=False),
            sa.Column("subject", sa.String(), nullable=False),
            sa.Column("value_json", sa.JSON(), nullable=False),
            sa.Column("source_message_id", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
            sa.Column("valid_from", sa.Date(), nullable=True),
            sa.Column("valid_to", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.ForeignKeyConstraint(["source_message_id"], ["chat_messages.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_financial_facts_id"), "financial_facts", ["id"], unique=False)
        op.create_index(op.f("ix_financial_facts_user_id"), "financial_facts", ["user_id"], unique=False)
        op.create_index(op.f("ix_financial_facts_fact_type"), "financial_facts", ["fact_type"], unique=False)
        op.create_index(op.f("ix_financial_facts_is_active"), "financial_facts", ["is_active"], unique=False)

    if "financial_warnings" not in tables:
        op.create_table(
            "financial_warnings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("warning_type", sa.String(), nullable=False),
            sa.Column("severity", sa.String(), nullable=False, server_default="info"),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("evidence_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_financial_warnings_id"), "financial_warnings", ["id"], unique=False)
        op.create_index(op.f("ix_financial_warnings_user_id"), "financial_warnings", ["user_id"], unique=False)
        op.create_index(op.f("ix_financial_warnings_warning_type"), "financial_warnings", ["warning_type"], unique=False)
        op.create_index(op.f("ix_financial_warnings_status"), "financial_warnings", ["status"], unique=False)

    if "financial_decision_logs" not in tables:
        op.create_table(
            "financial_decision_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("decision_title", sa.String(), nullable=False),
            sa.Column("decision_type", sa.String(), nullable=False),
            sa.Column("input_json", sa.JSON(), nullable=False),
            sa.Column("analysis_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_financial_decision_logs_id"), "financial_decision_logs", ["id"], unique=False)
        op.create_index(op.f("ix_financial_decision_logs_user_id"), "financial_decision_logs", ["user_id"], unique=False)
        op.create_index(op.f("ix_financial_decision_logs_decision_type"), "financial_decision_logs", ["decision_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_financial_decision_logs_decision_type"), table_name="financial_decision_logs")
    op.drop_index(op.f("ix_financial_decision_logs_user_id"), table_name="financial_decision_logs")
    op.drop_index(op.f("ix_financial_decision_logs_id"), table_name="financial_decision_logs")
    op.drop_table("financial_decision_logs")
    op.drop_index(op.f("ix_financial_warnings_status"), table_name="financial_warnings")
    op.drop_index(op.f("ix_financial_warnings_warning_type"), table_name="financial_warnings")
    op.drop_index(op.f("ix_financial_warnings_user_id"), table_name="financial_warnings")
    op.drop_index(op.f("ix_financial_warnings_id"), table_name="financial_warnings")
    op.drop_table("financial_warnings")
    op.drop_index(op.f("ix_financial_facts_is_active"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_fact_type"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_user_id"), table_name="financial_facts")
    op.drop_index(op.f("ix_financial_facts_id"), table_name="financial_facts")
    op.drop_table("financial_facts")
