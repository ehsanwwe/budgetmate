from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentPlan


def _fmt(amount: int | None) -> str:
    return f"{int(amount or 0):,} تومان"


class ResponseComposer:
    def compose(
        self,
        db: Session,
        plan: AgentPlan,
        results: list[AgentExecutionResult],
        fallback_message: str = "",
    ) -> AgentFinalResponse:
        if plan.clarification_question:
            return AgentFinalResponse(message=plan.clarification_question, metadata={"intent": plan.intent})

        inserted = [r for r in results if r.inserted_id]
        if inserted:
            tx = db.query(Transaction).filter(Transaction.id == inserted[-1].inserted_id).first()
            if tx:
                category = db.query(Category).filter(Category.id == tx.category_id).first() if tx.category_id else None
                kind = "درآمد" if tx.type == TransactionType.income else "هزینه"
                cat_text = f" در دسته {category.name}" if category else ""
                message = (
                    f"ثبت شد. {kind} {_fmt(tx.amount)} برای {tx.description or kind}{cat_text} ذخیره شد. "
                    "پیشنهاد کوتاه: آخر هفته یک نگاه سریع به روند خرج های این ماه داشته باش. "
                    "می خواهی برای همین دسته یک بودجه ماهانه مشخص کنیم؟"
                )
                return AgentFinalResponse(
                    message=message,
                    operations_summary=[f"inserted transaction {tx.id}"],
                    metadata={"intent": plan.intent, "transaction_id": tx.id},
                )

        selected = [r for r in results if r.rows]
        if selected and plan.final_response_hint:
            return AgentFinalResponse(
                message=plan.final_response_hint,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        if fallback_message:
            return AgentFinalResponse(message=fallback_message, metadata={"intent": plan.intent})
        if plan.final_response_hint:
            return AgentFinalResponse(message=plan.final_response_hint, metadata={"intent": plan.intent})

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
