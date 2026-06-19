from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.i18n.service import t as i18n_t
from app.models.category import Category
from app.models.goal import Goal
from app.models.transaction import Transaction, TransactionType
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentPlan, AgentPlanStep

_PLACEHOLDER_RE = re.compile(r"\[[a-zA-Z_][a-zA-Z0-9_\-\s.]*\]")
_SQL_RE = re.compile(r"\b(select|insert|update|delete|drop|alter|pragma)\b", re.IGNORECASE)

# Detects operation-confirmation sentences appended at the end of hints —
# these can bleed in when the LLM sees prior-turn results in history and
# copies them into the current final_response_hint.
_LEAKED_OP_RE = re.compile(
    r"[.،\s]+[^.،]{0,80}(?:منتقل شد|آپدیت شد|به‌روزرسانی شد|تغییر کرد|ثبت شد|ذخیره شد|اضافه شد)[^.،]{0,60}$",
    re.UNICODE,
)


def _fmt(amount: int | None, locale: str = "fa") -> str:
    unit = i18n_t("composer.toman", locale)
    return f"{int(amount or 0):,} {unit}"


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


def _strip_leaked_operations(message: str) -> str:
    """Remove trailing leaked operation-confirmation sentences from a SELECT-only hint."""
    return _LEAKED_OP_RE.sub("", message).strip()


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
        locale: str = "fa",
    ) -> AgentFinalResponse:
        if plan.clarification_question:
            return AgentFinalResponse(
                message=sanitize_user_message(plan.clarification_question) or i18n_t("composer.clarification", locale),
                metadata={"intent": plan.intent},
            )

        # Determine if this turn performed real writes (not just SELECTs or skipped dupes)
        current_turn_wrote = any(
            r.executed and r.operation_type.value in {"insert", "update"} and not r.skipped_duplicate
            for r in results
        )

        # Build a sanitized hint; strip leaked prior-turn op confirmations on SELECT-only turns
        safe_hint = sanitize_user_message(plan.final_response_hint)
        if safe_hint and not current_turn_wrote:
            safe_hint = _strip_leaked_operations(safe_hint)

        # Semantic goal dedup: existing active goal prevented a new insert
        skipped_with_existing = [r for r in results if r.skipped_duplicate and r.existing_record_id]
        if skipped_with_existing:
            existing_id = skipped_with_existing[-1].existing_record_id
            goal = db.query(Goal).filter(Goal.id == existing_id).first()
            if goal:
                deadline_text = i18n_t("composer.goal_deadline_txt", locale, {"date": goal.deadline.isoformat()}) if goal.deadline else ""
                return AgentFinalResponse(
                    message=i18n_t("composer.duplicate_goal", locale, {
                        "title": goal.title,
                        "amount": _fmt(goal.target_amount, locale),
                        "deadline": deadline_text,
                    }),
                    operations_summary=["skipped duplicate goal"],
                    metadata={"intent": plan.intent, "existing_goal_id": existing_id},
                )

        # For UPDATE turns: verify the write happened via DB re-read before using hint/response
        updated = [r for r in results if r.updated_id and not r.skipped_duplicate]
        if updated:
            ok = self._verify_updates(db, plan, updated)
            if not ok:
                return AgentFinalResponse(
                    message=i18n_t("composer.update_failed", locale),
                    metadata={"intent": plan.intent, "update_verification_failed": True},
                )

        # Primary response path: if the planner provided a clean hint and any operation executed,
        # use the hint (it is the planner's informed synthesis of all DB results).
        # For SELECT-only turns the hint has already been stripped of leaked op sentences above.
        any_executed = any(r.executed for r in results)
        if safe_hint and any_executed:
            return AgentFinalResponse(
                message=safe_hint,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        # Fallback DB-grounded responses (used when no good hint is available)
        inserted = [r for r in results if r.inserted_id and not r.skipped_duplicate]
        if inserted:
            response = self._compose_insert(db, plan, inserted, locale)
            if response:
                return response

        if updated:
            response = self._compose_update_fallback(db, plan, updated, locale)
            if response:
                return response

        rejected = [r for r in results if r.rejected_reason or r.error]
        if rejected:
            return AgentFinalResponse(
                message=self._compose_rejected(plan, rejected, locale),
                operations_summary=["rejected unsafe operation"],
                metadata={"intent": plan.intent, "rejected": True},
            )

        select_message = self._compose_select_results(db, plan, results, locale)
        if select_message:
            return AgentFinalResponse(
                message=select_message,
                operations_summary=[r.summary or "" for r in results if r.summary],
                metadata={"intent": plan.intent},
            )

        if fallback_message:
            return AgentFinalResponse(
                message=sanitize_user_message(fallback_message) or i18n_t("composer.uncertain_fallback", locale),
                metadata={"intent": plan.intent},
            )

        return AgentFinalResponse(
            message=i18n_t("composer.general_fallback", locale),
            metadata={"intent": plan.intent},
        )

    def _verify_updates(self, db: Session, plan: AgentPlan, updated_results: list[AgentExecutionResult]) -> bool:
        """Re-read all updated rows to confirm the write actually persisted."""
        step_by_id = {step.step_id: step for step in plan.steps}
        for result in updated_results:
            step = step_by_id.get(result.step_id)
            if not step:
                continue
            if step.table_name == "goals":
                goal = db.query(Goal).filter(Goal.id == result.updated_id).first()
                if not goal:
                    return False
        return True

    def _compose_update_fallback(
        self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult], locale: str = "fa"
    ) -> AgentFinalResponse | None:
        """DB-grounded fallback for update turns when no clean hint is available."""
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
        deadline = i18n_t("composer.goal_deadline_update", locale, {"date": goal.deadline.isoformat()}) if goal.deadline else ""
        return AgentFinalResponse(
            message=i18n_t("composer.goal_updated", locale, {"title": goal.title, "deadline": deadline}),
            operations_summary=[r.summary or "" for r in results if r.summary],
            metadata={"intent": plan.intent, "goal_id": goal.id},
        )

    def _compose_rejected(self, plan: AgentPlan, rejected: list[AgentExecutionResult], locale: str = "fa") -> str:
        reasons = " ".join(str(r.rejected_reason or r.error or "").lower() for r in rejected)
        if any(marker in reasons for marker in ("destructive", "administrative", "forbidden", "multiple statements", "comments", "drop", "delete", "alter")):
            return i18n_t("composer.rejected_destructive", locale)
        if "history_context" in reasons:
            return i18n_t("composer.rejected_history", locale)

        intent = (plan.intent or "").lower()
        step_text = " ".join(str(step.purpose or "").lower() for step in plan.steps)
        if "goal" in intent or "goal" in step_text:
            return i18n_t("composer.rejected_goal", locale)
        if any(word in intent or word in step_text for word in ("advice", "budget", "spending", "cfo", "financial_status")):
            return i18n_t("composer.rejected_advice", locale)
        return i18n_t("composer.rejected_default", locale)

    def _compose_insert(
        self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult], locale: str = "fa"
    ) -> AgentFinalResponse | None:
        step_by_id = {step.step_id: step for step in plan.steps}

        goal_result = next(
            (item for item in reversed(results)
             if item.inserted_id and step_by_id.get(item.step_id) and step_by_id[item.step_id].table_name == "goals"),
            None,
        )
        commitment_result = next(
            (item for item in reversed(results)
             if item.inserted_id and step_by_id.get(item.step_id) and step_by_id[item.step_id].table_name == "future_commitments"),
            None,
        )
        tx_result = next(
            (item for item in reversed(results)
             if item.inserted_id and step_by_id.get(item.step_id) and step_by_id[item.step_id].table_name == "transactions"),
            None,
        )

        if goal_result and not tx_result:
            goal = db.query(Goal).filter(Goal.id == goal_result.inserted_id).first()
            if goal:
                deadline_text = i18n_t("composer.goal_deadline_txt", locale, {"date": goal.deadline.isoformat()}) if goal.deadline else ""
                msg = i18n_t("composer.goal_created", locale, {
                    "title": goal.title,
                    "amount": _fmt(goal.target_amount, locale),
                    "deadline": deadline_text,
                })
                if commitment_result:
                    msg = msg + " " + i18n_t("composer.goal_with_commitment", locale)
                return AgentFinalResponse(
                    message=msg,
                    operations_summary=[r.summary or "" for r in results if r.summary],
                    metadata={"intent": plan.intent, "goal_id": goal.id},
                )

        if commitment_result and not tx_result and not goal_result:
            from app.models.future_commitment import FutureCommitment
            commitment = db.query(FutureCommitment).filter(FutureCommitment.id == commitment_result.inserted_id).first()
            if commitment:
                due_text = (
                    i18n_t("composer.commitment_due_date", locale, {"date": commitment.due_date.isoformat()})
                    if commitment.due_date
                    else (i18n_t("composer.commitment_due_month", locale, {"month": commitment.due_month}) if commitment.due_month else "")
                )
                return AgentFinalResponse(
                    message=i18n_t("composer.commitment_created", locale, {
                        "title": commitment.title,
                        "amount": _fmt(commitment.amount, locale),
                        "due": due_text,
                    }),
                    operations_summary=[r.summary or "" for r in results if r.summary],
                    metadata={"intent": plan.intent, "commitment_id": commitment.id},
                )

        if not tx_result:
            tx_result = next((r for r in reversed(results) if r.inserted_id), None)
            if not tx_result:
                return None

        tx = db.query(Transaction).filter(Transaction.id == tx_result.inserted_id).first()
        if not tx:
            return None
        category = db.query(Category).filter(Category.id == tx.category_id).first() if tx.category_id else None
        kind = i18n_t("composer.kind_income", locale) if tx.type == TransactionType.income else i18n_t("composer.kind_expense", locale)
        cat_text = i18n_t("composer.cat_in", locale, {"name": category.name}) if category else ""
        suggestion = (
            i18n_t("composer.tx_income_suggestion", locale)
            if tx.type == TransactionType.income
            else i18n_t("composer.tx_expense_suggestion", locale)
        )

        extra_parts = []
        if commitment_result:
            from app.models.future_commitment import FutureCommitment
            commitment = db.query(FutureCommitment).filter(FutureCommitment.id == commitment_result.inserted_id).first()
            if commitment:
                due_text = (
                    i18n_t("composer.commitment_due_date", locale, {"date": commitment.due_date.isoformat()})
                    if commitment.due_date
                    else (i18n_t("composer.commitment_due_month", locale, {"month": commitment.due_month}) if commitment.due_month else "")
                )
                extra_parts.append(i18n_t("composer.tx_commitment_also", locale, {
                    "amount": _fmt(commitment.amount, locale),
                    "due": due_text,
                }))

        message = i18n_t("composer.tx_recorded", locale, {
            "kind": kind,
            "amount": _fmt(tx.amount, locale),
            "desc": tx.description or kind,
            "cat": cat_text,
        })
        if extra_parts:
            message += " " + " ".join(extra_parts)
        else:
            message += f" {suggestion}"

        return AgentFinalResponse(
            message=message,
            operations_summary=[f"inserted transaction {tx.id}"],
            metadata={"intent": plan.intent, "transaction_id": tx.id},
        )

    def _compose_select_results(
        self, db: Session, plan: AgentPlan, results: list[AgentExecutionResult], locale: str = "fa"
    ) -> str | None:
        step_by_id = {step.step_id: step for step in plan.steps}
        totals: dict[str, int] = {}
        top_category: tuple[str, int] | None = None
        goal_rows: list[dict[str, Any]] = []
        non_goal_tables_with_rows: set[str] = set()

        for result in results:
            if not result.executed or result.operation_type.value != "select":
                continue
            step = step_by_id.get(result.step_id)
            if not step:
                continue
            table = step.table_name or ""
            if table == "goals" and result.rows:
                goal_rows.extend(result.rows)
                continue
            if result.rows and table not in {"goals", "categories"}:
                non_goal_tables_with_rows.add(table)
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
                top_category = (str(row_name or (category.name if category else i18n_t("composer.kind_expense", locale))), total)
                continue
            if ("name" in row or "category_name" in row) and total is not None:
                top_category = (str(row.get("name") or row.get("category_name") or i18n_t("composer.kind_expense", locale)), total)
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

        # If goals were found alongside multiple other tables with data, the hint (if any)
        # provides a better holistic synthesis than the goal list alone — return None to let
        # the hint handle it.
        if goal_rows and non_goal_tables_with_rows:
            return None

        if goal_rows and ("goal" in goal_text or "هدف" in goal_text or "goal" in (plan.intent or "").lower()):
            return self._compose_goal_rows(goal_rows, locale)

        if "expense" in totals and "income" in totals:
            expense = totals.get("expense", 0)
            income = totals.get("income", 0)
            balance = income - expense
            if expense and income:
                direction = i18n_t("composer.select_balance_positive", locale) if balance >= 0 else i18n_t("composer.select_balance_negative", locale)
                return i18n_t("composer.select_both", locale, {
                    "expense": _fmt(expense, locale),
                    "income": _fmt(income, locale),
                    "balance": _fmt(abs(balance), locale),
                    "direction": direction,
                })
            if expense and not income:
                return i18n_t("composer.select_expense_only", locale, {"amount": _fmt(expense, locale)})
            if income and not expense:
                return i18n_t("composer.select_income_only", locale, {"amount": _fmt(income, locale)})
            return i18n_t("composer.select_no_expense", locale)

        if "expense" in totals:
            expense = totals.get("expense", 0)
            return (
                i18n_t("composer.select_expense_only", locale, {"amount": _fmt(expense, locale)})
                if expense
                else i18n_t("composer.select_no_expense", locale)
            )
        if "income" in totals:
            income = totals.get("income", 0)
            return (
                i18n_t("composer.select_income_only", locale, {"amount": _fmt(income, locale)})
                if income
                else i18n_t("composer.select_no_income", locale)
            )
        if top_category:
            name, amount = top_category
            return (
                i18n_t("composer.select_top_category", locale, {"name": name, "amount": _fmt(amount, locale)})
                if amount
                else i18n_t("composer.select_no_data", locale)
            )
        if goal_rows:
            return self._compose_goal_rows(goal_rows, locale)
        return None

    def _compose_goal_rows(self, rows: list[dict[str, Any]], locale: str = "fa") -> str:
        visible_rows = [
            row
            for row in rows
            if row.get("is_active", True) is not False and str(row.get("status") or "active") != "archived"
        ]
        if not visible_rows:
            return i18n_t("composer.goals_no_active", locale)

        lines = [i18n_t("composer.goals_active_header", locale)]
        for row in visible_rows[:8]:
            title = str(row.get("title") or "")
            target = int(row.get("target_amount") or 0)
            current = int(row.get("current_amount") or 0)
            remaining = max(target - current, 0)
            progress = int((current / target) * 100) if target else 0
            deadline = row.get("deadline")
            deadline_text = i18n_t("composer.goals_deadline", locale, {"date": deadline}) if deadline else ""
            lines.append(i18n_t("composer.goals_active_row", locale, {
                "title": title,
                "target": _fmt(target, locale),
                "current": _fmt(current, locale),
                "remaining": _fmt(remaining, locale),
                "progress": progress,
                "deadline": deadline_text,
            }))
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
