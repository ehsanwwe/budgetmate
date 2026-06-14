from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_audit import AgentSqlAuditLog
from app.models.category import Category
from app.models.future_commitment import FutureCommitment
from app.models.goal import Goal
from app.models.personal_cfo import BehaviorInsight, FinancialDecisionLog, FinancialFact, FinancialMemory, FinancialPersona, FinancialWarning
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.services.agent_orchestrator.date_utils import parse_relative_date
from app.services.agent_orchestrator.table_policy import get_policy
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentOperationType, AgentPlanStep, SqlValidationResult
from app.services.agent_orchestrator.value_normalizer import normalize_amount, normalize_date
from app.services.personal_cfo.behavior_service import ALLOWED_INSIGHTS
from app.services.personal_cfo.behavior_service import upsert_behavior_insight
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

            if validation.operation_type == AgentOperationType.update:
                updated_id = self._execute_update(db, user, validation)
                summary = {"updated_id": updated_id}
                audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=AgentOperationType.update,
                    allowed=True,
                    executed=True,
                    updated_id=updated_id,
                    summary=f"updated row {updated_id}",
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
        if table == "goals":
            return self._insert_goal(db, user, params)
        if table == "future_commitments":
            return self._insert_future_commitment(db, user, params)
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

    def _execute_update(self, db: Session, user: User, validation: SqlValidationResult) -> int:
        table = validation.table_name
        params = dict(validation.params)
        assignments = self._parse_update_assignments(validation.sql or "")
        row_id = self._parse_update_row_id(validation.sql or "", params)
        if table == "goals":
            return self._update_goal(db, user, row_id, assignments, params)
        if table == "future_commitments":
            return self._update_future_commitment(db, user, row_id, assignments, params)
        if table == "financial_personas":
            return self._update_persona(db, user, row_id, assignments, params)
        if table == "financial_memories":
            return self._update_memory(db, user, row_id, assignments, params)
        if table == "behavior_insights":
            return self._update_behavior_insight(db, user, row_id, assignments, params)
        if table == "financial_facts":
            return self._update_fact(db, user, row_id, assignments, params)
        if table == "financial_warnings":
            return self._update_warning(db, user, row_id, assignments, params)
        raise ValueError("UPDATE on this table is not enabled")

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

    def _insert_goal(self, db: Session, user: User, params: dict[str, Any]) -> int:
        title = str(params.get("title") or "").strip()
        if not title:
            raise ValueError("goal title is required")
        if params.get("target_amount") is None:
            raise ValueError("goal target_amount is required")
        target_amount = normalize_amount(params.get("target_amount"))
        if target_amount <= 0:
            raise ValueError("goal target_amount must be positive")
        current_amount = normalize_amount(params.get("current_amount") or 0)
        status = str(params.get("status") or "active")
        goal = Goal(
            user_id=user.id,
            title=title[:200],
            target_amount=target_amount,
            current_amount=max(0, min(current_amount, target_amount)),
            deadline=normalize_date(params.get("deadline")) if params.get("deadline") else None,
            status=status,
            is_active=bool(params.get("is_active", status != "archived")),
            notes_json=self._json_param(params.get("notes_json")) if params.get("notes_json") is not None else None,
        )
        db.add(goal)
        db.commit()
        db.refresh(goal)
        return int(goal.id)

    def _insert_future_commitment(self, db: Session, user: User, params: dict[str, Any]) -> int:
        title = str(params.get("title") or "").strip()
        if not title:
            raise ValueError("future commitment title is required")
        amount = normalize_amount(params.get("amount"))
        if amount <= 0:
            raise ValueError("future commitment amount must be positive")
        category_id = self._visible_category_id(db, user, params.get("category_id"))
        row = FutureCommitment(
            user_id=user.id,
            title=title[:200],
            amount=amount,
            due_date=normalize_date(params.get("due_date")) if params.get("due_date") else None,
            due_month=str(params.get("due_month"))[:40] if params.get("due_month") else None,
            category_id=category_id,
            related_transaction_id=self._visible_transaction_id(db, user, params.get("related_transaction_id")),
            related_goal_id=self._visible_goal_id(db, user, params.get("related_goal_id")),
            description=str(params.get("description") or "")[:1000] or None,
            status=str(params.get("status") or "pending")[:30],
            source=str(params.get("source") or "chat")[:50],
            metadata_json=self._json_param(params.get("metadata_json")) if params.get("metadata_json") is not None else None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_goal(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        goal = db.query(Goal).filter(Goal.id == row_id, Goal.user_id == user.id).first()
        if not goal:
            raise ValueError("goal is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column in {"target_amount", "current_amount"}:
                setattr(goal, column, normalize_amount(value))
            elif column == "deadline":
                goal.deadline = normalize_date(value) if value else None
            elif column == "title":
                goal.title = str(value)[:200]
            elif column == "status":
                goal.status = str(value)[:30]
                if goal.status == "archived":
                    goal.is_active = False
            elif column == "is_active":
                goal.is_active = bool(value)
                if not goal.is_active:
                    goal.status = "archived"
            elif column == "notes_json":
                goal.notes_json = self._json_param(value)
        db.commit()
        db.refresh(goal)
        return int(goal.id)

    def _update_future_commitment(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(FutureCommitment).filter(FutureCommitment.id == row_id, FutureCommitment.user_id == user.id).first()
        if not row:
            raise ValueError("future commitment is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column == "amount":
                row.amount = normalize_amount(value)
            elif column == "due_date":
                row.due_date = normalize_date(value) if value else None
            elif column == "category_id":
                row.category_id = self._visible_category_id(db, user, value)
            elif column == "related_goal_id":
                row.related_goal_id = self._visible_goal_id(db, user, value)
            elif column == "related_transaction_id":
                row.related_transaction_id = self._visible_transaction_id(db, user, value)
            elif column == "metadata_json":
                row.metadata_json = self._json_param(value)
            else:
                setattr(row, column, str(value)[:1000] if value is not None else None)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_persona(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(FinancialPersona).filter(FinancialPersona.id == row_id, FinancialPersona.user_id == user.id).first()
        if not row:
            raise ValueError("persona is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column == "discipline_score":
                row.discipline_score = self._confidence(value)
            elif column == "confidence":
                row.confidence = self._confidence(value)
            elif column in {"emotional_spending_triggers_json", "notes_json"}:
                setattr(row, column, self._json_param(value))
            else:
                setattr(row, column, str(value)[:200] if value is not None else None)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_memory(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(FinancialMemory).filter(FinancialMemory.id == row_id, FinancialMemory.user_id == user.id).first()
        if not row:
            raise ValueError("memory is not available to the current user")
        for column, param_name in assignments.items():
            if column == "is_active":
                row.is_active = bool(params[param_name])
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_behavior_insight(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(BehaviorInsight).filter(BehaviorInsight.id == row_id, BehaviorInsight.user_id == user.id).first()
        if not row:
            raise ValueError("behavior insight is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column == "evidence_json":
                row.evidence_json = self._json_param(value)
            elif column == "confidence":
                row.confidence = self._confidence(value)
            elif column == "is_active":
                row.is_active = bool(value)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_fact(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(FinancialFact).filter(FinancialFact.id == row_id, FinancialFact.user_id == user.id).first()
        if not row:
            raise ValueError("financial fact is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column == "value_json":
                row.value_json = self._json_param(value)
            elif column == "confidence":
                row.confidence = self._confidence(value)
            elif column in {"valid_from", "valid_to"}:
                setattr(row, column, parse_relative_date(value) if value else None)
            elif column == "is_active":
                row.is_active = bool(value)
        db.commit()
        db.refresh(row)
        return int(row.id)

    def _update_warning(self, db: Session, user: User, row_id: int, assignments: dict[str, str], params: dict[str, Any]) -> int:
        row = db.query(FinancialWarning).filter(FinancialWarning.id == row_id, FinancialWarning.user_id == user.id).first()
        if not row:
            raise ValueError("financial warning is not available to the current user")
        for column, param_name in assignments.items():
            value = params[param_name]
            if column == "status":
                row.status = str(value)[:30]
            elif column == "resolved_at":
                row.resolved_at = datetime.utcnow() if value in {True, "now", "امروز"} else None
        db.commit()
        db.refresh(row)
        return int(row.id)

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
        row = upsert_behavior_insight(
            db,
            user.id,
            insight_type,
            self._json_param(params.get("evidence_json")),
            self._confidence(params.get("confidence")),
        )
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

    def _parse_update_assignments(self, sql: str) -> dict[str, str]:
        match = re.search(r"\bset\b(.+?)\bwhere\b", sql, re.IGNORECASE | re.DOTALL)
        if not match:
            raise ValueError("invalid UPDATE assignments")
        assignments: dict[str, str] = {}
        for item in match.group(1).split(","):
            col, param = item.split("=", 1)
            assignments[col.strip().lower()] = param.strip()[1:]
        return assignments

    def _parse_update_row_id(self, sql: str, params: dict[str, Any]) -> int:
        match = re.search(r"\bwhere\s+id\s*=\s*:([a-zA-Z_][\w]*)\s*$", sql, re.IGNORECASE)
        if not match:
            raise ValueError("invalid UPDATE target")
        return int(params[match.group(1)])

    def _visible_category_id(self, db: Session, user: User, category_id: Any) -> int | None:
        if category_id is None:
            return None
        category = db.query(Category).filter(Category.id == int(category_id)).first()
        if not category or (not category.is_default and category.user_id != user.id):
            raise ValueError("category_id is not available to the current user")
        return int(category.id)

    def _visible_goal_id(self, db: Session, user: User, goal_id: Any) -> int | None:
        if goal_id is None:
            return None
        goal = db.query(Goal).filter(Goal.id == int(goal_id), Goal.user_id == user.id).first()
        if not goal:
            raise ValueError("goal_id is not available to the current user")
        return int(goal.id)

    def _visible_transaction_id(self, db: Session, user: User, transaction_id: Any) -> int | None:
        if transaction_id is None:
            return None
        txn = db.query(Transaction).filter(Transaction.id == int(transaction_id), Transaction.user_id == user.id).first()
        if not txn:
            raise ValueError("related_transaction_id is not available to the current user")
        return int(txn.id)

    def _add_user_scope(self, sql: str, table_name: str, user_id_column: str) -> str:
        qualified = f"{table_name}.{user_id_column}" if table_name and table_name in sql else user_id_column
        clause = f"{qualified} = :__current_user_id"
        if re.search(r"\bwhere\b", sql, re.IGNORECASE):
            return re.sub(r"\bwhere\b", f"WHERE {clause} AND", sql, count=1, flags=re.IGNORECASE)
        return re.sub(r"\b(group\s+by|having|order\s+by|limit)\b", f"WHERE {clause} \\1", sql, count=1, flags=re.IGNORECASE) if re.search(r"\b(group\s+by|having|order\s+by|limit)\b", sql, re.IGNORECASE) else f"{sql} WHERE {clause}"

    def _add_category_scope(self, sql: str) -> str:
        table_ref = "categories.user_id" if "categories" in sql else "user_id"
        clause = f"({table_ref} IS NULL OR {table_ref} = :__current_user_id)"
        if re.search(r"\bwhere\b", sql, re.IGNORECASE):
            return re.sub(r"\bwhere\b", f"WHERE {clause} AND", sql, count=1, flags=re.IGNORECASE)
        return re.sub(r"\b(group\s+by|having|order\s+by|limit)\b", f"WHERE {clause} \\1", sql, count=1, flags=re.IGNORECASE) if re.search(r"\b(group\s+by|having|order\s+by|limit)\b", sql, re.IGNORECASE) else f"{sql} WHERE {clause}"

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
