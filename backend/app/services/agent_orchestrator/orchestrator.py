from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services.agent_orchestrator.context_builder import build_agent_context
from app.services.agent_orchestrator.db_world import render_db_world
from app.services.agent_orchestrator.goal_intake import GOAL_INTENT_TYPE, GoalIntakeGate
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.response_composer import ResponseComposer
from app.services.agent_orchestrator.semantic_interpreter import SemanticInterpreter, SemanticResult
from app.services.agent_orchestrator.sql_executor import SqlExecutor, audit_operation
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import (
    AgentExecutionResult,
    AgentFinalResponse,
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
    SourceScope,
)

logger = logging.getLogger(__name__)

_WRITE_OPS = {AgentOperationType.insert, AgentOperationType.update}


class _NullGate:
    """No-op gate — passes every message through to the orchestrator unchanged."""
    async def process(self, *args: Any, **kwargs: Any) -> None:
        return None


class AgentOrchestrator:
    def __init__(
        self,
        planner: AgentPlanner | None = None,
        validator: SqlValidator | None = None,
        executor: SqlExecutor | None = None,
        composer: ResponseComposer | None = None,
        goal_intake_gate: GoalIntakeGate | None = None,
    ):
        self.planner = planner or AgentPlanner()
        self.validator = validator or SqlValidator()
        self.executor = executor or SqlExecutor()
        self.composer = composer or ResponseComposer()
        # Accepts an explicit gate so callers (e.g. tests) can bypass or stub it.
        # Defaults to the real GoalIntakeGate for production use.
        self._gate = goal_intake_gate if goal_intake_gate is not None else GoalIntakeGate()

    async def run(
        self,
        db: Session,
        user: User,
        user_message: str,
        history: list[dict] | None = None,
        chat_mode: str | None = None,
        client_message_id: str | None = None,
    ) -> AgentFinalResponse:
        locale: str = getattr(user, "language", None) or "fa"

        # Cross-request idempotency: if client_message_id is provided and we already processed
        # it, return a cached no-op instead of re-executing writes.
        if client_message_id:
            if self._is_already_processed(db, user.id, client_message_id):
                logger.info(
                    "agent skipping duplicate request client_message_id=%s user=%s",
                    client_message_id,
                    user.id,
                )
                return AgentFinalResponse(
                    message="این درخواست قبلاً پردازش شده است.",
                    metadata={"idempotent_skip": True, "client_message_id": client_message_id},
                )
            self._mark_processing(db, user.id, client_message_id)

        db_world = render_db_world(db.get_bind())
        finance_context = build_agent_context(user, db)
        if chat_mode:
            finance_context.setdefault("user", {})["chat_mode"] = chat_mode

        # SemanticInterpreter runs first — one LLM call that understands the full
        # message context so gate and planner can use the result rather than each
        # making their own classification calls.
        pending_payload = self._get_pending_intent_payload(db, user)
        semantic: SemanticResult = await SemanticInterpreter().interpret(
            user_message=user_message,
            history=history,
            pending_intent_payload=pending_payload,
            finance_context=finance_context,
        )

        # Goal intake gate runs next — intercepts goal-like messages and manages
        # the decision gate (collect missing info → add vs consult → advisory or insert).
        gate_response = await self._gate.process(
            db, user, user_message, history, finance_context, semantic=semantic
        )
        if gate_response is not None:
            return gate_response

        all_results: list[AgentExecutionResult] = []
        execution_payloads: list[dict[str, Any]] = []
        plan = await self.planner.plan(
            db_world,
            user_message,
            finance_context,
            history=history,
            semantic_interpretation=semantic.raw if semantic else None,
        )
        last_action_plan: AgentPlan | None = None
        last_plan: AgentPlan = plan

        # Per-turn fingerprint dedup: prevent the same write executing twice in one run
        seen_fingerprints: set[str] = set()

        for _ in range(5):
            last_plan = plan
            if settings.AGENT_DEBUG_TRACE:
                logger.info(
                    "agent planner iteration intent=%s step_count=%s operation_types=%s",
                    plan.intent,
                    len(plan.steps),
                    [step.operation_type.value for step in plan.steps],
                )
            if plan.clarification_question:
                return self.composer.compose(db, plan, all_results, locale=locale)

            actionable = [
                s
                for s in plan.steps
                if s.operation_type in {AgentOperationType.select, AgentOperationType.insert, AgentOperationType.update}
            ]
            if not actionable:
                if last_action_plan and all_results:
                    composed_plan = last_action_plan.model_copy(update={"final_response_hint": plan.final_response_hint})
                    return self.composer.compose(db, composed_plan, all_results, fallback_message=plan.final_response_hint or "", locale=locale)
                return self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint or "", locale=locale)

            last_action_plan = plan
            had_repairable_failure = False
            for step in actionable:
                # CURRENT-TURN EXECUTION GUARD: reject writes inferred from history
                if step.operation_type in _WRITE_OPS and step.source_scope == SourceScope.history_context:
                    logger.warning(
                        "agent blocked history_context write step_id=%s table=%s intent=%s",
                        step.step_id,
                        step.table_name,
                        plan.intent,
                    )
                    audit_operation(db, user.id, plan.intent, step, "rejected", "write from history_context is not allowed", False)
                    result = AgentExecutionResult(
                        step_id=step.step_id,
                        operation_type=step.operation_type,
                        allowed=False,
                        executed=False,
                        rejected_reason="write from history_context is not allowed",
                    )
                    all_results.append(result)
                    execution_payloads.append(result.model_dump(mode="json"))
                    had_repairable_failure = True
                    break

                result = self._validate_and_execute(db, user, plan, step, seen_fingerprints)
                if settings.AGENT_DEBUG_TRACE:
                    logger.info(
                        "agent step validation step_id=%s operation=%s allowed=%s executed=%s skipped_duplicate=%s",
                        step.step_id,
                        step.operation_type.value,
                        result.allowed,
                        result.executed,
                        result.skipped_duplicate,
                    )
                all_results.append(result)
                execution_payloads.append(result.model_dump(mode="json"))

                # Track fingerprint to prevent intra-turn duplication
                if result.operation_fingerprint:
                    seen_fingerprints.add(result.operation_fingerprint)

                if not result.allowed or result.error:
                    if self._is_clearly_malicious(result):
                        return self.composer.compose(db, plan, all_results, locale=locale)
                    had_repairable_failure = True
                    break

            plan = await self.planner.plan(
                db_world,
                user_message,
                finance_context,
                history=history,
                execution_results=execution_payloads,
                semantic_interpretation=semantic.raw if semantic else None,
            )
            if had_repairable_failure:
                continue

        return self.composer.compose(db, last_action_plan or last_plan, all_results, fallback_message=last_plan.final_response_hint or "", locale=locale)

    def _validate_and_execute(
        self,
        db: Session,
        user: User,
        plan: AgentPlan,
        step: AgentPlanStep,
        seen_fingerprints: set[str],
    ) -> AgentExecutionResult:
        try:
            validation = self.validator.validate(step.operation_type, step.table_name, step.sql, step.params)
        except Exception as exc:
            audit_operation(db, user.id, plan.intent, step, "rejected", str(exc), False)
            return AgentExecutionResult(
                step_id=step.step_id,
                operation_type=step.operation_type,
                allowed=False,
                executed=False,
                rejected_reason=str(exc),
            )
        return self.executor.execute(db, user, step, validation, plan.intent, seen_fingerprints)

    def _is_clearly_malicious(self, result: AgentExecutionResult) -> bool:
        reason = (result.rejected_reason or result.error or "").lower()
        return any(
            marker in reason
            for marker in (
                "destructive",
                "administrative",
                "forbidden",
                "multiple statements",
                "comments",
                "cannot set user_id",
            )
        )

    @staticmethod
    def _cmid_fingerprint(user_id: int, client_message_id: str) -> str:
        import hashlib
        raw = f"cmid:{user_id}:{client_message_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:64]

    def _is_already_processed(self, db: Session, user_id: int, client_message_id: str) -> bool:
        try:
            from app.models.agent_idempotency import AgentOperationEvent
            fp = self._cmid_fingerprint(user_id, client_message_id)
            return (
                db.query(AgentOperationEvent)
                .filter(
                    AgentOperationEvent.user_id == user_id,
                    AgentOperationEvent.operation_fingerprint == fp,
                )
                .first()
            ) is not None
        except Exception:
            return False

    def _get_pending_intent_payload(self, db: Session, user: User) -> dict | None:
        try:
            from app.models.agent_idempotency import PendingAgentIntent
            intent = (
                db.query(PendingAgentIntent)
                .filter(
                    PendingAgentIntent.user_id == user.id,
                    PendingAgentIntent.intent_type == GOAL_INTENT_TYPE,
                    PendingAgentIntent.status == "pending",
                )
                .order_by(PendingAgentIntent.updated_at.desc())
                .first()
            )
            return dict(intent.payload_json) if intent else None
        except Exception:
            return None

    def _mark_processing(self, db: Session, user_id: int, client_message_id: str) -> None:
        try:
            from app.models.agent_idempotency import AgentOperationEvent
            fp = self._cmid_fingerprint(user_id, client_message_id)
            event = AgentOperationEvent(
                user_id=user_id,
                operation_fingerprint=fp,
                operation_type="request_guard",
                table_name="_request",
                status="executed",
            )
            db.add(event)
            db.commit()
        except Exception as exc:
            logger.debug("Could not mark client_message_id processing: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
