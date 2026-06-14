from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_audit import AgentSqlAuditLog
from app.models.category import Category
from app.models.personal_cfo import BehaviorInsight, FinancialDecisionLog, FinancialFact, FinancialMemory, FinancialWarning
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.agent_orchestrator.date_utils import parse_relative_date
from app.services.agent_orchestrator.table_policy import get_policy
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentOperationType, AgentPlanStep, SqlValidationResult
from app.services.agent_orchestrator.value_normalizer import normalize_amount, normalize_date
from app.services.personal_cfo.behavior_service import ALLOWED_INSIGHTS
from app.services.personal_cfo.memory_service import ALLOWED_MEMORY_TYPES


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
            sql = self._add_user_scope(sql, validation.table_name or "", policy.user_id_column)
            params["__current_user_id"] = user.id
        if validation.table_name == "categories":
            sql = self._add_category_scope(sql)
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
        if table == "transactions":
            return self._insert_transaction(db, user, params)
        if table == "financial_memories":
            return self._insert_memory(db, user, params)
        if table == "behavior_insights":
            return self._insert_behavior_insight(db, user, params)
        if table == "financial_facts":
            return self._insert_fact(db, user, params)
        if table == "financial_warnings":
            return self._insert_warning(db, user, params)
        if table == "financial_decision_logs":
            return self._insert_decision_log(db, user, params)
        raise ValueError("INSERT into this table is not enabled")

    def _insert_transaction(self, db: Session, user: User, params: dict[str, Any]) -> int:
        category_id = params.get("category_id")
        if category_id is not None:
            category = db.query(Category).filter(Category.id == int(category_id)).first()
            if not category or (not category.is_default and category.user_id != user.id):
                raise ValueError("category_id is not available to the current user")

        amount = normalize_amount(params.get("amount", 0))
        if amount < 1000:
            raise ValueError("amount is too small for a transaction")
        tx_type_raw = str(params.get("type", "expense"))
        if tx_type_raw not in {"expense", "income"}:
            raise ValueError("transaction type must be expense or income")
        tx_date = normalize_date(params.get("date"))

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

    def _insert_memory(self, db: Session, user: User, params: dict[str, Any]) -> int:
        memory_type = str(params.get("memory_type") or "")
        if memory_type not in ALLOWED_MEMORY_TYPES:
            raise ValueError("unsupported memory type")
        row = FinancialMemory(
            user_id=user.id,
            memory_type=memory_type,
            title=str(params.get("title") or memory_type)[:200],
            content_json=self._json_param(params.get("content_json")),
            source=str(params.get("source") or "chat")[:50],
            confidence=self._confidence(params.get("confidence")),
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _insert_behavior_insight(self, db: Session, user: User, params: dict[str, Any]) -> int:
        insight_type = str(params.get("insight_type") or "")
        if insight_type not in ALLOWED_INSIGHTS:
            raise ValueError("unsupported insight type")
        row = BehaviorInsight(
            user_id=user.id,
            insight_type=insight_type,
            evidence_json=self._json_param(params.get("evidence_json")),
            confidence=self._confidence(params.get("confidence")),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _insert_fact(self, db: Session, user: User, params: dict[str, Any]) -> int:
        row = FinancialFact(
            user_id=user.id,
            fact_type=str(params.get("fact_type") or "user_profile")[:80],
            subject=str(params.get("subject") or "")[:200],
            value_json=self._json_param(params.get("value_json")),
            confidence=self._confidence(params.get("confidence")),
            valid_from=parse_relative_date(params.get("valid_from")) if params.get("valid_from") else None,
            valid_to=parse_relative_date(params.get("valid_to")) if params.get("valid_to") else None,
            is_active=bool(params.get("is_active", True)),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _insert_warning(self, db: Session, user: User, params: dict[str, Any]) -> int:
        row = FinancialWarning(
            user_id=user.id,
            warning_type=str(params.get("warning_type") or "general")[:80],
            severity=str(params.get("severity") or "info")[:30],
            message=str(params.get("message") or "")[:500],
            evidence_json=self._json_param(params.get("evidence_json")),
            status=str(params.get("status") or "active")[:30],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _insert_decision_log(self, db: Session, user: User, params: dict[str, Any]) -> int:
        row = FinancialDecisionLog(
            user_id=user.id,
            decision_title=str(params.get("decision_title") or "financial decision")[:200],
            decision_type=str(params.get("decision_type") or "general")[:80],
            input_json=self._json_param(params.get("input_json")),
            analysis_json=self._json_param(params.get("analysis_json")),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _add_user_scope(self, sql: str, table_name: str, user_id_column: str) -> str:
        qualified = f"{table_name}.{user_id_column}" if table_name and table_name in sql else user_id_column
        clause = f"{qualified} = :__current_user_id"
        if re.search(r"\bwhere\b", sql, re.IGNORECASE):
            return re.sub(r"\bwhere\b", f"WHERE {clause} AND", sql, count=1, flags=re.IGNORECASE)
        return re.sub(r"\b(order\s+by|limit)\b", f"WHERE {clause} \\1", sql, count=1, flags=re.IGNORECASE) if re.search(r"\b(order\s+by|limit)\b", sql, re.IGNORECASE) else f"{sql} WHERE {clause}"

    def _add_category_scope(self, sql: str) -> str:
        table_ref = "categories.user_id" if "categories" in sql else "user_id"
        clause = f"({table_ref} IS NULL OR {table_ref} = :__current_user_id)"
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

    def _json_param(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                return {"value": value}
        return {"value": value}

    def _confidence(self, value: Any) -> float:
        try:
            return max(0, min(float(value or 0), 1))
        except (TypeError, ValueError):
            return 0
