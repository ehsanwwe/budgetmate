from __future__ import annotations

import json

from sqlalchemy.engine import Engine

from app.services.agent_orchestrator.schema_introspector import build_safe_schema
from app.services.agent_orchestrator.types import DbWorld


WORLD_INSTRUCTIONS = [
    "You can only plan SELECT, INSERT, and explicitly allowed UPDATE operations listed in this DB World.",
    "Never plan DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH, DETACH, VACUUM, comments, or multiple SQL statements.",
    "All user-owned tables are scoped by the backend. Do not include or set user_id.",
    "Use only named parameters such as :amount and put values in params.",
    "For categories, SELECT real rows first. Choose category_id only from returned rows; do not guess hidden ids.",
    "For transactions, INSERT only category_id, amount, type, description, date. The backend injects the authenticated user id.",
    "For goals, SELECT current goals before updating or archiving. Use UPDATE status='archived' and is_active=false for delete/archive requests.",
    "For future commitments, use pending status for unpaid obligations and include due_date or due_month when known.",
    "For spending decisions, query budget, current spending, goals, future commitments, and relevant memories before recommending a cap or approving a large purchase.",
    "For financial memories/facts/insights/warnings/decision logs, store only finance-relevant information and keep content compact.",
    "Ask clarification only when amount, type, date, or target entity is genuinely ambiguous.",
    "Return strict JSON matching AgentPlan only. Do not include prose during planning.",
]


def build_db_world(engine: Engine) -> DbWorld:
    return DbWorld(tables=build_safe_schema(engine), instructions=WORLD_INSTRUCTIONS)


def render_db_world(engine: Engine) -> str:
    world = build_db_world(engine)
    return json.dumps(world.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
