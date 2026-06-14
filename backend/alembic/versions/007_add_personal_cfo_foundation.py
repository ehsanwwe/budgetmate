"""add personal cfo foundation

Revision ID: 007_add_personal_cfo_foundation
Revises: 006add_agent_sql_audit_logs
Create Date: 2026-06-14
"""

from alembic import op
import sqlalchemy as sa


revision = "007_add_personal_cfo_foundation"
down_revision = "006add_agent_sql_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_personas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("financial_literacy_level", sa.String(), nullable=True),
        sa.Column("risk_tolerance", sa.String(), nullable=True),
        sa.Column("financial_anxiety_level", sa.String(), nullable=True),
        sa.Column("decision_style", sa.String(), nullable=True),
        sa.Column("time_horizon", sa.String(), nullable=True),
        sa.Column("debt_sensitivity", sa.String(), nullable=True),
        sa.Column("discipline_score", sa.Float(), nullable=True),
        sa.Column("saving_preference", sa.String(), nullable=True),
        sa.Column("emotional_spending_triggers_json", sa.JSON(), nullable=True),
        sa.Column("notes_json", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_financial_personas_id"), "financial_personas", ["id"], unique=False)
    op.create_index(op.f("ix_financial_personas_user_id"), "financial_personas", ["user_id"], unique=False)

    op.create_table(
        "financial_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("memory_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="chat"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_financial_memories_id"), "financial_memories", ["id"], unique=False)
    op.create_index(op.f("ix_financial_memories_user_id"), "financial_memories", ["user_id"], unique=False)
    op.create_index(op.f("ix_financial_memories_memory_type"), "financial_memories", ["memory_type"], unique=False)
    op.create_index(op.f("ix_financial_memories_is_active"), "financial_memories", ["is_active"], unique=False)

    op.create_table(
        "behavior_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("insight_type", sa.String(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("first_detected_at", sa.DateTime(), nullable=False),
        sa.Column("last_detected_at", sa.DateTime(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "insight_type", name="uq_behavior_insight_user_type"),
    )
    op.create_index(op.f("ix_behavior_insights_id"), "behavior_insights", ["id"], unique=False)
    op.create_index(op.f("ix_behavior_insights_user_id"), "behavior_insights", ["user_id"], unique=False)
    op.create_index(op.f("ix_behavior_insights_insight_type"), "behavior_insights", ["insight_type"], unique=False)
    op.create_index(op.f("ix_behavior_insights_is_active"), "behavior_insights", ["is_active"], unique=False)

    op.create_table(
        "persona_update_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("previous_json", sa.JSON(), nullable=True),
        sa.Column("new_json", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_persona_update_logs_id"), "persona_update_logs", ["id"], unique=False)
    op.create_index(op.f("ix_persona_update_logs_user_id"), "persona_update_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_persona_update_logs_user_id"), table_name="persona_update_logs")
    op.drop_index(op.f("ix_persona_update_logs_id"), table_name="persona_update_logs")
    op.drop_table("persona_update_logs")
    op.drop_index(op.f("ix_behavior_insights_is_active"), table_name="behavior_insights")
    op.drop_index(op.f("ix_behavior_insights_insight_type"), table_name="behavior_insights")
    op.drop_index(op.f("ix_behavior_insights_user_id"), table_name="behavior_insights")
    op.drop_index(op.f("ix_behavior_insights_id"), table_name="behavior_insights")
    op.drop_table("behavior_insights")
    op.drop_index(op.f("ix_financial_memories_is_active"), table_name="financial_memories")
    op.drop_index(op.f("ix_financial_memories_memory_type"), table_name="financial_memories")
    op.drop_index(op.f("ix_financial_memories_user_id"), table_name="financial_memories")
    op.drop_index(op.f("ix_financial_memories_id"), table_name="financial_memories")
    op.drop_table("financial_memories")
    op.drop_index(op.f("ix_financial_personas_user_id"), table_name="financial_personas")
    op.drop_index(op.f("ix_financial_personas_id"), table_name="financial_personas")
    op.drop_table("financial_personas")
