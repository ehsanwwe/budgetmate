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
  "requires_db": true,
  "steps": [
    {
      "step_id": "s1",
      "operation_type": "select|insert|final_response|ask_clarification|no_op",
      "purpose": "why this is needed",
      "table_name": "categories|transactions|budgets|goals|chat_messages|users|null",
      "sql": "parameterized SQL or null",
      "params": {},
      "depends_on": [],
      "user_visible": false,
      "confidence": 0.0
    }
  ],
  "final_response_hint": "Persian final answer if no more DB steps are needed",
  "clarification_question": null,
  "confidence": 0.0
}
Use SQL only as a proposal. The backend validates and executes it.
Do not include markdown, comments, prose, SQL fences, or hidden reasoning.
The LLM is responsible for financial intent detection. Do not wait for backend shortcuts.
For questions asking both income and expense, create separate SELECT steps for both totals.
For transaction creation, SELECT real categories first when category choice is needed.
Never invent totals, category names, or ids. Use final_response only after validated execution results are available."""


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
