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
    # Goal intake gate rule — CRITICAL
    "GOAL INTAKE GATE: The backend GoalIntakeGate intercepts desire-wording goal messages (میخوام بخرم, قصد دارم, etc.) and runs a multi-turn state machine before inserting any goal. The planner is only called for non-goal-like messages or explicit goal additions. Do NOT insert a goal from non-explicit desire wording.",
    "EXPLICIT GOAL ADD: INSERT INTO goals ONLY when the user explicitly requests adding a goal ('یک هدف اضافه کن', 'ثبت کن به عنوان هدف') WITH amount and deadline in the same message. For all other goal-like wording, return SELECT steps only and let the gate handle the state machine.",
    "PENDING INTENT: The pending_agent_intents table is system-only. Never SELECT or INSERT from it in plans. The gate manages it internally.",
    # Goal rules
    "For goals, SELECT current goals before updating or archiving. UPDATE is allowed only for safe goal fields listed in the table columns/policy; use UPDATE status='archived' and is_active=false for delete/archive requests.",
    "For named goal questions, compare the user's wording with actual SELECTed goal rows. Do not invent goal ids. If exactly one goal is a confident match, use that id; if none or multiple are plausible, ask a specific clarification.",
    "For a named goal timing question (e.g., 'این هدف تا کی فعال است'), SELECT goals and answer from the deadline column. Do NOT UPDATE unless the user explicitly says to change the deadline.",
    # Future commitment rules
    "For future commitments, use pending status for unpaid obligations and include due_date or due_month when known.",
    "Future commitments are for BINDING obligations the user is already committed to: checks, installments, rent dues, tour balances, loan repayments. Do not create a future_commitment when the user is merely planning or wanting to buy something.",
    # Semantic classification enforcement
    "GOAL vs COMMITMENT boundary: 'میخوام بخرم' → gate handles it (return SELECT only). 'چک دارم' → INSERT future_commitments. 'خریدم' → INSERT transactions.",
    "FUTURE COMMITMENT (not goal): Use future_commitments when user has a binding obligation: چک دارم, قسط دارم, باید اجاره/کرایه بدهم, تور ثبت‌نام کردم و باقی‌مانده‌اش ماه بعد است.",
    # Spending decisions
    "For spending decisions, query budget, current spending, goals, future commitments, and relevant memories before recommending a cap or approving a large purchase.",
    "For future-plan questions, SELECT goals, future_commitments, financial_facts, and financial_memories for the requested date range before answering.",
    "For direct goal questions, SELECT active goals first; include target_amount, current_amount, deadline, and status in the answer.",
    "For advice/analysis questions about reducing costs or improving finances, SELECT transactions grouped by category, budgets, active goals, and future commitments; return grounded advice based on real data; never return a generic retry message.",
    "For financial memories/facts/insights/warnings/decision logs, store only finance-relevant information and keep content compact.",
    "Ask clarification only when amount, type, date, or target entity is genuinely ambiguous.",
    "Return strict JSON matching AgentPlan only. Do not include prose during planning.",
]


def build_db_world(engine: Engine) -> DbWorld:
    return DbWorld(tables=build_safe_schema(engine), instructions=WORLD_INSTRUCTIONS)


def render_db_world(engine: Engine) -> str:
    world = build_db_world(engine)
    return json.dumps(world.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
