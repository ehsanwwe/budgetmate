from __future__ import annotations

import json

from sqlalchemy.engine import Engine

from app.services.agent_orchestrator.schema_introspector import build_safe_schema
from app.services.agent_orchestrator.types import DbWorld


WORLD_INSTRUCTIONS = [
    "You can only plan SELECT, INSERT, UPDATE, and DELETE operations against tables whose allowed_operations include that op in this DB World.",
    "Never plan DROP, ALTER, CREATE, PRAGMA, ATTACH, DETACH, VACUUM, comments, or multiple SQL statements.",
    "All user-owned tables are scoped by the backend. Do not SELECT, filter by, include, or set user_id; SQL or params containing user_id will be rejected and must be repaired by removing user_id.",
    # DELETE tool description
    "DELETE tool — use when the user asks to remove/discard/erase a stored record (a transaction, a future_commitment, etc.). Understand deletion requests naturally from the message; do not require literal 'delete' wording. Persian phrases like 'حذف کن', 'پاک کن', 'ولش کن', 'اینو بردار', 'اشتباه ثبت شد', 'برش دار' can all express deletion of a specific stored record when they refer to an item the user is discussing.",
    "DELETE syntax: DELETE FROM <table> WHERE <filter>. Filter must use only whitelisted selectable columns joined by AND, with named parameters — for example: DELETE FROM transactions WHERE id = :id | DELETE FROM transactions WHERE id IN (:i1, :i2) | DELETE FROM transactions WHERE type = :t AND date = :d. Do NOT include user_id, subqueries, or OR. The backend adds user-scoping automatically.",
    "Before deleting by fuzzy criteria (last transaction, restaurant expense today, all conversation-created records) FIRST issue a SELECT to obtain real ids from the DB. Then issue DELETE using those ids. Never fabricate ids.",
    "If a delete match is ambiguous (multiple candidates), ask ONE concise clarification question naming the candidates and their amounts/dates instead of guessing.",
    "If a delete SELECT returns zero rows, do NOT insert a DELETE step. Answer honestly that no matching record was found.",
    "For 'delete everything I told you about in this conversation' style requests: SELECT recent transactions (and future_commitments if relevant) whose created_at falls within the current conversation window, then DELETE by their id list. Confirm the actual count in the final response using the executor result — do not claim success unless the executor reports rows deleted.",
    "After a deletion succeeds you MUST treat those records as gone for the rest of this turn's reasoning. Do not include their amounts in subsequent totals, budgets, or advice within the same conversation until the user restores them.",
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
