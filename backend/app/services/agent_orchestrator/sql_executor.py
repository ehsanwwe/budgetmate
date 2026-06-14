from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_audit import AgentSqlAuditLog
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.agent_orchestrator.table_policy import get_policy
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentOperationType, AgentPlanStep, SqlValidationResult


def audit_operation(
    db: Session,
    user_id: int | None,
    intent: str | None,
    step: AgentPlanStep,
    validation_status: str,
    rejected_reason: str | None = None,
    executed: bool = False,
    result_summary: dict[str, Any] | None = None,
) -> None:
    audit = AgentSqlAuditLog(
        user_id=user_id,
        intent=intent,
        operation_type=step.operation_type.value,
        table_name=step.table_name,
        planned_sql=step.sql,
        params_json=step.params,
        validation_status=validation_status,
        rejected_reason=rejected_reason,
        executed=executed,
        result_summary_json=result_summary or {},
    )
    db.add(audit)
    db.commit()


class SqlExecutor:
    def execute(
        self,
        db: Session,
        user: User,
        step: AgentPlanStep,
        validation: SqlValidationResult,
        intent: str,
    ) -> AgentExecutionResult:
        if not validation.allowed:
            audit_operation(db, user.id, intent, step, "rejected", validation.rejected_reason, False)
            return AgentExecutionResult(
                step_id=step.step_id,
                operation_type=step.operation_type,
                allowed=False,
                executed=False,
                rejected_reason=validation.rejected_reason,
            )

        try:
            if validation.operation_type == AgentOperationType.select:
                rows = self._execute_select(db, user, validation)
                summary = {"row_count": len(rows)}
                audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=AgentOperationType.select,
                    allowed=True,
                    executed=True,
                    rows=rows,
                    summary=f"{len(rows)} rows selected",
                )

            inserted_id = self._execute_insert(db, user, validation)
            summary = {"inserted_id": inserted_id}
            audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
            return AgentExecutionResult(
                step_id=step.step_id,
                operation_type=AgentOperationType.insert,
                allowed=True,
                executed=True,
                inserted_id=inserted_id,
                summary=f"inserted row {inserted_id}",
            )
        except Exception as exc:
            db.rollback()
            audit_operation(db, user.id, intent, step, "error", str(exc), False)
            return AgentExecutionResult(
                step_id=step.step_id,
                operation_type=step.operation_type,
                allowed=True,
                executed=False,
                error=str(exc),
            )

    def _execute_select(self, db: Session, user: User, validation: SqlValidationResult) -> list[dict[str, Any]]:
        sql = validation.sql or ""
        params = dict(validation.params)
        policy = get_policy(validation.table_name or "")
        if policy and policy.user_scoped and policy.user_id_column:
            sql = self._add_user_scope(sql, policy.user_id_column)
            params["__current_user_id"] = user.id
        sql = self._add_limit(sql, validation.limit or (policy.max_select_rows if policy else 25))

        result = db.execute(text(sql), params)
        rows = []
        for row in result.mappings().all():
            rows.append({key: self._json_value(value) for key, value in row.items()})
        return rows

    def _execute_insert(self, db: Session, user: User, validation: SqlValidationResult) -> int:
        table = validation.table_name
        params = dict(validation.params)
        if table != "transactions":
            raise ValueError("only transaction inserts are enabled in phase 1")

        category_id = params.get("category_id")
        if category_id is not None:
            category = db.query(Category).filter(Category.id == int(category_id)).first()
            if not category or (not category.is_default and category.user_id != user.id):
                raise ValueError("category_id is not available to the current user")

        amount = int(params.get("amount", 0))
        if amount < 1000:
            raise ValueError("amount is too small for a transaction")
        tx_type_raw = str(params.get("type", "expense"))
        if tx_type_raw not in {"expense", "income"}:
            raise ValueError("transaction type must be expense or income")
        tx_date = params.get("date")
        if isinstance(tx_date, str):
            tx_date = date.fromisoformat(tx_date)
        elif not tx_date:
            tx_date = date.today()

        txn = Transaction(
            user_id=user.id,
            category_id=int(category_id) if category_id is not None else None,
            amount=amount,
            type=TransactionType.income if tx_type_raw == "income" else TransactionType.expense,
            description=str(params.get("description") or ("درآمد" if tx_type_raw == "income" else "هزینه")),
            date=tx_date,
        )
        db.add(txn)
        db.commit()
        db.refresh(txn)
        return int(txn.id)

    def _add_user_scope(self, sql: str, user_id_column: str) -> str:
        clause = f"{user_id_column} = :__current_user_id"
        if re.search(r"\bwhere\b", sql, re.IGNORECASE):
            return re.sub(r"\bwhere\b", f"WHERE {clause} AND", sql, count=1, flags=re.IGNORECASE)
        return re.sub(r"\b(order\s+by|limit)\b", f"WHERE {clause} \\1", sql, count=1, flags=re.IGNORECASE) if re.search(r"\b(order\s+by|limit)\b", sql, re.IGNORECASE) else f"{sql} WHERE {clause}"

    def _add_limit(self, sql: str, limit: int) -> str:
        if re.search(r"\blimit\s+\d+\b", sql, re.IGNORECASE):
            return re.sub(r"\blimit\s+\d+\b", f"LIMIT {limit}", sql, flags=re.IGNORECASE)
        return f"{sql} LIMIT {limit}"

    def _json_value(self, value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        return value
