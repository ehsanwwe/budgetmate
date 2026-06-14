from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentPlan

_PLACEHOLDER_RE = re.compile(r"\[[a-zA-Z_][a-zA-Z0-9_\-\s.]*\]")
_SQL_RE = re.compile(r"\b(select|insert|update|delete|drop|alter|pragma)\b", re.IGNORECASE)


def _fmt(amount: int | None) -> str:
    return f"{int(amount or 0):,} تومان"


def sanitize_user_message(message: str | None) -> str:
    if not message:
        return ""
    cleaned = message.replace("```json", "").replace("```", "").strip()
    if _PLACEHOLDER_RE.search(cleaned):
        return ""
    if _SQL_RE.search(cleaned):
        return ""
    if "{" in cleaned or "}" in cleaned:
        return ""
    return cleaned


class ResponseComposer:
    def compose(
        self,
        db: Session,
        plan: AgentPlan,
        results: list[AgentExecutionResult],
        fallback_message: str = "",
    ) -> AgentFinalResponse:
        if plan.clarification_question:
            return AgentFinalResponse(
                message=sanitize_user_message(plan.clarification_question)
                or "لطفا درخواستت را کمی دقیق تر بنویس.",
                metadata={"intent": plan.intent},
            )

        inserted = [r for r in results if r.inserted_id]
        if inserted:
            tx = db.query(Transaction).filter(Transaction.id == inserted[-1].inserted_id).first()
            if tx:
                category = db.query(Category).filter(Category.id == tx.category_id).first() if tx.category_id else None
                kind = "درآمد" if tx.type == TransactionType.income else "هزینه"
                cat_text = f" در دسته {category.name}" if category else ""
                suggestion = (
                    "بهتر است آخر هفته یک نگاه کوتاه به روند خرج های این ماه داشته باشیم."
                    if tx.type == TransactionType.expense
                    else "اگر این درآمد تکرارشونده است، می توانیم بعدا آن را در برنامه ماهانه ات لحاظ کنیم."
                )
                question = (
                    "می خواهی برای همین دسته یک بودجه ماهانه مشخص کنیم؟"
                    if tx.type == TransactionType.expense
                    else "می خواهی درآمدهای پروژه ای را جداگانه پیگیری کنیم؟"
                )
                message = (
                    f"ثبت شد. {kind} {_fmt(tx.amount)} برای {tx.description or kind}{cat_text} ذخیره شد. "
                    f"{suggestion} {question}"
                )
                return AgentFinalResponse(
                    message=message,
                    operations_summary=[f"inserted transaction {tx.id}"],
                    metadata={"intent": plan.intent, "transaction_id": tx.id},
                )

        selected = [r for r in results if r.rows]
        select_results = [r for r in results if r.operation_type.value == "select" and r.executed]
        aggregate = self._compose_aggregate(db, plan, (select_results[-1] if select_results else None))
        if aggregate:
            return AgentFinalResponse(
                message=aggregate,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        safe_hint = sanitize_user_message(plan.final_response_hint)
        if selected and safe_hint:
            return AgentFinalResponse(
                message=safe_hint,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        if fallback_message:
            return AgentFinalResponse(
                message=sanitize_user_message(fallback_message) or self._fallback_for_intent(plan.intent),
                metadata={"intent": plan.intent},
            )
        if safe_hint:
            return AgentFinalResponse(message=safe_hint, metadata={"intent": plan.intent})

        rejected = [r for r in results if r.rejected_reason or r.error]
        if rejected:
            return AgentFinalResponse(
                message="نتوانستم این درخواست را به شکل امن انجام بدهم. لطفا درخواستت را ساده تر و دقیق تر بنویس.",
                operations_summary=["rejected unsafe operation"],
                metadata={"intent": plan.intent, "rejected": True},
            )

        return AgentFinalResponse(
            message="متوجه شدم. برای ثبت یا تحلیل مالی، لطفا مبلغ و موضوع را کمی دقیق تر بگو.",
            metadata={"intent": plan.intent},
        )

    def _compose_aggregate(self, db: Session, plan: AgentPlan, result: AgentExecutionResult | None) -> str | None:
        if not result or not plan.intent.startswith("aggregate:"):
            return None
        parts = plan.intent.split(":")
        if len(parts) != 4:
            return None
        _, aggregate_type, range_key, tx_type = parts
        range_text = {
            "current_week": "این هفته",
            "previous_week": "هفته گذشته",
            "current_month": "این ماه",
            "previous_month": "ماه گذشته",
            "today": "امروز",
            "yesterday": "دیروز",
        }.get(range_key, "این بازه")
        kind_text = "درآمد" if tx_type == "income" else "هزینه"

        if aggregate_type == "total":
            total = int((result.rows[0].get("total") if result.rows else 0) or 0)
            if total <= 0:
                return f"برای {range_text} {kind_text} ثبت نشده است."
            verb = "داشته اید" if tx_type == "income" else "خرج کرده اید"
            return f"{kind_text} شما در {range_text} مجموعا {_fmt(total)} {verb}."

        if aggregate_type == "top_category":
            row = result.rows[0] if result.rows else {}
            total = int(row.get("total") or 0)
            if total <= 0:
                return f"برای {range_text} هزینه ای ثبت نشده است."
            category = None
            if row.get("category_id") is not None:
                category = db.query(Category).filter(Category.id == int(row["category_id"])).first()
            name = category.name if category else "سایر"
            return f"بیشترین خرج {range_text} مربوط به دسته {name} با مجموع {_fmt(total)} بوده است."
        return None

    def _fallback_for_intent(self, intent: str) -> str:
        if "top_category" in intent:
            return "هنوز داده کافی برای این تحلیل ندارم."
        if "aggregate" in intent:
            return "برای این بازه تراکنشی ثبت نشده است."
        return "متوجه شدم. لطفا درخواستت را کمی دقیق تر بنویس."
