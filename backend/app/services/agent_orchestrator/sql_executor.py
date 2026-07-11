from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.agent_audit import AgentSqlAuditLog
from app.models.agent_idempotency import AgentOperationEvent
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
from app.services.personal_cfo.goal_context_service import find_goal_candidates, goal_match_score, normalize_goal_text
from app.services.personal_cfo.behavior_service import upsert_behavior_insight
from app.services.personal_cfo.memory_service import ALLOWED_MEMORY_TYPES

# Dedup window: skip duplicate writes within this window (prevents history replay)
_DEDUP_WINDOW_MINUTES = 60

# Params excluded from fingerprint (ephemeral/metadata, never affect semantic identity)
_FINGERPRINT_EXCLUDED = {"description", "notes_json", "metadata_json", "source", "content_json", "evidence_json", "confidence"}

# Generic Persian finance words stripped before semantic description comparison.
# These words appear in planner-generated descriptions but carry no merchant identity.
_TX_DESC_SKIP = frozenset({
    "هزینه", "پول", "پرداخت", "بابت", "برای", "تومان", "تومن",
    "دادم", "کردم", "خرید", "خریدم", "درآمد", "درامد",
    "بدهی", "پرداختی", "خرج", "مبلغ",
})

# Character normalization map for transaction description comparison
_TX_CHAR_NORM = str.maketrans({
    "ي": "ی", "ك": "ک", "ة": "ه", "ۀ": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def normalize_transaction_description(text: str) -> frozenset[str]:
    """Extract meaningful merchant/subject tokens from a transaction description.

    Strips generic Persian finance words so "اسنپ" and "هزینه اسنپ" both
    reduce to {"اسنپ"} and are recognised as the same merchant by semantic dedup.
    """
    if not text:
        return frozenset()
    normalized = text.translate(_TX_CHAR_NORM).replace("‌", " ").lower()
    return frozenset(t for t in normalized.split() if t not in _TX_DESC_SKIP and len(t) > 1)


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


def _compute_fingerprint(
    user_id: int,
    operation_type: str,
    table_name: str,
    params: dict[str, Any],
) -> str:
    """Stable hash of the semantic identity of a write operation."""
    key_params: dict[str, Any] = {}
    for k, v in sorted(params.items()):
        if k in _FINGERPRINT_EXCLUDED:
            continue
        # Normalize amounts so "47 ملیون" and 47000000 get the same hash
        if k in {"amount", "target_amount", "current_amount"}:
            try:
                v = normalize_amount(v)
            except Exception:
                pass
        elif k in {"date", "deadline", "due_date"}:
            try:
                parsed = normalize_date(v) if v else None
                v = parsed.isoformat() if parsed else None
            except Exception:
                pass
        elif k == "due_month" and isinstance(v, str):
            v = re.sub(r"\s+", " ", v.strip().lower())
        # Normalize goal/commitment titles so superficial wording changes hash identically.
        elif k == "title" and table_name in {"goals", "future_commitments"} and isinstance(v, str):
            v = normalize_goal_text(v)
        elif isinstance(v, str):
            v = v.lower().strip()
        key_params[k] = v

    payload = json.dumps(
        {"u": user_id, "op": operation_type, "t": table_name, "p": key_params},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:40]


class SqlExecutor:
    def execute(
        self,
        db: Session,
        user: User,
        step: AgentPlanStep,
        validation: SqlValidationResult,
        intent: str,
        seen_fingerprints: set[str] | None = None,
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

        # Compute idempotency fingerprint for write operations
        fingerprint: str | None = None
        if validation.operation_type in {AgentOperationType.insert, AgentOperationType.update}:
            fingerprint = _compute_fingerprint(
                user.id,
                validation.operation_type.value,
                validation.table_name or "",
                validation.params,
            )

            # Per-turn dedup: same fingerprint already executed this run
            if seen_fingerprints is not None and fingerprint in seen_fingerprints:
                audit_operation(db, user.id, intent, step, "skipped_duplicate", "duplicate within same turn", False)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=step.operation_type,
                    allowed=True,
                    executed=False,
                    skipped_duplicate=True,
                    operation_fingerprint=fingerprint,
                    summary="skipped duplicate write (same turn)",
                )

            # Cross-turn dedup: same fingerprint within the dedup window
            window_start = datetime.utcnow() - timedelta(minutes=_DEDUP_WINDOW_MINUTES)
            existing = (
                db.query(AgentOperationEvent)
                .filter(
                    AgentOperationEvent.user_id == user.id,
                    AgentOperationEvent.operation_fingerprint == fingerprint,
                    AgentOperationEvent.status == "executed",
                    AgentOperationEvent.created_at >= window_start,
                )
                .first()
            )
            if existing:
                audit_operation(db, user.id, intent, step, "skipped_duplicate", f"duplicate of event_id={existing.id}", False)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=step.operation_type,
                    allowed=True,
                    executed=False,
                    skipped_duplicate=True,
                    operation_fingerprint=fingerprint,
                    summary=f"skipped duplicate (already executed within {_DEDUP_WINDOW_MINUTES}m)",
                )

        # Semantic goal dedup: check active goals with similar title before any INSERT.
        if validation.operation_type == AgentOperationType.insert and validation.table_name == "goals":
            try:
                existing_goal_id = self._check_semantic_goal_duplicate(db, user, validation.params)
            except Exception:
                existing_goal_id = None
            if existing_goal_id is not None:
                audit_operation(db, user.id, intent, step, "skipped_duplicate",
                                f"active goal already exists id={existing_goal_id}", False)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=step.operation_type,
                    allowed=True,
                    executed=False,
                    skipped_duplicate=True,
                    operation_fingerprint=fingerprint,
                    existing_record_id=existing_goal_id,
                    summary=f"skipped duplicate goal (active goal id={existing_goal_id} already exists)",
                )

        # Semantic future-commitment dedup: the LLM/stream path can produce the same
        # obligation twice with slightly different non-semantic params. Block that here.
        if validation.operation_type == AgentOperationType.insert and validation.table_name == "future_commitments":
            try:
                existing_commitment_id = self._check_semantic_future_commitment_duplicate(db, user, validation.params)
            except Exception:
                existing_commitment_id = None
            if existing_commitment_id is not None:
                audit_operation(
                    db,
                    user.id,
                    intent,
                    step,
                    "skipped_duplicate",
                    f"pending future commitment already exists id={existing_commitment_id}",
                    False,
                )
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=step.operation_type,
                    allowed=True,
                    executed=False,
                    skipped_duplicate=True,
                    operation_fingerprint=fingerprint,
                    existing_record_id=existing_commitment_id,
                    summary=f"skipped duplicate future commitment (id={existing_commitment_id} already exists)",
                )

        # Semantic transaction dedup: catches the case where the planner creates one
        # INSERT without category_id and then another INSERT with category_id but the same
        # expense (e.g. "اسنپ" then "هزینه اسنپ" for the same 200k transport expense).
        # The fingerprint dedup misses this because category_id changes the hash.
        if validation.operation_type == AgentOperationType.insert and validation.table_name == "transactions":
            try:
                existing_tx_id = self._check_semantic_transaction_duplicate(db, user, validation.params)
            except Exception:
                existing_tx_id = None
            if existing_tx_id is not None:
                audit_operation(
                    db,
                    user.id,
                    intent,
                    step,
                    "skipped_duplicate",
                    f"semantic duplicate transaction already exists id={existing_tx_id}",
                    False,
                )
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=step.operation_type,
                    allowed=True,
                    executed=False,
                    skipped_duplicate=True,
                    operation_fingerprint=fingerprint,
                    existing_record_id=existing_tx_id,
                    summary=f"skipped duplicate transaction (id={existing_tx_id} already exists within dedup window)",
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

            if validation.operation_type == AgentOperationType.delete:
                deleted_ids = self._execute_delete(db, user, validation)
                summary = {"deleted_ids": deleted_ids, "deleted_count": len(deleted_ids)}
                audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=AgentOperationType.delete,
                    allowed=True,
                    executed=True,
                    deleted_ids=deleted_ids,
                    deleted_row_count=len(deleted_ids),
                    summary=(
                        f"deleted {len(deleted_ids)} row(s)"
                        if deleted_ids
                        else "no matching row to delete"
                    ),
                )

            if validation.operation_type == AgentOperationType.update:
                updated_id = self._execute_update(db, user, validation)
                summary = {"updated_id": updated_id}
                audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
                self._record_operation_event(db, user.id, fingerprint, "update", validation.table_name or "", updated_id, validation.params)
                return AgentExecutionResult(
                    step_id=step.step_id,
                    operation_type=AgentOperationType.update,
                    allowed=True,
                    executed=True,
                    updated_id=updated_id,
                    operation_fingerprint=fingerprint,
                    summary=f"updated row {updated_id}",
                )

            inserted_id = self._execute_insert(db, user, validation)
            summary = {"inserted_id": inserted_id}
            audit_operation(db, user.id, intent, step, "allowed", executed=True, result_summary=summary)
            self._record_operation_event(db, user.id, fingerprint, "insert", validation.table_name or "", inserted_id, validation.params)
            return AgentExecutionResult(
                step_id=step.step_id,
                operation_type=AgentOperationType.insert,
                allowed=True,
                executed=True,
                inserted_id=inserted_id,
                operation_fingerprint=fingerprint,
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

    def _record_operation_event(
        self,
        db: Session,
        user_id: int,
        fingerprint: str | None,
        operation_type: str,
        table_name: str,
        target_id: int | None,
        params: dict[str, Any],
    ) -> None:
        if not fingerprint:
            return
        try:
            event = AgentOperationEvent(
                user_id=user_id,
                operation_fingerprint=fingerprint,
                operation_type=operation_type,
                table_name=table_name,
                target_record_id=target_id,
                status="executed",
                payload_json=params,
            )
            db.add(event)
            db.commit()
        except Exception:
            db.rollback()

    def _check_semantic_goal_duplicate(self, db: Session, user: User, params: dict[str, Any]) -> int | None:
        """Return existing active goal id if a semantically identical goal already exists."""
        title = str(params.get("title") or "").strip()
        if not title:
            return None
        target_amount: int | None = None
        try:
            if params.get("target_amount") is not None:
                target_amount = normalize_amount(params["target_amount"])
        except Exception:
            pass
        normalized_incoming = normalize_goal_text(title)
        candidates = find_goal_candidates(db, user.id, title)
        for candidate in candidates:
            normalized_existing = normalize_goal_text(candidate.title or "")
            amounts_match = target_amount is not None and candidate.target_amount == target_amount
            no_amount = target_amount is None
            # Exact normalized title match
            if normalized_incoming and normalized_existing == normalized_incoming:
                if amounts_match or no_amount:
                    return candidate.id
            # High semantic similarity
            score = goal_match_score(title, candidate.title or "")
            if amounts_match:
                if score >= 0.55:
                    return candidate.id
            elif no_amount and score >= 0.80:
                return candidate.id
        return None

    def _check_semantic_future_commitment_duplicate(self, db: Session, user: User, params: dict[str, Any]) -> int | None:
        """Return an existing pending commitment id for the same obligation.

        This catches duplicate writes when the planner returns repeated INSERTs,
        a repair loop replays the same obligation with slightly different
        metadata, or the frontend/stream path submits the same turn twice.
        """
        title = str(params.get("title") or "").strip()
        if not title:
            return None

        try:
            amount = normalize_amount(params.get("amount"))
        except Exception:
            return None
        if amount <= 0:
            return None

        incoming_due_date = None
        if params.get("due_date"):
            try:
                incoming_due_date = normalize_date(params.get("due_date"))
            except Exception:
                incoming_due_date = None
        incoming_due_month = str(params.get("due_month") or "").strip().lower() or None
        incoming_norm = normalize_goal_text(title)
        window_start = datetime.utcnow() - timedelta(minutes=_DEDUP_WINDOW_MINUTES)

        candidates = (
            db.query(FutureCommitment)
            .filter(
                FutureCommitment.user_id == user.id,
                FutureCommitment.status == str(params.get("status") or "pending")[:30],
                FutureCommitment.amount == amount,
                FutureCommitment.created_at >= window_start,
            )
            .all()
        )

        for candidate in candidates:
            existing_norm = normalize_goal_text(candidate.title or "")
            title_matches = bool(incoming_norm and existing_norm == incoming_norm) or goal_match_score(title, candidate.title or "") >= 0.75
            if not title_matches:
                continue

            due_matches = False
            if incoming_due_date and candidate.due_date:
                due_matches = incoming_due_date == candidate.due_date
            elif incoming_due_month and candidate.due_month:
                due_matches = incoming_due_month == str(candidate.due_month).strip().lower()
            else:
                # If one representation is missing/different but the duplicate was created
                # in the recent replay window with same title+amount, treat it as duplicate.
                due_matches = True

            if due_matches:
                return int(candidate.id)

        return None

    def _check_semantic_transaction_duplicate(self, db: Session, user: User, params: dict[str, Any]) -> int | None:
        """Return the id of an existing transaction that is semantically identical to params.

        Two transaction inserts are considered duplicates when they share the same
        user, type, amount, and date within the dedup window AND their meaningful
        description tokens overlap significantly (subset or high Jaccard score).

        This catches the planner pattern of inserting "اسنپ" in one iteration and
        "هزینه اسنپ" with a category_id in the next — both reduce to token {"اسنپ"}.
        """
        tx_type_raw = str(params.get("type", "")).strip()
        if tx_type_raw not in {"expense", "income"}:
            return None
        try:
            amount = normalize_amount(params.get("amount", 0))
        except Exception:
            return None
        if amount < 1000:
            return None

        tx_date = None
        try:
            if params.get("date"):
                tx_date = normalize_date(params["date"])
        except Exception:
            pass

        tx_type = TransactionType.income if tx_type_raw == "income" else TransactionType.expense
        window_start = datetime.utcnow() - timedelta(minutes=_DEDUP_WINDOW_MINUTES)

        query = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.type == tx_type,
                Transaction.amount == amount,
                Transaction.created_at >= window_start,
            )
        )
        if tx_date is not None:
            query = query.filter(Transaction.date == tx_date)

        candidates = query.all()
        if not candidates:
            return None

        incoming_tokens = normalize_transaction_description(str(params.get("description") or ""))

        for candidate in candidates:
            existing_tokens = normalize_transaction_description(str(candidate.description or ""))

            # No meaningful tokens in either — amount/type/date match is sufficient
            if not incoming_tokens or not existing_tokens:
                return int(candidate.id)

            # Subset: "اسنپ" ⊆ "هزینه اسنپ" or vice versa → same merchant
            if incoming_tokens.issubset(existing_tokens) or existing_tokens.issubset(incoming_tokens):
                return int(candidate.id)

            # High token overlap → same merchant
            jaccard = len(incoming_tokens & existing_tokens) / len(incoming_tokens | existing_tokens)
            if jaccard >= 0.6:
                return int(candidate.id)

        return None

    def _execute_delete(self, db: Session, user: User, validation: SqlValidationResult) -> list[int]:
        """Execute a policy-approved DELETE, scoped to the authenticated user.

        Strategy:
          1. Read the matching row ids using the same WHERE, adding user-scope.
          2. Perform the DELETE by id list so ownership is authoritative and
             we return the exact list of removed ids.
          3. Empty match returns [] (never raises) so the LLM can report
             "no matching record found" honestly.
        """
        table = validation.table_name or ""
        policy = get_policy(table)
        if not policy:
            raise ValueError("delete target has no policy")
        base_where = self._extract_where(validation.sql or "")
        if not base_where:
            raise ValueError("DELETE missing WHERE")

        scoped_where = base_where
        params = dict(validation.params)
        if policy.user_scoped and policy.user_id_column:
            scoped_where = f"({base_where}) AND {policy.user_id_column} = :__current_user_id"
            params["__current_user_id"] = user.id

        # Discover the ids so we can report them
        select_sql = f"SELECT id FROM {table} WHERE {scoped_where}"
        rows = db.execute(text(select_sql), params).mappings().all()
        matched_ids = [int(row["id"]) for row in rows if row.get("id") is not None]
        if not matched_ids:
            return []

        # Use the id list to perform a definitive scoped delete
        id_params = {f"__del_id_{i}": mid for i, mid in enumerate(matched_ids)}
        placeholders = ", ".join(f":{k}" for k in id_params.keys())
        delete_sql = f"DELETE FROM {table} WHERE id IN ({placeholders})"
        if policy.user_scoped and policy.user_id_column:
            delete_sql += f" AND {policy.user_id_column} = :__current_user_id"
        del_params: dict[str, Any] = {**id_params}
        if policy.user_scoped and policy.user_id_column:
            del_params["__current_user_id"] = user.id
        db.execute(text(delete_sql), del_params)
        db.commit()
        return matched_ids

    def _extract_where(self, sql: str) -> str:
        match = re.search(r"\bwhere\b(.+)$", sql.strip(), re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return match.group(1).strip().rstrip(";").strip()

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
