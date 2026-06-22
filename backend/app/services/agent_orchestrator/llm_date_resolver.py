"""LLM-driven date resolver for natural-language Persian date phrases.

Replaces hardcoded regex phrase lists as the primary semantic date parser.
Used for goal deadlines and future commitment due dates where silently
defaulting to today is incorrect.

Deterministic fallbacks (ISO parse, "today", "yesterday") are tried first
for trivial cases to avoid unnecessary LLM calls.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

from app.services.agent_orchestrator.date_utils import app_timezone, local_today
from app.services.ai import LLMProviderError, get_ai_chat_completion

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a Persian date interpreter embedded in a financial app.
Given a natural-language date phrase (Persian or mixed), resolve it to an exact ISO date.

Current date: {current_date}
Timezone: {timezone}
Context type: {context_type}
  (transaction_date = past expense, goal_deadline = future saving goal,
   commitment_due_date = future bill/obligation, budget_period = month range)
Pending intent context: {pending_context}

Return ONLY valid JSON:
{{
  "raw_text": "original phrase",
  "resolved_date": "YYYY-MM-DD or null",
  "confidence": 0.0,
  "date_kind": "past|today|future|deadline|due_date|period|unknown",
  "interpretation_fa": "توضیح کوتاه فارسی (فقط برای لاگ/تست)",
  "needs_confirmation": true/false
}}

Resolution rules:
- Compute all relative phrases from current_date.
- "سه روز بعد / دیگه / جلوتر / آینده / بعد از سه روز" → current_date + 3 days
- "یک ماه بعد / دیگه / جلوتر / آینده / ماه بعد / ماه آینده" → current_date + 1 month
- "دو ماه بعد / دیگه / بعد از امروز" → current_date + 2 months
- "آخر این ماه / آخر ماه / پایان ماه" → last calendar day of current month
- "آخر ماه بعد / آخر ماه آینده" → last calendar day of next month
- "یک سال بعد / سال بعد / سال آینده" → current_date + 12 months
- "نزدیک عید / آستانه نوروز / قبل نوروز" → approximately Esfand 20 (March 11 of next year if current month > 3, else same year)
- "آخر تابستون / تابستان آینده" → September 22 (end of Persian summer) — set confidence 0.65, needs_confirmation=true
- "خرداد سال بعد" → June 22 of next year — confidence 0.8
- For vague seasonal phrases, set confidence < 0.65, needs_confirmation=true
- For completely unknown phrases, set resolved_date=null, confidence=0.1, needs_confirmation=true

IMPORTANT safety rules by context_type:
- goal_deadline / commitment_due_date: if not confident (< 0.7), set needs_confirmation=true
- transaction_date: if past phrase is unresolvable, today is acceptable with confidence=0.85
- NEVER silently turn an unknown future goal/commitment deadline into today
"""

_USER_TMPL = """\
Date phrase to resolve: "{raw_text}"

Full message context: {message}

Recent conversation:
{history}"""

_TRIVIAL_TODAY = {"today", "امروز", "همین امروز"}
_TRIVIAL_YESTERDAY = {"yesterday", "دیروز"}
_TRIVIAL_TOMORROW = {"tomorrow", "فردا"}


@dataclass
class DateResolution:
    raw_text: str | None
    resolved_date: date | None
    confidence: float
    date_kind: str
    interpretation_fa: str
    needs_confirmation: bool

    @classmethod
    def unresolved(cls, raw_text: str | None = None) -> "DateResolution":
        return cls(
            raw_text=raw_text,
            resolved_date=None,
            confidence=0.1,
            date_kind="unknown",
            interpretation_fa="نامشخص",
            needs_confirmation=True,
        )

    @classmethod
    def today_resolution(cls, raw_text: str | None = None) -> "DateResolution":
        return cls(
            raw_text=raw_text,
            resolved_date=local_today(),
            confidence=0.99,
            date_kind="today",
            interpretation_fa="امروز",
            needs_confirmation=False,
        )


class LLMDateResolver:
    """Resolves natural-language date phrases through the LLM.

    Falls back to trivial deterministic parsing for obvious cases (ISO, today,
    yesterday) to avoid unnecessary LLM calls.
    """

    async def resolve(
        self,
        raw_date_text: str,
        user_message: str = "",
        history: list[dict] | None = None,
        current_date: date | None = None,
        financial_context_type: str = "transaction_date",
        pending_intent: dict | None = None,
    ) -> DateResolution:
        today = current_date or local_today()
        clean = raw_date_text.strip().lower().replace("‌", " ")

        # Fast path: trivial deterministic cases that don't need LLM
        if not clean:
            return DateResolution.today_resolution(raw_date_text) if financial_context_type == "transaction_date" else DateResolution.unresolved(raw_date_text)
        if clean in _TRIVIAL_TODAY:
            return DateResolution.today_resolution(raw_date_text)
        if clean in _TRIVIAL_YESTERDAY:
            from datetime import timedelta
            return DateResolution(
                raw_text=raw_date_text, resolved_date=today - timedelta(days=1),
                confidence=0.99, date_kind="past", interpretation_fa="دیروز", needs_confirmation=False,
            )
        if clean in _TRIVIAL_TOMORROW:
            from datetime import timedelta
            return DateResolution(
                raw_text=raw_date_text, resolved_date=today + timedelta(days=1),
                confidence=0.99, date_kind="future", interpretation_fa="فردا", needs_confirmation=False,
            )
        try:
            parsed = date.fromisoformat(clean)
            return DateResolution(
                raw_text=raw_date_text, resolved_date=parsed,
                confidence=0.99, date_kind="future" if parsed >= today else "past",
                interpretation_fa=f"تاریخ مشخص {parsed.isoformat()}",
                needs_confirmation=False,
            )
        except (ValueError, TypeError):
            pass

        # LLM resolution for natural language
        tz_obj = app_timezone()
        tz = str(getattr(tz_obj, "key", "Asia/Tehran"))

        pending_context: str
        if pending_intent:
            pending_context = json.dumps(
                {k: v for k, v in pending_intent.items() if k in {"state", "item_title"}},
                ensure_ascii=False,
            )
        else:
            pending_context = "none"

        history_lines: list[str] = []
        if history:
            for item in (history or [])[-4:]:
                if item.get("role") in {"user", "assistant"} and item.get("content"):
                    label = "کاربر" if item["role"] == "user" else "دستیار"
                    history_lines.append(f"[{label}]: {str(item['content'])[:200]}")

        system_prompt = _SYSTEM.format(
            current_date=today.isoformat(),
            timezone=tz,
            context_type=financial_context_type,
            pending_context=pending_context,
        )
        user_content = _USER_TMPL.format(
            raw_text=raw_date_text,
            message=str(user_message)[:500],
            history="\n".join(history_lines) if history_lines else "(none)",
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            raw = await get_ai_chat_completion(messages, require_json=True)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return DateResolution.unresolved(raw_date_text)

            resolved_date: date | None = None
            if data.get("resolved_date"):
                try:
                    resolved_date = date.fromisoformat(str(data["resolved_date"]))
                except (ValueError, TypeError):
                    pass

            result = DateResolution(
                raw_text=data.get("raw_text", raw_date_text),
                resolved_date=resolved_date,
                confidence=float(data.get("confidence", 0.5)),
                date_kind=str(data.get("date_kind", "unknown")),
                interpretation_fa=str(data.get("interpretation_fa", "")),
                needs_confirmation=bool(data.get("needs_confirmation", False)),
            )
            logger.debug(
                "llm_date_resolver %r → %s (conf=%.2f, confirm=%s) [%s]",
                raw_date_text,
                result.resolved_date,
                result.confidence,
                result.needs_confirmation,
                result.interpretation_fa,
            )
            return result
        except (LLMProviderError, json.JSONDecodeError, Exception) as exc:
            logger.debug("LLMDateResolver failed for %r: %s", raw_date_text, exc)
            return DateResolution.unresolved(raw_date_text)
