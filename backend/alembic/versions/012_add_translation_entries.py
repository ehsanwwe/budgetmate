"""add translation_entries table

Revision ID: 012_add_translation_entries
Revises: 011_add_user_preferences
Create Date: 2026-06-19 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "012_add_translation_entries"
down_revision = "011_add_user_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "translation_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("locale", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("locale", "namespace", "key", name="uq_translation_locale_ns_key"),
    )
    op.create_index(op.f("ix_translation_entries_id"), "translation_entries", ["id"])
    op.create_index(op.f("ix_translation_entries_locale"), "translation_entries", ["locale"])
    op.create_index(op.f("ix_translation_entries_namespace"), "translation_entries", ["namespace"])
    op.create_index(op.f("ix_translation_entries_key"), "translation_entries", ["key"])


def downgrade() -> None:
    op.drop_index(op.f("ix_translation_entries_key"), table_name="translation_entries")
    op.drop_index(op.f("ix_translation_entries_namespace"), table_name="translation_entries")
    op.drop_index(op.f("ix_translation_entries_locale"), table_name="translation_entries")
    op.drop_index(op.f("ix_translation_entries_id"), table_name="translation_entries")
    op.drop_table("translation_entries")
