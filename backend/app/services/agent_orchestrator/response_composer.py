from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentPlan, AgentPlanStep

_PLACEHOLDER_RE = re.compile(r"\[[a-zA-Z_][a-zA-Z0-9_\-\s.]*\]")
_SQL_RE = re.compile(r"\b(select|insert|update|delete|drop|alter|pragma)\b", re.IGNORECASE)


def _fmt(amount: int | None) -> str:
    return f"{int(amount or 0):,} تومان"


def sanitize_user_message(message: str | None) -> str:
    if not message:
        return ""
    cleaned = message.replace("```json", "").replace("```", "").strip()
    if _is_generic_failure(cleaned):
        return ""
    if _PLACEHOLDER_RE.search(cleaned):
        return ""
    if _SQL_RE.search(cleaned):
        return ""
    if "{" in cleaned or "}" in cleaned:
        return ""
    return cleaned


def _is_generic_failure(message: str) -> bool:
    text = " ".join((message or "").split())
    return (
        "نتوانستم این درخواست" in text
        or "درخواستت را ساده" in text
        or "درخواستت را با اطمینان پردازش" in text
    )


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
                message=sanitize_user_message(plan.clarification_question) or "لطفا درخواستت را کمی دقیق تر بنویس.",
                metadata={"intent": plan.intent},
            )

        safe_hint = sanitize_user_message(plan.final_response_hint)
        if safe_hint and any(r.executed for r in results):
            return AgentFinalResponse(
                message=safe_hint,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        inserted = [r for r in results if r.inserted_id]
        if inserted:
            response = self._compose_insert(db, plan, inserted)
            if response:
                return response

        updated = [r for r in results if r.updated_id]
        if updated:
            response = self._compose_update(db, plan, updated)
            if response:
                return response

        rejected = [r for r in results if r.rejected_reason or r.error]
        if rejected:
            return AgentFinalResponse(
                message=self._compose_rejected(plan, rejected),
                operations_summary=["rejected unsafe operation"],
                metadata={"intent": plan.intent, "rejected": True},
            )

        select_message = self._compose_select_results(db, plan, results)
        if select_message:
            return AgentFinalResponse(
                message=select_message,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )
        if safe_hint:
            return AgentFinalResponse(
                message=safe_hint,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )
        if select_message:
            return AgentFinalResponse(
                message=select_message,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )
        if fallback_message:
            return AgentFinalResponse(
                message=sanitize_user_message(fallback_message) or "فعلا نتوانستم پاسخ نهایی مطمئنی بسازم.",
                metadata={"intent": plan.intent},
            )

        return AgentFinalResponse(
            message="متوجه شدم. برای ثبت یا تحلیل مالی، لطفا مبلغ و موضوع را کمی دقیق تر بگو.",
            metadata={"intent": plan.intent},
        )

    def _compose_update(self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult]) -> AgentFinalResponse | None:
        step_by_id = {step.step_id: step for step in plan.steps}
        goal_update = next(
            (
                result
                for result in reversed(results)
                if result.updated_id and step_by_id.get(result.step_id) and step_by_id[result.step_id].table_name == "goals"
            ),
            None,
        )
        if not goal_update:
            return None
        goal = db.query(Goal).filter(Goal.id == goal_update.updated_id).first()
        if not goal:
            return None
        deadline = f" با مهلت {goal.deadline.isoformat()}" if goal.deadline else ""
        return AgentFinalResponse(
            message=f"به‌روزرسانی شد. هدف {goal.title}{deadline} ذخیره شد.",
            operations_summary=[r.summary or "" for r in results if r.summary],
            metadata={"intent": plan.intent, "goal_id": goal.id},
        )

    def _compose_rejected(self, plan: AgentPlan, rejected: list[AgentExecutionResult]) -> str:
        reasons = " ".join(str(r.rejected_reason or r.error or "").lower() for r in rejected)
        if any(marker in reasons for marker in ("destructive", "administrative", "forbidden", "multiple statements", "comments", "drop", "delete", "alter")):
            return "عملیات نامعتبر است و به شکل امن اجرا نشد."

        intent = (plan.intent or "").lower()
        step_text = " ".join(str(step.purpose or "").lower() for step in plan.steps)
        if "goal" in intent or "goal" in step_text:
            return "برای پاسخ دقیق باید اهداف ثبت‌شده را بررسی کنم، اما برنامه پایگاه‌داده کامل و معتبر نبود. دوباره بپرس تا هدف را از روی داده‌های واقعی پیدا کنم."
        if any(word in intent or word in step_text for word in ("advice", "budget", "spending", "cfo", "financial_status")):
            return "برای این تحلیل باید بودجه، خرج‌ها، اهداف و تعهدات آینده را از داده‌های شما بخوانم. این بار برنامه خواندن داده کامل نشد؛ دوباره بپرس تا تحلیل را از داده‌های واقعی بسازم."
        return "فعلاً این عملیات با قوانین ایمنی پایگاه‌داده سازگار نشد. اگر درخواست مالی عادی است، دوباره با همان جزئیات بپرس."

    def _compose_insert(self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult]) -> AgentFinalResponse | None:
        step_by_id = {step.step_id: step for step in plan.steps}
        result = next(
            (
                item
                for item in reversed(results)
                if step_by_id.get(item.step_id) and step_by_id[item.step_id].table_name == "transactions"
            ),
            results[-1],
        )
        tx = db.query(Transaction).filter(Transaction.id == result.inserted_id).first()
        if not tx:
            return None
        category = db.query(Category).filter(Category.id == tx.category_id).first() if tx.category_id else None
        kind = "درآمد" if tx.type == TransactionType.income else "هزینه"
        cat_text = f" در دسته {category.name}" if category else ""
        suggestion = (
            "اگر این درآمد تکرارشونده است، می توانیم بعدا آن را در برنامه ماهانه ات لحاظ کنیم."
            if tx.type == TransactionType.income
            else "بهتر است آخر هفته یک نگاه کوتاه به روند خرج های این ماه داشته باشیم."
        )
        message = f"ثبت شد. {kind} {_fmt(tx.amount)} برای {tx.description or kind}{cat_text} ذخیره شد. {suggestion}"
        return AgentFinalResponse(
            message=message,
            operations_summary=[f"inserted transaction {tx.id}"],
            metadata={"intent": plan.intent, "transaction_id": tx.id},
        )

    def _compose_select_results(self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult]) -> str | None:
        step_by_id = {step.step_id: step for step in plan.steps}
        totals: dict[str, int] = {}
        top_category: tuple[str, int] | None = None
        goal_rows: list[dict[str, Any]] = []

        for result in results:
            if not result.executed or result.operation_type.value != "select":
                continue
            step = step_by_id.get(result.step_id)
            if not step:
                continue
            if step.table_name == "goals" and result.rows:
                goal_rows.extend(result.rows)
                continue
            if result.rows and "type" in result.rows[0]:
                for typed_row in result.rows:
                    typed_total = self._extract_total(typed_row)
                    typed_type = typed_row.get("type")
                    if typed_type in {"expense", "income"} and typed_total is not None:
                        totals[str(typed_type)] = typed_total
                continue
            row = result.rows[0] if result.rows else {}
            total = self._extract_total(row)
            if "category_id" in row and total is not None:
                category = db.query(Category).filter(Category.id == int(row["category_id"])).first() if row.get("category_id") is not None else None
                row_name = row.get("name") or row.get("category_name")
                top_category = (str(row_name or (category.name if category else "سایر")), total)
                continue
            if ("name" in row or "category_name" in row) and total is not None:
                top_category = (str(row.get("name") or row.get("category_name") or "سایر"), total)
                continue
            tx_type = self._step_transaction_type(step)
            if tx_type and total is not None:
                totals[tx_type] = total
                continue

        goal_text = " ".join(
            str(part or "").lower()
            for step in plan.steps
            for part in (step.purpose, step.expected_result_name, step.result_usage)
        )
        if goal_rows and ("goal" in goal_text or "هدف" in goal_text or "goal" in (plan.intent or "").lower()):
            return self._compose_goal_rows(goal_rows)

        if "expense" in totals and "income" in totals:
            expense = totals.get("expense", 0)
            income = totals.get("income", 0)
            balance = income - expense
            if expense and income:
                balance_text = f"تراز ثبت شده شما {_fmt(abs(balance))} {'مثبت' if balance >= 0 else 'منفی'} است."
                return f"در این بازه {_fmt(expense)} هزینه و {_fmt(income)} درآمد ثبت کرده اید. {balance_text}"
            if expense and not income:
                return f"در این بازه {_fmt(expense)} هزینه ثبت شده اما درآمدی ثبت نشده است."
            if income and not expense:
                return f"در این بازه درآمد شما {_fmt(income)} بوده و هزینه ای ثبت نشده است."
            return "برای این بازه درآمد یا هزینه ای ثبت نشده است."

        if "expense" in totals:
            expense = totals.get("expense", 0)
            return f"در این بازه مجموعا {_fmt(expense)} هزینه ثبت شده است." if expense else "برای این بازه هزینه ای ثبت نشده است."
        if "income" in totals:
            income = totals.get("income", 0)
            return f"درآمد شما در این بازه مجموعا {_fmt(income)} بوده است." if income else "برای این بازه درآمدی ثبت نشده است."
        if top_category:
            name, amount = top_category
            return f"بیشترین خرج این بازه مربوط به دسته {name} با مجموع {_fmt(amount)} بوده است." if amount else "برای این بازه هزینه ای ثبت نشده است."
        if goal_rows:
            return self._compose_goal_rows(goal_rows)
        return None

    def _compose_goal_rows(self, rows: list[dict[str, Any]]) -> str:
        visible_rows = [
            row
            for row in rows
            if row.get("is_active", True) is not False and str(row.get("status") or "active") != "archived"
        ]
        if not visible_rows:
            return "فعلاً هدف مالی فعالی برای شما ثبت نشده است."

        lines = ["اهداف فعال شما:"]
        for row in visible_rows[:8]:
            title = str(row.get("title") or "هدف مالی")
            target = int(row.get("target_amount") or 0)
            current = int(row.get("current_amount") or 0)
            remaining = max(target - current, 0)
            progress = int((current / target) * 100) if target else 0
            deadline = row.get("deadline")
            deadline_text = f"، مهلت {deadline}" if deadline else ""
            lines.append(f"- {title}: هدف {_fmt(target)}، پس‌انداز فعلی {_fmt(current)}، باقی‌مانده {_fmt(remaining)}، پیشرفت {progress}%{deadline_text}")
        return "\n".join(lines)

    def _extract_total(self, row: dict[str, Any]) -> int | None:
        for key in ("total", "total_amount", "sum", "amount"):
            if key in row:
                return int(row.get(key) or 0)
        return None

    def _step_transaction_type(self, step: AgentPlanStep) -> str | None:
        raw = step.params.get("type")
        if raw in {"expense", "income"}:
            return str(raw)
        purpose = " ".join(
            str(part or "").lower()
            for part in (step.purpose, step.expected_result_name, step.result_usage)
        )
        sql = (step.sql or "").lower()
        if "income" in purpose or "type = 'income'" in sql or 'type = "income"' in sql:
            return "income"
        if "expense" in purpose or "type = 'expense'" in sql or 'type = "expense"' in sql:
            return "expense"
        return None
