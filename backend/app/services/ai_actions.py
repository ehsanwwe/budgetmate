"""Post-processing for AI replies: extract JSON action blocks, execute them, strip from visible text."""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.core.jalali import current_jalali_month, gregorian_to_jalali
from app.models.budget import Budget
from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

logger = logging.getLogger(__name__)

_ACTION_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S | re.IGNORECASE)

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "create_transaction": ["amount", "type", "category"],
    "create_goal": ["title", "target_amount"],
    "set_budget": ["amount"],
    "set_income": ["amount"],
}


def _jalali_to_gregorian_date(jalali_str: str) -> Optional[date]:
    """Convert YYYY-MM-DD Jalali string to Python date. Returns None on failure."""
    try:
        parts = jalali_str.strip().split("-")
        jy, jm, jd = int(parts[0]), int(parts[1]), int(parts[2])
        # Reuse existing jalali helper (it returns gy, days — need full conversion)
        # Inline the full conversion here to avoid importing a private helper.
        jy += 1595
        raw_days = (
            -355779
            + (365 + _leap(jy)) * (jy // 2820 * 2820)
            + (365 + _leap(jy % 2820 + 474)) * ((jy % 2820) // 4 * 4)
            + (365 + _leap(jy % 4 + (jy % 2820) // 4 * 4)) * (jy % 4)
            + (30 * jm - (jm - (1 if jm <= 6 else 7)))
            + jd
        )
        gy = 400 * (raw_days // 146097)
        raw_days %= 146097
        if raw_days > 36524:
            raw_days -= 1
            gy += 100 * (raw_days // 36524)
            raw_days %= 36524
            if raw_days >= 365:
                raw_days += 1
        gy += 4 * (raw_days // 1461)
        raw_days %= 1461
        if raw_days > 365:
            gy += (raw_days - 1) // 365
            raw_days = (raw_days - 1) % 365
        # raw_days is now day-of-year (0-based)
        month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if gy % 4 == 0 and (gy % 100 != 0 or gy % 400 == 0):
            month_days[1] = 29
        gm = 1
        for md in month_days:
            if raw_days < md:
                gd = raw_days + 1
                return date(gy, gm, gd)
            raw_days -= md
            gm += 1
        return None
    except Exception:
        return None


def _leap(year: int) -> bool:
    return ((year - 474) % 2820 + 474 + 38) * 682 % 2816 < 682


def _deadline_from_jalali(deadline_val) -> Optional[date]:
    if not deadline_val or deadline_val == "null":
        return None
    if isinstance(deadline_val, str):
        return _jalali_to_gregorian_date(deadline_val)
    return None


def extract_actions(reply_text: str) -> tuple[str, list[dict]]:
    """Return (cleaned_text, list_of_action_dicts). Malformed/incomplete blocks are skipped."""
    actions: list[dict] = []
    cleaned = reply_text

    for match in _ACTION_BLOCK_RE.finditer(reply_text):
        raw_json = match.group(1)
        try:
            action = json.loads(raw_json)
            if not isinstance(action, dict) or "action" not in action:
                continue
            action_type = action["action"]
            required = _REQUIRED_FIELDS.get(action_type, [])
            if not all(k in action for k in required):
                logger.debug("Skipping action %s: missing required fields %s", action_type, required)
                cleaned = cleaned.replace(match.group(0), "", 1)
                continue
            actions.append(action)
            cleaned = cleaned.replace(match.group(0), "", 1)
        except (json.JSONDecodeError, ValueError):
            logger.debug("Skipping malformed action block: %s", raw_json[:200])

    cleaned = cleaned.strip()
    return cleaned, actions


def _fmt(amount: int) -> str:
    return f"{amount:,} تومان"


def _find_category(persian_name: str, db: Session, user_id: int) -> Optional[Category]:
    name_clean = persian_name.strip()
    cats = db.query(Category).filter(
        (Category.is_default == True) | (Category.user_id == user_id)
    ).all()
    for cat in cats:
        if cat.name.strip() == name_clean:
            return cat
    # fuzzy: substring match
    for cat in cats:
        if name_clean in cat.name or cat.name in name_clean:
            return cat
    return None


def execute_action(action: dict, db: Session, user: User) -> dict:
    kind = action.get("action", "")
    try:
        if kind == "create_goal":
            title = str(action.get("title", "هدف جدید"))
            target = int(action.get("target_amount", 0))
            if target < 100000:
                logger.warning("Rejected create_goal: target_amount=%s is below 100000", target)
                return {"ok": False, "reason": f"مبلغ هدف {target} تومان معقول نیست. حداقل ۱۰۰٬۰۰۰ تومان لازم است."}
            deadline = _deadline_from_jalali(action.get("deadline"))
            goal = Goal(user_id=user.id, title=title, target_amount=target, current_amount=0, deadline=deadline)
            db.add(goal)
            db.commit()
            return {"ok": True, "confirmation": f"✅ هدف «{title}» با مبلغ {_fmt(target)} ثبت شد."}

        if kind == "create_transaction":
            amount = int(action.get("amount", 0))
            if amount < 1000:
                logger.warning("Rejected create_transaction: amount=%s is below 1000", amount)
                return {"ok": False, "reason": f"مبلغ {amount} تومان معقول نیست. حداقل ۱۰۰۰ تومان لازم است."}
            tx_type_raw = str(action.get("type", "expense"))
            if tx_type_raw not in ("expense", "income"):
                return {"ok": False, "reason": "نوع تراکنش نامعتبر است."}
            tx_type = TransactionType.income if tx_type_raw == "income" else TransactionType.expense
            category_name = str(action.get("category", ""))
            category = _find_category(category_name, db, user.id) if category_name else None
            description = str(action.get("description", "")).strip() or category_name or ("درآمد" if tx_type == TransactionType.income else "هزینه")
            if len(description) < 2:
                return {"ok": False, "reason": "توضیح تراکنش کوتاه/ناقص است."}
            date_val = action.get("date", "today")
            if date_val == "today" or not date_val:
                tx_date = date.today()
            else:
                tx_date = _jalali_to_gregorian_date(str(date_val)) or date.today()
            txn = Transaction(
                user_id=user.id,
                category_id=category.id if category else None,
                amount=amount,
                type=tx_type,
                description=description,
                date=tx_date,
            )
            db.add(txn)
            db.commit()
            cat_label = category.name if category else category_name or "عمومی"
            return {"ok": True, "confirmation": f"✅ تراکنش {_fmt(amount)} در دسته «{cat_label}» ثبت شد."}

        if kind == "set_budget":
            amount = int(action.get("amount", 0))
            if amount < 100000:
                logger.warning("Rejected set_budget: amount=%s is below 100000", amount)
                return {"ok": False, "reason": f"مبلغ بودجه {amount} تومان معقول نیست. حداقل ۱۰۰٬۰۰۰ تومان لازم است."}
            jm, jy = current_jalali_month()
            budget = db.query(Budget).filter(
                Budget.user_id == user.id, Budget.month == jm, Budget.year == jy
            ).first()
            if budget:
                budget.amount = amount
            else:
                budget = Budget(user_id=user.id, month=jm, year=jy, amount=amount)
                db.add(budget)
            db.commit()
            return {"ok": True, "confirmation": f"✅ بودجه ماهانه روی {_fmt(amount)} تنظیم شد."}

        if kind == "set_income":
            amount = int(action.get("amount", 0))
            if amount < 1_000_000:
                logger.warning("Rejected set_income: amount=%s is below 1_000_000", amount)
                return {"ok": False, "reason": f"مبلغ درآمد {amount} تومان معقول نیست. حداقل ۱٬۰۰۰٬۰۰۰ تومان لازم است."}
            user.monthly_income = amount
            db.commit()
            return {"ok": True, "confirmation": f"✅ درآمد ماهانه‌ات روی {_fmt(amount)} ثبت شد."}

        return {"ok": False, "reason": f"action ناشناخته: {kind}"}

    except Exception as exc:
        logger.error("execute_action %s failed: %s", kind, exc)
        return {"ok": False, "reason": str(exc)}


def process_ai_reply(reply_text: str, db: Session, user: User) -> str:
    """Extract action blocks, execute them, return final visible text with confirmations.

    Failed actions are logged server-side only — never shown to the user.
    """
    cleaned, actions = extract_actions(reply_text)
    confirmations: list[str] = []
    for action in actions:
        result = execute_action(action, db, user)
        if result["ok"]:
            confirmations.append(result["confirmation"])
        else:
            logger.warning(
                "Action rejected (user=%s, action=%s): %s",
                user.id, action.get("action"), result.get("reason"),
            )

    if confirmations:
        return cleaned + "\n\n" + "\n".join(confirmations)
    return cleaned
