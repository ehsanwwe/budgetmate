"""Goal intake decision gate + financial advisory conversation mode — Phase 5.8.

State machine for goal-like purchase/saving intents:

  collecting_amount → collecting_target_date → awaiting_user_choice → consumed
                                                                    ↘ consultation_active → consumed

ARCHITECTURE NOTE:
GoalIntakeGate is a thin pending-state manager. Semantic routing decisions
(cancel, bypass, intent classification) come from SemanticInterpreter, which is
called by the orchestrator BEFORE this gate. The gate uses the pre-computed
SemanticResult instead of its own keyword lists as the primary decision maker.

_CANCEL_KEYWORDS is kept as a tiny emergency guard for when semantic is unavailable.
LLM calls inside the gate are for data extraction (amount, date) and advisory, not
for primary intent classification.
"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.models.agent_idempotency import PendingAgentIntent
from app.models.goal import Goal
from app.models.user import User
from app.services.agent_orchestrator.date_utils import local_today, parse_relative_date
from app.services.agent_orchestrator.llm_date_resolver import LLMDateResolver
from app.services.agent_orchestrator.types import AgentFinalResponse
from app.services.agent_orchestrator.value_normalizer import normalize_amount
from app.services.ai import LLMProviderError, get_ai_chat_completion
from app.services.agent_orchestrator.persian_utils import to_persian_digits

if TYPE_CHECKING:
    from app.services.agent_orchestrator.semantic_interpreter import SemanticResult

logger = logging.getLogger(__name__)

GOAL_INTENT_TYPE = "goal_intake_pending"


class NullGoalIntakeGate:
    """No-op gate for tests that focus on orchestrator internals, not the intake flow."""
    async def process(self, *args, **kwargs) -> None:
        return None

# State constants
STATE_COLLECTING_AMOUNT = "collecting_amount"
STATE_COLLECTING_DATE = "collecting_target_date"
STATE_AWAITING_CHOICE = "awaiting_user_choice"
STATE_CONSULTATION = "consultation_active"
STATE_CONSUMED = "consumed"
STATE_CANCELLED = "cancelled"

# ── Detection / extraction prompts ───────────────────────────────────────────

_DETECTION_SYSTEM = (
    "تشخیص دقیق نوع پیام مالی فارسی. فقط JSON برگردان."
)

_DETECTION_USER_TMPL = """پیام کاربر: {message}

JSON زیر را برگردان (هیچ متن اضافه‌ای نگذار):
{{
  "is_goal_like": true/false,
  "is_explicit_add": true/false,
  "is_commitment": true/false,
  "is_transaction": true/false,
  "item_title": "عنوان کالا یا null",
  "amount": number_or_null,
  "target_date_text": "متن تاریخ هدف یا null"
}}

تعریف‌ها:
- is_goal_like=true: کاربر آرزو/قصد خرید یا پس‌انداز دارد ولی تعهد قطعی ندارد
  (میخوام بخرم، قصد دارم، میخوام پس‌انداز کنم، دوست دارم بخرم، هدفم اینه که بخرم)
- is_explicit_add=true: صراحتاً «یک هدف اضافه کن» یا «ثبت کن به عنوان هدف» + مبلغ + تاریخ
- is_commitment=true: تعهد پرداخت قطعی (چک دارم، قسط دارم، باید کرایه بدهم، بدهی دارم)
- is_transaction=true: پرداخت/دریافت انجام شده (خریدم، دادم، پرداخت کردم، پولش اومد)
- amount: مبلغ به تومان به صورت عدد صحیح، بدون واحد
- target_date_text: متن تاریخ هدف اگر ذکر شده (مثل «آخر سال»، «ماه بعد»، «تا خرداد»)

مثال‌های is_explicit_add=true:
  «یک هدف جدید اضافه کن برای خرید ساعت ۸۰ میلیون تا آخر سال»
  «به اهداف مالیم اضافه کن: لپتاپ، ۲۰۰ میلیون، ۶ ماه دیگه»

مثال‌های is_goal_like=true, is_explicit_add=false:
  «میخوام انگشتر طلا بخرم»
  «قصد دارم لپتاپ بخرم»
  «میخوام ماشین بخرم به مبلغ ۵۰۰ میلیون تا آخر سال»
  «رینگ اسپورت میخام بخرم ماه آینده ۲۰۰ میلیون»"""

_EXTRACTION_SYSTEM = "استخراج مبلغ و تاریخ از پیام. فقط JSON برگردان."

_EXTRACTION_USER_TMPL = """پیام: {message}

JSON:
{{"amount": number_or_null, "target_date_text": "string_or_null"}}

amount: مبلغ به تومان (عدد صحیح) یا null
target_date_text: متن تاریخ (مثل «آخر سال»، «ماه بعد»، «تا خرداد») یا null"""

_ADVISORY_SYSTEM = """شما Personal CFO (مدیر مالی شخصی) هستید.
چهار نقش دارید: مدیر مالی، روانشناس مالی، برنامه‌ریز مالی بلندمدت، دستیار تصمیم مالی.

قوانین پاسخ:
- پاسخ به فارسی، کوتاه (یک پاراگراف)
- همدلانه، بدون قضاوت، بدون اعداد ساختگی
- اعداد فقط از داده‌های واقعی ارائه‌شده
- اگر ماه‌های باقی‌مانده مشخص است، پس‌انداز ماهانه لازم محاسبه کن
- یک سوال مفید و کوتاه در پایان بپرس
- هدف را ثبت نکن؛ فقط مشاوره بده"""

# Emergency cancel guard — used ONLY when SemanticInterpreter result is unavailable.
# Do not expand this list. Primary cancel detection is SemanticResult.should_cancel_pending_flow.
_CANCEL_KEYWORDS_EMERGENCY = {
    "ولش کن", "ول کن", "بی‌خیال", "بیخیال", "منصرف شدم", "نمی‌خوام",
    "نمیخوام", "فراموشش کن", "فراموش کن", "لغو", "کنسل", "cancel",
    "نه ولش", "بذار بره", "ولم کن", "بیخیالش",
}


def _fmt_toman(amount: int | None) -> str:
    if not amount:
        return "مبلغ نامشخص"
    return to_persian_digits(f"{int(amount):,} تومان")


def _months_between(today: date, date_text: str | None) -> int | None:
    """Estimate months between today and target_date_text (for advisory only)."""
    if not date_text:
        return None
    try:
        # Uses parse_relative_date only as an approximation for advisory display.
        target = parse_relative_date(date_text)
        delta_days = (target - today).days
        if delta_days <= 0:
            return None
        return max(1, round(delta_days / 30))
    except Exception:
        return None


# ── GoalIntakeGate ────────────────────────────────────────────────────────────

class GoalIntakeGate:
    """Pre-orchestrator gate that manages the goal intake state machine.

    Returns AgentFinalResponse when it handles the message.
    Returns None when the message should pass through to the main orchestrator.

    Routing decisions (cancel, bypass, goal_question detection) use the
    SemanticResult from SemanticInterpreter. Keyword lists are emergency backups.
    """

    async def process(
        self,
        db: Session,
        user: User,
        user_message: str,
        history: list[dict] | None,
        finance_context: dict,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse | None:
        # 1. Active pending intent → routing through semantic, then state machine
        active_intent = self._get_active_intent(db, user)
        if active_intent:
            # Semantic-first routing (requires LLM result from orchestrator)
            if semantic is not None:
                if semantic.should_cancel_pending_flow:
                    self._cancel_stale_intents(db, user)
                    return AgentFinalResponse(
                        message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                        metadata={"goal_intake_state": STATE_CANCELLED},
                    )
                # User is asking about an existing goal, not answering our question
                if semantic.user_intent == "goal_question":
                    # Pass through so orchestrator/planner can answer from saved goals
                    return None
                # Clearly unrelated message — pass through
                if semantic.should_bypass_goal_intake:
                    return None
                if semantic.user_intent in {"expense", "income", "future_commitment"}:
                    # User registered a different transaction; cancel stale intent
                    self._cancel_stale_intents(db, user)
                    return None
            else:
                # Emergency keyword guard when semantic unavailable
                if self._is_cancellation_emergency(user_message):
                    self._cancel_stale_intents(db, user)
                    return AgentFinalResponse(
                        message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                        metadata={"goal_intake_state": STATE_CANCELLED},
                    )

            return await self._handle_active_intent(
                db, user, user_message, active_intent, history, finance_context, semantic=semantic
            )

        # 2. No active intent → detect if goal-like
        # Use semantic intent if available to avoid an extra LLM detection call
        if semantic is not None:
            intent_str = semantic.user_intent
            if intent_str in {
                "expense", "income", "future_commitment", "explicit_goal_add",
                "goal_question", "advice_question", "budget_question",
                "cancel_flow", "other", "answer_pending_question",
            }:
                return None  # Pass through to orchestrator

            if intent_str == "goal_desire":
                # Extract item title — try semantic first, fall back to LLM detection
                item_title = semantic.target_item or ""
                if not item_title:
                    detection = await self._detect(user_message)
                    if not detection:
                        return None
                    item_title = str(detection.get("item_title") or "").strip()
                if not item_title:
                    return None

                amount = semantic.money_amount
                target_date_text = semantic.date_raw_text
                if amount is None or target_date_text is None:
                    # Fill gaps from detection if needed
                    detection = await self._detect(user_message)
                    if detection:
                        if amount is None:
                            amount = detection.get("amount")
                        if target_date_text is None:
                            target_date_text = detection.get("target_date_text")

                self._cancel_stale_intents(db, user)
                return self._start_intake(db, user, user_message, item_title, amount, target_date_text)

            # invalid_both_choice or unknown — pass through
            return None

        # No semantic — fall back to LLM detection (original behavior)
        detection = await self._detect(user_message)
        if not detection:
            return None

        if detection.get("is_commitment") or detection.get("is_transaction"):
            return None
        if not detection.get("is_goal_like"):
            return None
        if detection.get("is_explicit_add"):
            return None

        item_title = str(detection.get("item_title") or "").strip()
        if not item_title:
            return None

        amount: int | None = detection.get("amount")
        target_date_text: str | None = detection.get("target_date_text")
        self._cancel_stale_intents(db, user)
        return self._start_intake(db, user, user_message, item_title, amount, target_date_text)

    # ── Active-intent handlers ────────────────────────────────────────────────

    async def _handle_active_intent(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None,
        finance_context: dict,
        *,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse | None:
        state = intent.payload_json.get("state")

        if state == STATE_COLLECTING_AMOUNT:
            return await self._collect_amount(db, user, user_message, intent, history, semantic=semantic)
        if state == STATE_COLLECTING_DATE:
            return await self._collect_date(db, user, user_message, intent, history, semantic=semantic)
        if state == STATE_AWAITING_CHOICE:
            return await self._awaiting_choice(db, user, user_message, intent, history, finance_context, semantic=semantic)
        if state == STATE_CONSULTATION:
            return await self._consultation(db, user, user_message, intent, history, finance_context, semantic=semantic)
        return None

    def _is_cancellation_emergency(self, text: str) -> bool:
        """Emergency keyword guard — only for when SemanticInterpreter result is unavailable."""
        cleaned = text.strip().lower().replace("‌", " ")
        return any(kw in cleaned for kw in _CANCEL_KEYWORDS_EMERGENCY)

    def _amount_from_history(self, history: list[dict] | None, item_title: str) -> int | None:
        """Scan recent history for an amount mentioned near the goal title."""
        if not history:
            return None
        title_lower = item_title.lower()
        for msg in reversed(history[-10:]):
            content = str(msg.get("content") or "")
            if title_lower in content.lower() or any(
                kw in content for kw in ["میلیون", "هزار", "تومان"]
            ):
                amount = self._try_extract_amount(content)
                if amount is not None:
                    return amount
        return None

    async def _collect_amount(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None = None,
        *,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse | None:
        payload = intent.payload_json
        item_title = payload.get("item_title", "آن خرید")

        # Semantic-first cancel check (emergency keyword fallback when semantic unavailable)
        if (semantic is not None and semantic.should_cancel_pending_flow) or \
           (semantic is None and self._is_cancellation_emergency(user_message)):
            self._cancel_stale_intents(db, user)
            return AgentFinalResponse(
                message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                metadata={"goal_intake_state": STATE_CANCELLED},
            )

        # Try to get amount from semantic interpreter first (avoids extra LLM call)
        amount: int | None = None
        if semantic is not None:
            amount = semantic.money_amount

        # User claims they already said it — check history
        if amount is None and any(kw in user_message for kw in ["قبلاً گفتم", "قبلا گفتم", "گفتم", "گفته بودم", "همین چت"]):
            amount = self._amount_from_history(history, item_title)

        # Fall back to direct extraction from message
        if amount is None:
            amount = self._try_extract_amount(user_message)
        if amount is None:
            extraction = await self._extract_values(user_message)
            amount = extraction.get("amount")

        if amount is None:
            # Check if user switched topics
            if semantic is not None and semantic.user_intent in {"expense", "income", "future_commitment"}:
                self._cancel_stale_intents(db, user)
                return None
            detection = await self._detect(user_message)
            if detection and (detection.get("is_commitment") or detection.get("is_transaction")):
                self._cancel_stale_intents(db, user)
                return None
            if detection and detection.get("is_goal_like") and detection.get("item_title"):
                new_title = str(detection.get("item_title") or "").strip()
                if new_title and new_title.lower() != (payload.get("item_title") or "").lower():
                    self._cancel_stale_intents(db, user)
                    new_amount = detection.get("amount")
                    new_date = detection.get("target_date_text")
                    return self._start_intake(db, user, user_message, new_title, new_amount, new_date)
            return AgentFinalResponse(
                message=f"مبلغ مورد نظر برای {item_title} را بگو — مثلاً «۱۰۰ میلیون».",
                metadata={"goal_intake_state": STATE_COLLECTING_AMOUNT, "intent_id": intent.id},
            )

        # Got amount — check if date also in same message
        date_text: str | None = None
        if semantic is not None:
            date_text = semantic.date_raw_text
        if not date_text:
            extraction = await self._extract_values(user_message)
            date_text = extraction.get("target_date_text")

        if date_text:
            self._update_intent(db, intent, {"target_amount": amount, "target_date_text": date_text}, STATE_AWAITING_CHOICE)
            return self._ask_add_or_consult(payload.get("item_title", item_title), amount, date_text, intent.id)

        self._update_intent(db, intent, {"target_amount": amount}, STATE_COLLECTING_DATE)
        return AgentFinalResponse(
            message="تا چه زمانی می‌خواهی به این خرید برسی؟",
            metadata={"goal_intake_state": STATE_COLLECTING_DATE, "intent_id": intent.id},
        )

    async def _collect_date(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None = None,
        *,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse | None:
        payload = intent.payload_json

        if (semantic is not None and semantic.should_cancel_pending_flow) or \
           (semantic is None and self._is_cancellation_emergency(user_message)):
            self._cancel_stale_intents(db, user)
            return AgentFinalResponse(
                message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                metadata={"goal_intake_state": STATE_CANCELLED},
            )

        # Extract date text — semantic first, then LLM extraction
        date_text: str | None = None
        if semantic is not None:
            date_text = semantic.date_raw_text
        if not date_text:
            extraction = await self._extract_values(user_message)
            date_text = extraction.get("target_date_text")

        if date_text is None:
            if semantic is not None and semantic.user_intent in {"expense", "income", "future_commitment"}:
                self._cancel_stale_intents(db, user)
                return None
            detection = await self._detect(user_message)
            if detection and (detection.get("is_commitment") or detection.get("is_transaction")):
                self._cancel_stale_intents(db, user)
                return None
            return AgentFinalResponse(
                message="تا چه زمانی می‌خواهی به این خرید برسی؟ مثلاً «آخر سال» یا «۶ ماه دیگه».",
                metadata={"goal_intake_state": STATE_COLLECTING_DATE, "intent_id": intent.id},
            )

        self._update_intent(db, intent, {"target_date_text": date_text}, STATE_AWAITING_CHOICE)
        item_title = payload.get("item_title", "این خرید")
        amount = payload.get("target_amount")
        return self._ask_add_or_consult(item_title, amount, date_text, intent.id)

    async def _awaiting_choice(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None,
        finance_context: dict,
        *,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse:
        payload = intent.payload_json

        # Cancel check — semantic primary, keyword emergency backup
        if (semantic is not None and semantic.should_cancel_pending_flow) or \
           (semantic is None and self._is_cancellation_emergency(user_message)):
            self._cancel_stale_intents(db, user)
            return AgentFinalResponse(
                message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                metadata={"goal_intake_state": STATE_CANCELLED},
            )

        # Determine choice: semantic "invalid_both_choice" → "both", else call LLM classifier
        if semantic is not None and semantic.user_intent == "invalid_both_choice":
            choice = "both"
        else:
            choice = await self._classify_choice(user_message)

        if choice == "both":
            return await self._handle_both_choice(db, user, intent, payload)

        if choice == "add":
            return await self._insert_goal_from_intent(db, user, intent, payload, user_message, history)
        if choice == "consult":
            self._update_intent(db, intent, {}, STATE_CONSULTATION)
            advisory = await self._generate_advisory(user_message, payload, finance_context, history)
            return AgentFinalResponse(
                message=advisory,
                metadata={"goal_intake_state": STATE_CONSULTATION, "intent_id": intent.id},
            )
        # ambiguous — rephrase to avoid word-for-word repeat
        return AgentFinalResponse(
            message="برای ادامه یکی رو انتخاب کن: «ثبتش کن» یا «اول مشاوره بده».",
            metadata={"goal_intake_state": STATE_AWAITING_CHOICE, "intent_id": intent.id},
        )

    async def _handle_both_choice(
        self,
        db: Session,
        user: User,
        intent: PendingAgentIntent,
        payload: dict,
    ) -> AgentFinalResponse:
        """Handle repeated 'both' choices with escalating responses and auto-cancel at count 3."""
        count = int(payload.get("invalid_both_count", 0)) + 1

        if count >= 3:
            # Third time: cancel the pending flow entirely
            self._cancel_stale_intents(db, user)
            return AgentFinalResponse(
                message=(
                    "برای اینکه این مرحله دور خودش نچرخه، فعلاً این تصمیم رو کنار گذاشتم. "
                    "هر وقت خواستی می‌تونی دوباره بگی ثبتش کنم یا مشاوره می‌خوام."
                ),
                metadata={"goal_intake_state": STATE_CANCELLED},
            )

        # Update count in payload (state stays awaiting_user_choice)
        self._update_intent(db, intent, {"invalid_both_count": count}, STATE_AWAITING_CHOICE)

        msg = await self._generate_both_response(payload, count)
        return AgentFinalResponse(
            message=msg,
            metadata={
                "goal_intake_state": STATE_AWAITING_CHOICE,
                "intent_id": intent.id,
                "invalid_both_count": count,
            },
        )

    async def _consultation(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None,
        finance_context: dict,
        *,
        semantic: "SemanticResult | None" = None,
    ) -> AgentFinalResponse:
        payload = intent.payload_json

        if (semantic is not None and semantic.should_cancel_pending_flow) or \
           (semantic is None and self._is_cancellation_emergency(user_message)):
            self._cancel_stale_intents(db, user)
            return AgentFinalResponse(
                message="باشه، این مورد رو کنار گذاشتم. چیزی ثبت نشد.",
                metadata={"goal_intake_state": STATE_CANCELLED},
            )

        choice = await self._classify_choice(user_message)
        if choice == "add":
            return await self._insert_goal_from_intent(db, user, intent, payload, user_message, history)

        advisory = await self._generate_advisory(user_message, payload, finance_context, history)
        return AgentFinalResponse(
            message=advisory,
            metadata={"goal_intake_state": STATE_CONSULTATION, "intent_id": intent.id},
        )

    # ── Goal insertion ────────────────────────────────────────────────────────

    async def _insert_goal_from_intent(
        self,
        db: Session,
        user: User,
        intent: PendingAgentIntent,
        payload: dict,
        user_message: str = "",
        history: list[dict] | None = None,
    ) -> AgentFinalResponse:
        item_title = str(payload.get("item_title") or "").strip()
        target_amount = payload.get("target_amount")
        target_date_text: str | None = payload.get("target_date_text")

        if not item_title or not target_amount:
            return AgentFinalResponse(
                message="برای ثبت هدف به عنوان و مبلغ نیاز است. لطفا دوباره مشخص کن.",
                metadata={"goal_intake_state": STATE_AWAITING_CHOICE, "intent_id": intent.id},
            )

        # Idempotency: check for existing active goal with same title + amount
        existing_id = self._find_existing_goal(db, user, item_title, int(target_amount))
        if existing_id is not None:
            self._consume_intent(db, intent)
            existing_goal = db.query(Goal).filter(Goal.id == existing_id).first()
            title_display = existing_goal.title if existing_goal else item_title
            return AgentFinalResponse(
                message=f"این هدف قبلاً ثبت شده بود؛ دوباره ثبت نکردم. هدف «{title_display}» در اهداف فعال شما وجود دارد.",
                operations_summary=["skipped duplicate goal"],
                metadata={"goal_intake_state": STATE_CONSUMED, "existing_goal_id": existing_id},
            )

        # Resolve deadline through LLMDateResolver (not parse_relative_date).
        # For goal deadlines, never silently fallback to today on unknown phrases.
        deadline: date | None = None
        if target_date_text:
            resolver = LLMDateResolver()
            resolution = await resolver.resolve(
                raw_date_text=target_date_text,
                user_message=user_message or payload.get("source_message", ""),
                history=history,
                current_date=local_today(),
                financial_context_type="goal_deadline",
                pending_intent=payload,
            )
            if resolution.resolved_date and not resolution.needs_confirmation:
                deadline = resolution.resolved_date
            elif resolution.resolved_date and resolution.confidence >= 0.65:
                # Moderate confidence — accept but log
                deadline = resolution.resolved_date
                logger.info(
                    "goal_intake accepting moderate-confidence date %s (conf=%.2f) for %r",
                    resolution.resolved_date,
                    resolution.confidence,
                    item_title,
                )
            else:
                # Low confidence or needs confirmation — ask user before writing
                self._consume_intent(db, intent)  # consume to avoid repeat asks
                return AgentFinalResponse(
                    message=(
                        f"مطمئن نشدم تاریخ هدف «{item_title}» رو درست فهمیدم. "
                        f"لطفاً تاریخ دقیق‌تری بده — مثلاً «آخر خرداد» یا «شش ماه دیگه»."
                    ),
                    metadata={"goal_intake_state": STATE_COLLECTING_DATE, "intent_id": intent.id},
                )

        goal = Goal(
            user_id=user.id,
            title=item_title[:200],
            target_amount=int(target_amount),
            current_amount=0,
            deadline=deadline,
            status="active",
            is_active=True,
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)

        self._consume_intent(db, intent)

        # Create monthly saving commitments for this goal
        commitment_suffix = ""
        try:
            commitment_count = self._create_saving_commitments(db, user, goal)
            if commitment_count > 0:
                installment_amount = round(goal.target_amount / commitment_count)
                commitment_suffix = to_persian_digits(
                    f" همچنین {commitment_count} تعهد پس‌انداز ماهانه "
                    f"{installment_amount:,} تومانی برای رسیدن به این هدف اضافه شد."
                )
        except Exception:
            logger.exception("goal_intake: failed to create saving commitments for goal %d", goal.id)
            commitment_suffix = " (ایجاد تعهدات پس‌انداز با خطا مواجه شد.)"

        deadline_text = to_persian_digits(f"، مهلت {goal.deadline.isoformat()}") if goal.deadline else ""
        return AgentFinalResponse(
            message=to_persian_digits(f"هدف «{goal.title}» با مبلغ {goal.target_amount:,} تومان{deadline_text} ثبت شد.") + commitment_suffix,
            operations_summary=["inserted goal"],
            metadata={"goal_intake_state": STATE_CONSUMED, "goal_id": goal.id},
        )

    # ── State machine helpers ─────────────────────────────────────────────────

    def _start_intake(
        self,
        db: Session,
        user: User,
        source_message: str,
        item_title: str,
        amount: int | None,
        target_date_text: str | None,
    ) -> AgentFinalResponse:
        if amount is None:
            intent = self._create_intent(db, user, source_message, item_title, None, None, STATE_COLLECTING_AMOUNT)
            return AgentFinalResponse(
                message=to_persian_digits(f"برای اینکه درست بررسی کنم، حدوداً چه مبلغی برای خرید {item_title} در نظر داری؟"),
                metadata={"goal_intake_state": STATE_COLLECTING_AMOUNT, "intent_id": intent.id},
            )
        if target_date_text is None:
            intent = self._create_intent(db, user, source_message, item_title, amount, None, STATE_COLLECTING_DATE)
            return AgentFinalResponse(
                message="تا چه زمانی می‌خواهی به این خرید برسی؟",
                metadata={"goal_intake_state": STATE_COLLECTING_DATE, "intent_id": intent.id},
            )
        intent = self._create_intent(db, user, source_message, item_title, amount, target_date_text, STATE_AWAITING_CHOICE)
        return self._ask_add_or_consult(item_title, amount, target_date_text, intent.id)

    def _ask_add_or_consult(
        self, item_title: str, amount: int | None, date_text: str, intent_id: int
    ) -> AgentFinalResponse:
        amount_fmt = _fmt_toman(amount)
        return AgentFinalResponse(
            message=to_persian_digits(
                f"اطلاعات کامل شد: {item_title}، {amount_fmt}، {date_text}. "
                "می‌خواهی این را به اهداف مالی‌ات اضافه کنم یا اول درباره منطقی بودنش "
                "با توجه به بودجه و هزینه‌هایت مشاوره بگیری؟"
            ),
            metadata={"goal_intake_state": STATE_AWAITING_CHOICE, "intent_id": intent_id},
        )

    def _get_active_intent(self, db: Session, user: User) -> PendingAgentIntent | None:
        return (
            db.query(PendingAgentIntent)
            .filter(
                PendingAgentIntent.user_id == user.id,
                PendingAgentIntent.intent_type == GOAL_INTENT_TYPE,
                PendingAgentIntent.status == "pending",
            )
            .order_by(PendingAgentIntent.updated_at.desc())
            .first()
        )

    def _create_intent(
        self,
        db: Session,
        user: User,
        source_message: str,
        item_title: str,
        amount: int | None,
        date_text: str | None,
        state: str,
    ) -> PendingAgentIntent:
        from app.services.personal_cfo.goal_context_service import normalize_goal_text
        payload: dict[str, Any] = {
            "item_title": item_title,
            "normalized_title": normalize_goal_text(item_title),
            "target_amount": amount,
            "target_date_text": date_text,
            "source_message": source_message[:500],
            "state": state,
        }
        intent = PendingAgentIntent(
            user_id=user.id,
            intent_type=GOAL_INTENT_TYPE,
            payload_json=payload,
            status="pending",
        )
        db.add(intent)
        db.commit()
        db.refresh(intent)
        return intent

    def _update_intent(
        self, db: Session, intent: PendingAgentIntent, updates: dict, new_state: str
    ) -> None:
        payload = dict(intent.payload_json or {})
        payload.update(updates)
        payload["state"] = new_state
        intent.payload_json = payload
        intent.updated_at = __import__("datetime").datetime.utcnow()
        db.commit()

    def _consume_intent(self, db: Session, intent: PendingAgentIntent) -> None:
        payload = dict(intent.payload_json or {})
        payload["state"] = STATE_CONSUMED
        intent.payload_json = payload
        intent.status = "consumed"
        intent.consumed_at = __import__("datetime").datetime.utcnow()
        db.commit()

    def _cancel_stale_intents(self, db: Session, user: User) -> None:
        stale = (
            db.query(PendingAgentIntent)
            .filter(
                PendingAgentIntent.user_id == user.id,
                PendingAgentIntent.intent_type == GOAL_INTENT_TYPE,
                PendingAgentIntent.status == "pending",
            )
            .all()
        )
        for intent in stale:
            payload = dict(intent.payload_json or {})
            payload["state"] = STATE_CANCELLED
            intent.payload_json = payload
            intent.status = "consumed"
        if stale:
            db.commit()

    def _find_existing_goal(self, db: Session, user: User, title: str, amount: int) -> int | None:
        from app.services.personal_cfo.goal_context_service import find_goal_candidates, goal_match_score
        candidates = find_goal_candidates(db, user.id, title)
        for candidate in candidates:
            score = goal_match_score(title, candidate.title or "")
            amounts_match = candidate.target_amount == amount
            if score >= 0.55 and amounts_match:
                return int(candidate.id)
        return None

    # ── LLM calls ────────────────────────────────────────────────────────────

    async def _detect(self, user_message: str) -> dict | None:
        """Detect intent type and extract structured info from a user message."""
        messages = [
            {"role": "system", "content": _DETECTION_SYSTEM},
            {"role": "user", "content": _DETECTION_USER_TMPL.format(message=user_message)},
        ]
        try:
            raw = await get_ai_chat_completion(messages, require_json=True)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            return data
        except (LLMProviderError, json.JSONDecodeError, Exception) as exc:
            logger.debug("goal_intake detect failed: %s", exc)
            return None

    async def _extract_values(self, user_message: str) -> dict:
        """Extract amount and target_date_text from a follow-up user message."""
        messages = [
            {"role": "system", "content": _EXTRACTION_SYSTEM},
            {"role": "user", "content": _EXTRACTION_USER_TMPL.format(message=user_message)},
        ]
        try:
            raw = await get_ai_chat_completion(messages, require_json=True)
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.debug("goal_intake extract failed: %s", exc)
            return {}

    async def _classify_choice(self, user_message: str) -> str:
        """Classify user's add/consult/both choice via LLM.

        Uses LLM directly — keyword lists are not the primary classifier since
        users express choices in unlimited ways. The LLM prompt includes examples.
        """
        system = "تشخیص انتخاب کاربر: ثبت هدف یا مشاوره. فقط یک کلمه برگردان."
        user_content = (
            f"کاربر باید بین ثبت هدف مالی یا مشاوره مالی انتخاب کند.\n\n"
            f"پیام کاربر: {user_message}\n\n"
            "فقط یکی از این چهار را برگردان (یک کلمه):\n"
            "- add      — اگر کاربر می‌خواهد ثبت/اضافه کند\n"
            "- consult  — اگر کاربر می‌خواهد مشاوره بگیرد\n"
            "- both     — اگر کاربر می‌خواهد هر دو\n"
            "- ambiguous — اگر مشخص نیست\n\n"
            "نمونه‌های ثبت: اضافه کن، ثبت کن، بله، آره، ok، باشه، بزن تو، هدفش کن\n"
            "نمونه‌های مشاوره: مشاوره، بررسی، به نظرت، منطقی، می‌صرفه، راهنمایی، نه اول، صبر کن\n"
            "نمونه‌های هر دو: هر دو، هردو، جفتش، هر دو تا، both"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        try:
            raw = await get_ai_chat_completion(messages, require_json=False)
            word = raw.strip().lower().split()[0] if raw.strip() else "ambiguous"
            if "both" in word:
                return "both"
            if "add" in word:
                return "add"
            if "consult" in word:
                return "consult"
            return "ambiguous"
        except Exception:
            return "ambiguous"

    async def _generate_advisory(
        self,
        user_message: str,
        payload: dict,
        finance_context: dict,
        history: list[dict] | None,
    ) -> str:
        item_title = payload.get("item_title", "این خرید")
        target_amount: int | None = payload.get("target_amount")
        date_text: str | None = payload.get("target_date_text")
        today = local_today()

        months_remaining = _months_between(today, date_text)
        monthly_saving = (
            round(target_amount / months_remaining)
            if target_amount and months_remaining and months_remaining > 0
            else None
        )

        goal_info = {
            "item": item_title,
            "target_amount_toman": target_amount,
            "target_date": date_text,
            "months_remaining": months_remaining,
            "required_monthly_saving": monthly_saving,
        }

        budget_amount = finance_context.get("budget") or 0
        spent = finance_context.get("total_spent_this_month") or 0
        income = finance_context.get("total_income_this_month") or 0
        remaining = finance_context.get("remaining_budget") or 0
        active_goals = finance_context.get("active_goals", [])
        commitments = finance_context.get("future_commitments", [])

        context_summary = {
            "monthly_budget": budget_amount,
            "spent_this_month": spent,
            "income_this_month": income,
            "remaining_budget": remaining,
            "active_goals_count": len(active_goals),
            "active_goals": [
                {"title": g.get("title"), "target_amount": g.get("target_amount"),
                 "remaining": g.get("remaining_amount")}
                for g in active_goals[:3]
            ],
            "upcoming_commitments": len(commitments),
        }

        user_content = (
            f"اطلاعات مالی کاربر:\n{json.dumps(context_summary, ensure_ascii=False)}\n\n"
            f"هدف در حال بررسی:\n{json.dumps(goal_info, ensure_ascii=False)}\n\n"
            f"تاریخ امروز: {today.isoformat()}\n\n"
            f"پیام کاربر: {user_message}"
        )

        messages: list[dict] = [{"role": "system", "content": _ADVISORY_SYSTEM}]
        if history:
            for item in history[-4:]:
                if item.get("role") in {"user", "assistant"} and item.get("content"):
                    messages.append({"role": item["role"], "content": str(item["content"])[:400]})
        messages.append({"role": "user", "content": user_content})

        try:
            return await get_ai_chat_completion(messages, require_json=False)
        except LLMProviderError:
            return (
                f"با توجه به وضعیت مالی فعلیت، خرید {item_title} "
                f"با مبلغ {_fmt_toman(target_amount)} نیاز به بررسی بیشتری دارد. "
                "آیا این خرید برایت ضروری است یا می‌تواند به بعد موکول شود؟"
            )

    async def _generate_both_response(self, payload: dict, count: int) -> str:
        """LLM-generated naturalized response for repeated 'both' choices."""
        item_title = payload.get("item_title", "این مورد")
        system = "دستیار مالی فارسی هستی. پاسخ کوتاه، طبیعی، و مودبانه بده. بدون عنوان یا مقدمه."

        if count == 1:
            user_content = (
                f"کاربر برای تصمیم ثبت یا مشاوره هدف «{item_title}» گفته «هر دو». "
                "به‌طور طبیعی توضیح بده که هم‌زمان هر دو ممکن نیست و باید اول یکی انتخاب کند. "
                "یک سوال ملایم در پایان بپرس. کوتاه باش (۲ جمله)."
            )
        else:
            user_content = (
                f"کاربر دوباره برای هدف «{item_title}» گفته «هر دو» — این دومین بار است. "
                "پاسخ کوتاه‌تر و صریح‌تر بده، متفاوت از پاسخ قبلی. "
                "بگو فقط یکی انتخاب کند: «ثبتش کن» یا «مشاوره می‌خوام». "
                "حداکثر یک جمله باش."
            )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]
        try:
            return await get_ai_chat_completion(messages, require_json=False)
        except LLMProviderError:
            if count == 1:
                return (
                    "متوجه‌ام، ولی برای این مرحله باید یکی رو انتخاب کنی. "
                    "می‌خوای این هدف رو ثبت کنم یا اول مشاوره بگیری؟"
                )
            return "لطفاً یکی انتخاب کن: «ثبتش کن» یا «مشاوره می‌خوام»."

    def _create_saving_commitments(self, db: Session, user: User, goal: Goal) -> int:
        """Create monthly saving commitments for a goal. Returns number created.

        Idempotent: skips creation if commitments with source=goal_saving_plan
        already exist for this goal.
        """
        from app.models.future_commitment import FutureCommitment

        if not goal.deadline or not goal.target_amount:
            return 0

        today = local_today()
        if goal.deadline <= today:
            return 0

        # Idempotency: skip if saving plan already exists for this goal
        existing = (
            db.query(FutureCommitment)
            .filter(
                FutureCommitment.related_goal_id == goal.id,
                FutureCommitment.user_id == user.id,
                FutureCommitment.source == "goal_saving_plan",
                FutureCommitment.status != "cancelled",
            )
            .count()
        )
        if existing > 0:
            logger.info("goal_intake: saving commitments already exist for goal %d, skipping", goal.id)
            return 0

        # Calculate month count
        delta_days = (goal.deadline - today).days
        month_count = max(1, round(delta_days / 30))

        base_amount = goal.target_amount // month_count
        remainder = goal.target_amount - (base_amount * month_count)

        created = 0
        for i in range(month_count):
            # Advance month-by-month from today, clamping to valid month days
            raw_month = today.month + i
            due_year = today.year + (raw_month - 1) // 12
            due_month = (raw_month - 1) % 12 + 1
            max_day = calendar.monthrange(due_year, due_month)[1]
            due_day = min(today.day, max_day)
            due_date = date(due_year, due_month, due_day)

            # Distribute remainder on the last installment to ensure exact sum
            installment_amount = base_amount + (remainder if i == month_count - 1 else 0)

            commitment = FutureCommitment(
                user_id=user.id,
                title=f"پس‌انداز خرید {goal.title}",
                amount=installment_amount,
                due_date=due_date,
                due_month=f"{due_year}-{due_month:02d}",
                related_goal_id=goal.id,
                source="goal_saving_plan",
                status="pending",
                description=f"قسط پس‌انداز برای هدف {goal.title}",
                metadata_json={
                    "installment_index": i + 1,
                    "installment_count": month_count,
                    "goal_title": goal.title,
                },
            )
            db.add(commitment)
            created += 1

        if created > 0:
            db.commit()

        return created

    # ── Amount extraction utility ─────────────────────────────────────────────

    def _try_extract_amount(self, text: str) -> int | None:
        """Try to extract an amount from text using normalize_amount."""
        try:
            amount = normalize_amount(text)
            if amount >= 1_000:
                return amount
            return None
        except Exception:
            return None
