from __future__ import annotations

import json

from sqlalchemy.engine import Engine

from app.services.agent_orchestrator.schema_introspector import build_safe_schema
from app.services.agent_orchestrator.types import DbWorld


WORLD_INSTRUCTIONS = [
    "You can only plan SELECT, INSERT, and explicitly allowed UPDATE operations listed in this DB World.",
    "Never plan DELETE, DROP, ALTER, CREATE, PRAGMA, ATTACH, DETACH, VACUUM, comments, or multiple SQL statements.",
    "All user-owned tables are scoped by the backend. Do not SELECT, filter by, include, or set user_id; SQL or params containing user_id will be rejected and must be repaired by removing user_id.",
    "Use only named parameters such as :amount and put values in params.",
    "For categories, SELECT real rows first. Choose category_id only from returned rows; do not guess hidden ids.",
    "For transactions, INSERT only category_id, amount, type, description, date. The backend injects the authenticated user id.",
    "For goals, SELECT current goals before updating or archiving. UPDATE is allowed only for safe goal fields listed in the table columns/policy; use UPDATE status='archived' and is_active=false for delete/archive requests.",
    "For named goal questions, compare the user's wording with actual SELECTed goal rows. Do not invent goal ids. If exactly one goal is a confident match, use that id; if none or multiple are plausible, ask a specific clarification.",
    "For future commitments, use pending status for unpaid obligations and include due_date or due_month when known.",
    "For spending decisions, query budget, current spending, goals, future commitments, and relevant memories before recommending a cap or approving a large purchase.",
    "For future-plan questions, SELECT goals, future_commitments, financial_facts, and financial_memories for the requested date range before answering.",
    "For direct goal questions, SELECT active goals first; include target_amount, current_amount, deadline, and status in the answer.",
    "For planned purchases in the future, create a future commitment or financial fact, not a current transaction, unless the user says they already bought or paid.",
    "Use recent chat history for follow-up amounts. If the user only provides an amount after a planned-purchase clarification, connect it to that pending future purchase.",
    "For financial memories/facts/insights/warnings/decision logs, store only finance-relevant information and keep content compact.",
    "Ask clarification only when amount, type, date, or target entity is genuinely ambiguous.",
    "Return strict JSON matching AgentPlan only. Do not include prose during planning.",
]


def build_db_world(engine: Engine) -> DbWorld:
    return DbWorld(tables=build_safe_schema(engine), instructions=WORLD_INSTRUCTIONS)


def render_db_world(engine: Engine) -> str:
    world = build_db_world(engine)
    return json.dumps(world.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
