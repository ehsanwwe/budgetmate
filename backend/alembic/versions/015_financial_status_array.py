"""convert current financial status to JSON array"""
import json
from alembic import op
import sqlalchemy as sa

revision = "015_financial_status_array"
down_revision = "014_add_google_oauth_fields"
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, current_financial_status FROM users")).fetchall()
    for user_id, value in rows:
        converted = [] if not value else [value]
        bind.execute(sa.text("UPDATE users SET current_financial_status=:value WHERE id=:id"), {"value": json.dumps(converted), "id": user_id})
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("current_financial_status", existing_type=sa.String(), type_=sa.JSON(), nullable=False, server_default="[]")

def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, current_financial_status FROM users")).fetchall()
    for user_id, value in rows:
        try:
            values = json.loads(value) if isinstance(value, str) else value
        except (TypeError, json.JSONDecodeError):
            values = []
        bind.execute(sa.text("UPDATE users SET current_financial_status=:value WHERE id=:id"), {"value": values[0] if values else None, "id": user_id})
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("current_financial_status", existing_type=sa.JSON(), type_=sa.String(), nullable=True, server_default=None)
