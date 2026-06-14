"""Goal intake decision gate + financial advisory conversation mode — Phase 5.8.

State machine for goal-like purchase/saving intents:

  collecting_amount → collecting_target_date → awaiting_user_choice → consumed
                                                                    ↘ consultation_active → consumed
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models.agent_idempotency import PendingAgentIntent
from app.models.goal import Goal
from app.models.user import User
from app.services.agent_orchestrator.date_utils import local_today, parse_relative_date
from app.services.agent_orchestrator.types import AgentFinalResponse
from app.services.agent_orchestrator.value_normalizer import normalize_amount
from app.services.ai import LLMProviderError, get_ai_chat_completion

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

_CHOICE_SYSTEM = "تشخیص انتخاب کاربر: ثبت هدف یا مشاوره. فقط یک کلمه برگردان."

_CHOICE_USER_TMPL = """کاربر باید بین ثبت هدف مالی یا مشاوره مالی انتخاب کند.

پیام کاربر: {message}

فقط یکی از این سه را برگردان (یک کلمه):
- add   — اگر کاربر می‌خواهد ثبت/اضافه کند
- consult — اگر کاربر می‌خواهد مشاوره بگیرد
- ambiguous — اگر مشخص نیست

کلیدواژه‌های ثبت: اضافه کن، ثبت کن، بله، آره، بزن، هدفش کن، باشه ثبت، بزن تو، ok
کلیدواژه‌های مشاوره: مشاوره، بررسی، به نظرت، منطقی، می‌صرفه، راهنمایی، نه اول، صبر کن، فکر کن"""

_ADVISORY_SYSTEM = """شما Personal CFO (مدیر مالی شخصی) هستید.
چهار نقش دارید: مدیر مالی، روانشناس مالی، برنامه‌ریز مالی بلندمدت، دستیار تصمیم مالی.

قوانین پاسخ:
- پاسخ به فارسی، کوتاه (یک پاراگراف)
- همدلانه، بدون قضاوت، بدون اعداد ساختگی
- اعداد فقط از داده‌های واقعی ارائه‌شده
- اگر ماه‌های باقی‌مانده مشخص است، پس‌انداز ماهانه لازم محاسبه کن
- یک سوال مفید و کوتاه در پایان بپرس
- هدف را ثبت نکن؛ فقط مشاوره بده"""


def _fmt_toman(amount: int | None) -> str:
    if not amount:
        return "مبلغ نامشخص"
    return f"{int(amount):,} تومان"


def _months_between(today: date, date_text: str | None) -> int | None:
    """Estimate months between today and target_date_text."""
    if not date_text:
        return None
    try:
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
    """

    async def process(
        self,
        db: Session,
        user: User,
        user_message: str,
        history: list[dict] | None,
        finance_context: dict,
    ) -> AgentFinalResponse | None:
        # 1. Active pending intent → handle via state machine
        active_intent = self._get_active_intent(db, user)
        if active_intent:
            return await self._handle_active_intent(
                db, user, user_message, active_intent, history, finance_context
            )

        # 2. No active intent → detect if goal-like
        detection = await self._detect(user_message)
        if not detection:
            return None

        if detection.get("is_commitment") or detection.get("is_transaction"):
            return None  # commitment / transaction → pass to orchestrator

        if not detection.get("is_goal_like"):
            return None  # not goal-like → pass through

        if detection.get("is_explicit_add"):
            return None  # explicit "add goal with all details" → let orchestrator insert directly

        # 3. Goal-like (non-explicit) → start intake
        item_title = str(detection.get("item_title") or "").strip()
        if not item_title:
            return None  # can't extract title → pass through

        amount: int | None = detection.get("amount")
        target_date_text: str | None = detection.get("target_date_text")

        # Cancel stale intents from previous sessions
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
    ) -> AgentFinalResponse | None:
        state = intent.payload_json.get("state")

        if state == STATE_COLLECTING_AMOUNT:
            return await self._collect_amount(db, user, user_message, intent)
        if state == STATE_COLLECTING_DATE:
            return await self._collect_date(db, user, user_message, intent)
        if state == STATE_AWAITING_CHOICE:
            return await self._awaiting_choice(db, user, user_message, intent, history, finance_context)
        if state == STATE_CONSULTATION:
            return await self._consultation(db, user, user_message, intent, history, finance_context)
        return None

    async def _collect_amount(
        self, db: Session, user: User, user_message: str, intent: PendingAgentIntent
    ) -> AgentFinalResponse | None:
        payload = intent.payload_json
        item_title = payload.get("item_title", "آن خرید")

        amount = self._try_extract_amount(user_message)
        if amount is None:
            extraction = await self._extract_values(user_message)
            amount = extraction.get("amount")

        if amount is None:
            # Check if clearly unrelated (commitment / transaction)
            detection = await self._detect(user_message)
            if detection and (detection.get("is_commitment") or detection.get("is_transaction")):
                self._cancel_stale_intents(db, user)
                return None  # pass through
            if detection and detection.get("is_goal_like") and detection.get("item_title"):
                new_title = str(detection.get("item_title") or "").strip()
                if new_title and new_title.lower() != (payload.get("item_title") or "").lower():
                    # New goal-like message → restart intake
                    self._cancel_stale_intents(db, user)
                    new_amount = detection.get("amount")
                    new_date = detection.get("target_date_text")
                    return self._start_intake(db, user, user_message, new_title, new_amount, new_date)
            return AgentFinalResponse(
                message=f"مبلغ مورد نظر برای {item_title} را بگو — مثلاً «۱۰۰ میلیون».",
                metadata={"goal_intake_state": STATE_COLLECTING_AMOUNT, "intent_id": intent.id},
            )

        # Got amount — check if date also in same message
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
        self, db: Session, user: User, user_message: str, intent: PendingAgentIntent
    ) -> AgentFinalResponse | None:
        payload = intent.payload_json

        extraction = await self._extract_values(user_message)
        date_text = extraction.get("target_date_text")

        if date_text is None:
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
    ) -> AgentFinalResponse:
        payload = intent.payload_json
        choice = await self._classify_choice(user_message)

        if choice == "add":
            return self._insert_goal_from_intent(db, user, intent, payload)
        if choice == "consult":
            self._update_intent(db, intent, {}, STATE_CONSULTATION)
            advisory = await self._generate_advisory(user_message, payload, finance_context, history)
            return AgentFinalResponse(
                message=advisory,
                metadata={"goal_intake_state": STATE_CONSULTATION, "intent_id": intent.id},
            )
        # ambiguous
        return AgentFinalResponse(
            message="می‌خواهی ثبتش کنم یا اول مشاوره بگیری؟",
            metadata={"goal_intake_state": STATE_AWAITING_CHOICE, "intent_id": intent.id},
        )

    async def _consultation(
        self,
        db: Session,
        user: User,
        user_message: str,
        intent: PendingAgentIntent,
        history: list[dict] | None,
        finance_context: dict,
    ) -> AgentFinalResponse:
        payload = intent.payload_json
        choice = await self._classify_choice(user_message)
        if choice == "add":
            return self._insert_goal_from_intent(db, user, intent, payload)

        advisory = await self._generate_advisory(user_message, payload, finance_context, history)
        return AgentFinalResponse(
            message=advisory,
            metadata={"goal_intake_state": STATE_CONSULTATION, "intent_id": intent.id},
        )

    # ── Goal insertion ────────────────────────────────────────────────────────

    def _insert_goal_from_intent(
        self, db: Session, user: User, intent: PendingAgentIntent, payload: dict
    ) -> AgentFinalResponse:
        item_title = str(payload.get("item_title") or "").strip()
        target_amount = payload.get("target_amount")
        target_date_text = payload.get("target_date_text")

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

        # Parse deadline
        deadline: date | None = None
        if target_date_text:
            try:
                deadline = parse_relative_date(target_date_text)
            except Exception:
                deadline = None

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

        deadline_text = f"، مهلت {goal.deadline.isoformat()}" if goal.deadline else ""
        return AgentFinalResponse(
            message=f"هدف «{goal.title}» با مبلغ {goal.target_amount:,} تومان{deadline_text} ثبت شد.",
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
                message=f"برای اینکه درست بررسی کنم، حدوداً چه مبلغی برای خرید {item_title} در نظر داری؟",
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
            message=(
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
        """Classify user's add/consult choice. Returns 'add', 'consult', or 'ambiguous'."""
        # Fast keyword-based classification first
        text = user_message.strip().lower().replace("‌", " ")
        add_kw = ["اضافه کن", "ثبت کن", "بزن تو اهداف", "هدفش کن", "ثبتش کن",
                  "به هدف", "بزن", "آره", "بله", "ok", "اوکی", "باشه ثبت"]
        consult_kw = ["مشاوره", "بررسی کن", "بررسیش کن", "به نظرت", "منطقیه",
                      "می‌صرفه", "میصرفه", "راهنمایی", "نه اول", "اول مشاوره",
                      "نظرت", "صبر کن", "فکر کن"]
        if any(kw in text for kw in add_kw):
            return "add"
        if any(kw in text for kw in consult_kw):
            return "consult"

        # LLM fallback for ambiguous cases
        messages = [
            {"role": "system", "content": _CHOICE_SYSTEM},
            {"role": "user", "content": _CHOICE_USER_TMPL.format(message=user_message)},
        ]
        try:
            raw = await get_ai_chat_completion(messages, require_json=False)
            word = raw.strip().lower().split()[0] if raw.strip() else "ambiguous"
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

        # Build compact finance summary for advisory
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

    # ── Amount extraction utility ─────────────────────────────────────────────

    def _try_extract_amount(self, text: str) -> int | None:
        """Try to extract an amount from text using normalize_amount."""
        try:
            amount = normalize_amount(text)
            if amount >= 1_000:  # min reasonable amount
                return amount
            return None
        except Exception:
            return None
