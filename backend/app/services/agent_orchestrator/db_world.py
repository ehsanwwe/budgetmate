from __future__ import annotations

import json

from sqlalchemy.engine import Engine

from app.services.agent_orchestrator.schema_introspector import build_safe_schema
from app.services.agent_orchestrator.types import DbWorld


WORLD_INSTRUCTIONS = [
    "You can only plan SELECT, INSERT, UPDATE, and DELETE operations against tables whose allowed_operations include that op in this DB World.",
    "Never plan DROP, ALTER, CREATE, PRAGMA, ATTACH, DETACH, VACUUM, comments, or multiple SQL statements.",
    "All user-owned tables are scoped by the backend. Do not SELECT, filter by, include, or set user_id; SQL or params containing user_id will be rejected and must be repaired by removing user_id.",
    # Transaction deletion policy — LLM must never plan DELETE against transactions
    "TRANSACTION DELETION IS NOT AVAILABLE IN CHAT: You MUST NOT plan a DELETE step against the transactions table under any circumstance. The transactions table intentionally has no DELETE in its allowed_operations. Understand deletion-style requests naturally (e.g. «تراکنش آخرم را حذف کن», «این خرید را پاک کن», «همه هزینه‌های امروز را بردار», «delete my last transaction», «remove the taxi expense») and answer them with a short natural-language explanation that the user should delete transactions from the transaction-management menu («مدیریت تراکنش‌ها» / 'transaction management'). Do not invent an alternative side-effect (do not archive, do not zero the amount, do not create a compensating transaction). Just answer in prose via final_response_hint.",
    "DELETE tool — reserved for future_commitments only. Use it when the user asks to remove a stored future_commitment. Understand deletion requests naturally from the message; do not require literal 'delete' wording. Persian phrases like 'حذف کن', 'پاک کن', 'ولش کن', 'اینو بردار', 'اشتباه ثبت شد', 'برش دار' can all express deletion of a stored future_commitment when they refer to that obligation.",
    "DELETE syntax (future_commitments only): DELETE FROM future_commitments WHERE <filter>. Filter must use only whitelisted selectable columns joined by AND, with named parameters — for example: DELETE FROM future_commitments WHERE id = :id | DELETE FROM future_commitments WHERE id IN (:i1, :i2). Do NOT include user_id, subqueries, or OR. The backend adds user-scoping automatically. NEVER emit DELETE FROM transactions.",
    "Before deleting by fuzzy criteria (a specific check, a specific installment) FIRST issue a SELECT to obtain real future_commitments ids from the DB. Then issue DELETE using those ids. Never fabricate ids.",
    "If a delete match is ambiguous (multiple candidates), ask ONE concise clarification question naming the candidates and their amounts/dates instead of guessing.",
    "If a delete SELECT returns zero rows, do NOT insert a DELETE step. Answer honestly that no matching record was found.",
    # Bulk deletion safety
    "BULK DELETION SAFETY: A DELETE that filters by anything OTHER than a specific id or a specific id list (e.g. filters by type, date, source_message_id, amount, description) is a BULK delete. You MUST set the plan step field bulk_scope=true for these. If you do not set bulk_scope=true, the executor rejects the delete unless exactly one row matches the filter — this prevents singular requests like 'delete the 500,000 toman commitment' from silently deleting several similar rows when the match is ambiguous.",
    "AMBIGUOUS SINGULAR DELETE: If the user's phrasing is singular ('delete this check', 'حذف کن این چک') do NOT set bulk_scope=true. Do a SELECT first; if it returns more than one candidate, present them briefly and ask which one instead of guessing.",
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
    # Conversation reasoning state — persisted invalidation, stated balance, assumptions
    "CONVERSATION REASONING STATE: When the user says «قبلی‌ها رو حساب نکن», 'ignore those transactions in the plan', 'start over from here', 'my balance is X', or gives a simplifying assumption ('assume everything is due by the 8th'), record the decision so it survives across turns. Do this with INSERT INTO financial_facts using fact_type='chat_reasoning_state' and value_json containing one or more of: {\"excluded_transaction_ids\":[...]}, {\"excluded_commitment_ids\":[...]}, {\"reasoning_baseline_at\":\"ISO datetime\"}, {\"stated_balance\":<int>,\"stated_balance_at\":\"ISO datetime\"}, {\"assumptions\":[{\"topic\":\"...\",\"assumption\":\"...\"}]}, {\"disclosed_debts\":[{\"title\":\"...\",\"amount\":<int>,\"due_date\":\"...\"}]}. Only include the fields being added; existing state is merged automatically. This is orthogonal to DELETE — the DB rows are NOT modified.",
    "READ that state from finance_context.conversation_reasoning_state on every turn — it already contains adjusted_* totals and the merged exclusions/balance/assumptions. Prefer adjusted_* totals in reasoning; keep raw totals only when specifically asked about totals in the DB.",
    "USER-STATED BALANCE: When the user tells you their current cash+bank total ('روی هم ۷ میلیون تومن دارم', 'I have 7 million'), store it via a chat_reasoning_state fact with {\"stated_balance\":<toman_int>,\"stated_balance_at\":\"ISO datetime\"}. Then use conversation_reasoning_state.user_stated_available_balance for any personalized allocation. Do not ask again in the same conversation.",
    "USER-DISCLOSED DEBT: When the user tells you about a debt that is not stored in future_commitments (e.g. «۱۰ میلیون بدهی دارم» without a due_date binding), you MUST include it in reasoning even without persisting. Optionally record it as a chat_reasoning_state fact with {\"disclosed_debts\":[{\"title\":\"...\",\"amount\":<int>,\"note\":\"...\"}]} so future turns remember it. Never respond with 'no debts on file' when the user has told you about debts in the conversation.",
    "SIMPLIFYING ASSUMPTIONS: When the user gives an assumption («فرض کن همه تا هشتم سررسیده», 'assume the salary arrives'), store it in chat_reasoning_state.assumptions and USE the assumption immediately; do not ask again for the detail the user just told you to abstract away.",
    "Ask clarification only when amount, type, date, or target entity is genuinely ambiguous.",
    "Return strict JSON matching AgentPlan only. Do not include prose during planning.",
]


def build_db_world(engine: Engine) -> DbWorld:
    return DbWorld(tables=build_safe_schema(engine), instructions=WORLD_INSTRUCTIONS)


def render_db_world(engine: Engine) -> str:
    world = build_db_world(engine)
    return json.dumps(world.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
