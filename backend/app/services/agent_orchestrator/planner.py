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
      "confidence": 0.0
    }
  ],
  "final_response_instruction": "how to answer after DB results are available",
  "final_response_hint": "Persian final answer if no more DB steps are needed",
  "clarification_question": null,
  "confidence": 0.0
}
Use SQL only as a proposal. The backend validates and executes it.
Do not include markdown, comments, prose, SQL fences, or hidden reasoning.
You are responsible for all financial intent detection. There are no backend keyword shortcuts.
For questions asking both income and expense, create separate SELECT steps for both totals.
For transaction creation, SELECT real categories first when category choice is needed, then choose category_id only from returned rows in the next iteration.
Natural Persian finance messages are usually enough to act. Examples of enough information:
- "چهل هزار تومن صبح پول اتوبوس دادم" means expense, amount 40000, today, bus/morning description.
- "هفته پیش یک پروژه زدم که پولش سه روز پیش اومد چهارده میلیون تومان بود" means income, amount 14000000, transaction date three days ago, project income description.
Use relative date phrases directly as params if useful: امروز, دیروز, پریروز, سه روز پیش, هفته پیش, ماه گذشته, این ماه, این هفته.
Use Persian written numbers or normalized integers in params. The backend normalizes values after you extract them.
For totals, grouped top categories, recent transactions, budgets, goals, memories, persona, facts, warnings, or decisions, propose safe SELECTs against DB World tables.
If Personal CFO tables are available, you may propose INSERTs for finance-relevant memories, facts, insights, warnings, or decision logs. Do not store secrets or unrelated personal details.
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
        for item in (history or [])[-8:]:
            if item.get("role") in {"user", "assistant"} and item.get("content"):
                messages.append({"role": item["role"], "content": str(item["content"])[:1000]})
        if execution_results:
            messages.append(
                {
                    "role": "system",
                    "content": "Validated execution results:\n" + json.dumps(execution_results, ensure_ascii=False, default=str),
                }
            )
        messages.append({"role": "user", "content": user_message})

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
