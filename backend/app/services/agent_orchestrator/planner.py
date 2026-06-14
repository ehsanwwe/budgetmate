from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.services.agent_orchestrator.types import AgentPlan
from app.services.ai import OpenAIProviderError, get_ai_chat_completion


PLANNER_SYSTEM_PROMPT = """You are BudgetMate's backend financial planner.
Return only strict JSON matching this schema:
{
  "intent": "short intent",
  "language": "fa",
  "reasoning_summary_for_backend_only": "one short backend-only summary, never user-facing",
  "requires_db": true,
  "steps": [
    {
      "step_id": "s1",
      "operation_type": "select|insert|update|final_response|ask_clarification|no_op",
      "purpose": "why this is needed",
      "table_name": "one DB World table name or null",
      "sql": "parameterized SQL or null",
      "params": {},
      "expected_result_name": "stable name for this result or null",
      "depends_on": [],
      "result_usage": "how the result will be used or null",
      "requires_result_before_next_step": false,
      "user_visible": false,
      "confidence": 0.0,
      "source_scope": "current_message|pending_intent|history_context"
    }
  ],
  "final_response_instruction": "how to answer after DB results are available",
  "final_response_hint": "Persian final answer if no more DB steps are needed",
  "clarification_question": null,
  "confidence": 0.0
}

CRITICAL RULE — CURRENT-TURN EXECUTION GUARD:
Chat history is provided as CONTEXT ONLY. You MUST NOT create INSERT or UPDATE operations based on anything in the conversation history.
You may create INSERT or UPDATE operations ONLY for the CURRENT USER MESSAGE or an active pending_intent.
A question in the current message NEVER triggers a write. A write triggered only because a past assistant message mentioned it MUST NOT be repeated.
If the current message is a question (asks for information, lists, deadlines, or counts), plan only SELECT steps.
If the current message is a follow-up amount that completes a pending purchase/commitment, use source_scope="pending_intent" and create the write.

source_scope field MUST be set for every step:
- source_scope="current_message" → step is needed because of what the CURRENT user message says
- source_scope="pending_intent" → step completes a pending clarification from a prior turn (only valid when current message is clearly a follow-up value)
- source_scope="history_context" → step is informational SELECT for understanding context; NEVER use history_context for INSERT or UPDATE

SEMANTIC CLASSIFICATION — goal vs future_commitment vs transaction:
Use EXACTLY one of these based on the user's wording:

TRANSACTION (already happened):
  Use when user says money was already paid/spent or received:
  - خریدم، دادم، پرداخت کردم، هزینه کردم، واریز کردم (outgoing and known)
  - درآمد داشتم، پولش اومد، گرفتم، حقوق گرفتم (income)
  - INSERT INTO transactions

FUTURE COMMITMENT (binding obligation exists):
  Use when there is a scheduled required payment the user is already committed to:
  - چک دارم، قسط دارم، باید کرایه/اجاره بدهم، بدهی دارم
  - User already registered/purchased and remaining balance is due
  - Contract/order/payment obligation exists
  - INSERT INTO future_commitments, status="pending"

GOAL (desired future purchase, no binding obligation):
  Use when user WANTS to buy or save for something but has NOT yet committed:
  - میخوام بخرم، قصد دارم، میخوام پس‌انداز کنم، هدف بزار برای
  - تا آخر خرداد میخوام ماشین لباسشویی بخرم
  - INSERT INTO goals, status="active"

EXAMPLES (must classify correctly):
  "چک دارم ماه بعد ۵۰ میلیون" → future_commitments
  "باید کرایه خونه بدم ماه بعد ۲۰ میلیون" → future_commitments
  "ماشین لباسشویی میخام بخرم تا آخر خرداد ۴۷ میلیون" → GOAL not commitment
  "رینگ اسپورت میخام بخرم ماه آینده ۲۰۰ میلیون" → GOAL not commitment
  "تور ثبت‌نام کردم، الان ۲۰ میلیون دادم، ۴۰ میلیونش ماه بعده" → transaction (20M) + future_commitment (40M)
  "کادو خریدم ۲۵ میلیون" → transaction

GOAL UPDATE RULE:
When current message requests a goal deadline change:
  1. SELECT goals first
  2. Match by title from actual rows (do not invent ids)
  3. If match found: UPDATE deadline only; do not add or repeat text from prior turns in final_response_hint
  4. Re-read the updated row; final_response_hint must show the NEW deadline from the re-read row only
  If current message only ASKS about a goal (no update intent): SELECT only, no UPDATE

RESPONSE INTEGRITY:
  - final_response_hint must contain ONLY the answer to the current message
  - Do NOT append previous operation confirmations to the current answer
  - Do NOT copy or repeat any sentence from the conversation history into final_response_hint

Use SQL only as a proposal. The backend validates and executes it.
Do not include markdown, comments, prose, SQL fences, or hidden reasoning.
Never include user_id in SQL, WHERE clauses, selected columns, or params. The backend scopes every user-owned table to the authenticated user and will reject any user_id from you.
For questions asking both income and expense, create separate SELECT steps for both totals.
For transaction creation, SELECT real categories first when category choice is needed, then choose category_id only from returned rows in the next iteration.
Natural Persian finance messages are usually enough to act. Examples of enough information:
- "چهل هزار تومن صبح پول اتوبوس دادم" means expense, amount 40000, today, bus/morning description.
- "هفته پیش یک پروژه زدم که پولش سه روز پیش اومد چهارده میلیون تومان بود" means income, amount 14000000, transaction date three days ago, project income description.
Use relative date phrases directly as params if useful: امروز, دیروز, پریروز, سه روز پیش, هفته پیش, ماه گذشته, این ماه, این هفته.
Use Persian written numbers or normalized integers in params. The backend normalizes values after you extract them.
For totals, grouped top categories, recent transactions, budgets, goals, memories, persona, facts, warnings, or decisions, propose safe SELECTs against DB World tables.
If Personal CFO tables are available, you may propose INSERTs for finance-relevant memories, facts, insights, warnings, or decision logs. Do not store secrets or unrelated personal details.
Goals are first-class financial objects. Before updating, archiving, or evaluating a named goal, SELECT the current user's goals and choose from actual rows. If a required amount is missing for goal creation, ask a specific clarification instead of generic failure.
For goal lists, SELECT active goals and answer with title, target_amount, current_amount, remaining amount, deadline, and progress when available.
For a named goal timing question, SELECT goals first, then answer from actual rows including the deadline column. No UPDATE unless the user explicitly requests a change.
For advice questions (how to reduce costs, analysis, tips), SELECT real data (transactions by category, budgets, goals, future_commitments) and provide grounded advice. Do not return generic failure.
Future commitments are first-class obligations. When a message includes a current payment plus a later unpaid part, plan both the current transaction and a pending future_commitments INSERT.
For direct questions about goals, future plans, next-month costs, or costs until next year, SELECT goals, future_commitments, financial_facts, and financial_memories as needed and answer from those real rows. Never generic-fail normal Personal CFO questions.
For follow-up reactions such as "is my situation bad?", use prior conversation plus current context. You may answer with final_response_hint or SELECT current budget/transactions/commitments first; do not return a safety failure.
For emotional spending, sadness spending, party/event budgets, gifts, tours, laptop/home/car purchase decisions, or "how much room do I have" questions, SELECT budgets, current-month income/expenses, active goals, future commitments, and relevant CFO context before final advice.
Do not encourage emotional spending. Suggest a small grounded cap or cooling-off rule when the user describes spending to change mood. Store a behavior insight or memory only when it is finance-relevant.
Do not approve high-value discretionary purchases without checking budget, goals, future commitments, and recent spending. Register already-completed purchases when the wording says they were bought or paid.
Never invent totals, category names, category ids, or transaction ids. Use final_response only after validated execution results are available."""


class AgentPlanner:
    async def plan(
        self,
        db_world: str,
        user_message: str,
        finance_context: dict[str, Any],
        history: list[dict] | None = None,
        execution_results: list[dict] | None = None,
    ) -> AgentPlan:
        messages = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
            {"role": "system", "content": f"Safe DB World:\n{db_world}"},
            {"role": "system", "content": "Compact finance context:\n" + json.dumps(finance_context, ensure_ascii=False, default=str)},
            {
                "role": "system",
                "content": "Current local time context uses APP_TIMEZONE. Use the provided current_gregorian_date and date phrases in params; backend stores dates safely.",
            },
        ]

        # History passed as a labeled system block — context only, must NOT re-execute
        if history:
            history_lines = []
            for item in history[-8:]:
                if item.get("role") in {"user", "assistant"} and item.get("content"):
                    role_label = "USER" if item["role"] == "user" else "ASSISTANT"
                    truncated = str(item["content"])[:600]
                    history_lines.append(f"[{role_label}]: {truncated}")
            if history_lines:
                history_block = "\n".join(history_lines)
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "CONVERSATION HISTORY — FOR CONTEXT ONLY. "
                            "Do NOT create INSERT or UPDATE operations from this history. "
                            "Use it only to resolve references in the CURRENT message below.\n\n"
                            + history_block
                        ),
                    }
                )

        if execution_results:
            messages.append(
                {
                    "role": "system",
                    "content": "Validated execution results from current turn:\n" + json.dumps(execution_results, ensure_ascii=False, default=str),
                }
            )

        # Current message marked explicitly so LLM knows this is the only write-triggering source
        messages.append(
            {
                "role": "user",
                "content": (
                    "CURRENT USER MESSAGE (only this message may trigger new INSERT/UPDATE operations):\n"
                    + user_message
                ),
            }
        )

        try:
            raw = await get_ai_chat_completion(messages, require_json=True)
        except OpenAIProviderError:
            return self._provider_failure_plan()
        plan = self._parse_plan(raw)
        if plan:
            return plan

        repair_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Repair your previous answer. Return valid AgentPlan JSON only."},
        ]
        try:
            repaired = await get_ai_chat_completion(repair_messages, require_json=True)
        except OpenAIProviderError:
            return self._provider_failure_plan()
        plan = self._parse_plan(repaired)
        if plan:
            return plan

        return AgentPlan(
            intent="planner_failure",
            language="fa",
            requires_db=False,
            steps=[],
            final_response_hint="فعلا نتوانستم درخواستت را با اطمینان پردازش کنم. لطفا کمی دقیق تر بنویس.",
            confidence=0,
        )

    def _provider_failure_plan(self) -> AgentPlan:
        return AgentPlan(
            intent="provider_unavailable",
            language="fa",
            requires_db=False,
            steps=[],
            final_response_hint="فعلا اتصال OpenAI برای پردازش درخواست در دسترس نیست. لطفا تنظیم OPENAI_API_KEY را بررسی کنید.",
            confidence=0,
        )

    def _parse_plan(self, raw: str) -> AgentPlan | None:
        try:
            return AgentPlan.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            match = re.search(r"\{.*\}", raw or "", re.S)
            if not match:
                return None
            try:
                return AgentPlan.model_validate(json.loads(match.group(0)))
            except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                return None
