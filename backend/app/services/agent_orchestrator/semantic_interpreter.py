"""LLM-driven semantic interpretation layer — runs before gate and planner.

The SemanticInterpreter is the first orchestration step. It calls the LLM once
to understand the user's message holistically: intent, money, date, action
capabilities, and flow-state routing. Gate and planner use this result rather
than calling their own classification LLMs.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.agent_orchestrator.date_utils import app_timezone, local_today
from app.services.ai import LLMProviderError, get_ai_chat_completion

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are BudgetMate's semantic interpreter. Read the user's Persian (or mixed) financial message
and return a structured JSON object. You have access to:
- Current date and timezone
- Recent conversation history
- Active pending flow (if any)
- Compact finance context

Return ONLY valid JSON — no markdown, no prose:
{{
  "language": "fa|en|mixed",
  "user_intent": "<see values below>",
  "is_question": true/false,
  "should_continue_pending_flow": true/false,
  "should_cancel_pending_flow": true/false,
  "should_bypass_goal_intake": true/false,
  "referenced_entities": {{
    "goal_title": null,
    "target_item": null,
    "transaction_title": null,
    "commitment_title": null
  }},
  "money": {{
    "amount": null,
    "currency": "IRT|IRR|unknown",
    "raw_text": null,
    "confidence": 0.0
  }},
  "date": {{
    "raw_text": null,
    "resolved_date": null,
    "date_kind": "past|today|future|deadline|due_date|transaction_date|unknown",
    "confidence": 0.0,
    "needs_user_confirmation": false
  }},
  "action": {{
    "can_write": false,
    "write_type": null,
    "requires_more_info": false,
    "missing_fields": []
  }},
  "final_behavior": {{
    "answer_directly": false,
    "ask_clarification": false,
    "clarification_reason": null
  }}
}}

user_intent values:
- expense: already-completed payment ("خریدم", "دادم", "پرداخت کردم", "هزینه کردم") — money has actually left the user's pocket / account
- income: received money that has ACTUALLY ARRIVED ("گرفتم", "واریز شد", "حقوق اومد", "درآمد داشتم")
- future_commitment: binding future obligation ("چک دارم", "قسط دارم", "باید اجاره بدم", "بدهی دارم")
- goal_desire: non-binding wish to buy/save ("میخوام بخرم", "دوست دارم بخرم", "میخوام پس‌انداز کنم")
- explicit_goal_add: explicitly requesting goal creation WITH all required info ("یک هدف اضافه کن X مبلغ Y تا Z")
- goal_question: asking about an existing goal progress or deadline ("چقدر مونده", "برای همون تور چقدر باید سیو کنم")
- budget_question: asking about available budget or spending summary
- advice_question: asking for financial advice/analysis
- cancel_flow: PURE cancellation with NO destructive or informational request attached ("بیخیال", "ولش کن", "منصرف شدم", "فراموشش کن", "نمیخوام", "لغو" when they mean "do nothing, drop this pending question")
- answer_pending_question: answering a question the assistant just asked (amount, date, or add/consult choice)
- invalid_both_choice: user wants "both" options when only one can proceed ("هر دو", "هردو", "جفتش", "both")
- other: none of the above — includes deletion requests, invalidation requests, reasoning-context requests, balance questions, and mixed messages that the planner should handle

CANCEL vs DELETE / INVALIDATION — CRITICAL:
Cancellation-style words ("بیخیال", "ولش کن", "فراموشش کن", "forget it", "never mind", "leave it") are NOT always cancel_flow. They are only cancel_flow when the entire message is asking the assistant to do nothing.

If the same message ALSO asks to:
  - delete/remove/erase records ("پاک کن", "حذف کن", "delete", "remove", "erase"),
  - ignore records for the current calculation ("قبلی‌ها رو حساب نکن", "ignore those in the plan", "start from here"),
  - answer a new question,
  - register a new transaction/commitment,
then:
  - user_intent MUST NOT be cancel_flow
  - user_intent MUST be "other" (or expense/income if applicable)
  - should_cancel_pending_flow MUST be false
  - should_bypass_goal_intake MUST be true
  - The planner will read the full message and decide the right tool call.

Examples of mixed messages that are NOT cancel_flow:
  - «ولش کن، هرچی تراکنش گفتم پاک کن» → other + should_bypass_goal_intake=true (the user wants deletion)
  - «forget the previous plan and delete the transactions I entered» → other + should_bypass_goal_intake=true
  - «قبلی‌ها رو حساب نکن، از اول شروع کنیم» → other + should_bypass_goal_intake=true (invalidation, not cancellation)

RECEIVED vs UNCERTAIN INCOME — CRITICAL:
user_intent=income is ONLY for income that has actually been received.
If the message describes income as maybe/likely/pending/scheduled/expected:
  - «شاید ۵ میلیون بگیرم», «احتمالاً حقوقم تا هشتم میاد», «اگر پول پروژه بیاد ۲۰ میلیون می‌گیرم»,
    «حقوقم قطعیه ولی هفته بعد می‌آید», «probably», «might», «expected next week»,
then:
  - user_intent MUST be "other"
  - action.can_write MUST be false
  - action.write_type MUST be null
This lets the planner keep the money as forecast/scenario and NOT insert a transaction.

referenced_entities:
- goal_title: title of an EXISTING goal being asked about
- target_item: item being DESIRED (for goal_desire intent, e.g. "لپتاپ", "ماشین")
- transaction_title: title of a completed transaction being described
- commitment_title: title of a commitment being registered

money.amount: integer Toman value (no currency suffix). Confidence >= 0.8 when unambiguous.
date.resolved_date: ISO YYYY-MM-DD. Compute from current_date for relative phrases.
  "سه روز بعد/دیگه/جلوتر/آینده/بعد از سه روز" = current_date + 3 days
  "یک ماه بعد/دیگه/جلوتر/آینده" = current_date + 1 month
  "دو ماه بعد" = current_date + 2 months
  "آخر این ماه" = last day of current month
  "آخر ماه بعد" = last day of next month
  For vague seasonal phrases, set confidence < 0.6 and needs_user_confirmation=true.

Current date: {current_date}
Timezone: {timezone}
Pending flow: {pending_context}
"""

_USER_TMPL = """\
Finance context (compact):
{finance_context}

Conversation history (use to resolve references like 'هزینه‌های بالا', 'اول چت گفتم', 'قبلاً گفتم'):
{history}

Current user message: {message}"""


@dataclass
class SemanticResult:
    language: str = "fa"
    user_intent: str = "other"
    is_question: bool = False
    should_continue_pending_flow: bool = False
    should_cancel_pending_flow: bool = False
    should_bypass_goal_intake: bool = False
    referenced_entities: dict = field(default_factory=dict)
    money: dict = field(default_factory=dict)
    date: dict = field(default_factory=dict)
    action: dict = field(default_factory=dict)
    final_behavior: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_llm_json(cls, data: dict) -> "SemanticResult":
        return cls(
            language=str(data.get("language", "fa")),
            user_intent=str(data.get("user_intent", "other")),
            is_question=bool(data.get("is_question", False)),
            should_continue_pending_flow=bool(data.get("should_continue_pending_flow", False)),
            should_cancel_pending_flow=bool(data.get("should_cancel_pending_flow", False)),
            should_bypass_goal_intake=bool(data.get("should_bypass_goal_intake", False)),
            referenced_entities=data.get("referenced_entities") or {},
            money=data.get("money") or {},
            date=data.get("date") or {},
            action=data.get("action") or {},
            final_behavior=data.get("final_behavior") or {},
            raw=data,
        )

    @classmethod
    def fallback(cls) -> "SemanticResult":
        """Used when the LLM call fails; downstream still functions via existing heuristics."""
        return cls(raw={"_fallback": True})

    @property
    def money_amount(self) -> int | None:
        """High-confidence extracted amount, or None."""
        amt = self.money.get("amount")
        conf = float(self.money.get("confidence", 0.0))
        if amt is not None and conf >= 0.75:
            try:
                return int(amt)
            except (TypeError, ValueError):
                return None
        return None

    @property
    def date_raw_text(self) -> str | None:
        return self.date.get("raw_text") or None

    @property
    def date_resolved(self) -> date | None:
        raw = self.date.get("resolved_date")
        conf = float(self.date.get("confidence", 0.0))
        if raw and conf >= 0.75:
            try:
                return date.fromisoformat(str(raw))
            except (ValueError, TypeError):
                return None
        return None

    @property
    def target_item(self) -> str | None:
        return (self.referenced_entities.get("target_item") or "").strip() or None

    @property
    def referenced_goal_title(self) -> str | None:
        return (self.referenced_entities.get("goal_title") or "").strip() or None


class SemanticInterpreter:
    """Calls the LLM once to understand the user message before any routing decisions."""

    async def interpret(
        self,
        user_message: str,
        history: list[dict] | None,
        pending_intent_payload: dict | None,
        finance_context: dict,
    ) -> SemanticResult:
        today = local_today()
        tz_obj = app_timezone()
        tz = str(getattr(tz_obj, "key", "Asia/Tehran"))

        pending_context: str
        if pending_intent_payload:
            state = pending_intent_payload.get("state", "")
            item = pending_intent_payload.get("item_title", "")
            amount = pending_intent_payload.get("target_amount")
            date_text = pending_intent_payload.get("target_date_text")
            pending_context = (
                f"state={state}, item={item!r}, "
                f"amount={amount or 'pending'}, date={date_text or 'pending'}"
            )
        else:
            pending_context = "none"

        history_lines: list[str] = []
        if history:
            for item in history[-15:]:
                if item.get("role") in {"user", "assistant"} and item.get("content"):
                    label = "کاربر" if item["role"] == "user" else "دستیار"
                    history_lines.append(f"[{label}]: {str(item['content'])[:600]}")

        compact_ctx = {
            k: v
            for k, v in (finance_context or {}).items()
            if k in {
                "budget",
                "total_spent_this_month",
                "total_income_this_month",
                "remaining_budget",
                "active_goals",
                "current_gregorian_date",
            }
        }

        system_prompt = _SYSTEM.format(
            current_date=today.isoformat(),
            timezone=tz,
            pending_context=pending_context,
        )
        user_content = _USER_TMPL.format(
            finance_context=json.dumps(compact_ctx, ensure_ascii=False, default=str),
            history="\n".join(history_lines) if history_lines else "(no prior context)",
            message=user_message,
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = await get_ai_chat_completion(messages, require_json=True)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return SemanticResult.fallback()
            result = SemanticResult.from_llm_json(data)
            logger.debug(
                "semantic_interpreter intent=%s cancel=%s bypass=%s money_conf=%.2f date_conf=%.2f",
                result.user_intent,
                result.should_cancel_pending_flow,
                result.should_bypass_goal_intake,
                float(result.money.get("confidence", 0)),
                float(result.date.get("confidence", 0)),
            )
            return result
        except (LLMProviderError, json.JSONDecodeError, Exception) as exc:
            logger.debug("SemanticInterpreter LLM call failed: %s", exc)
            return SemanticResult.fallback()
