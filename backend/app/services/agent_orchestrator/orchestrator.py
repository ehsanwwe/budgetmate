from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User
from app.services.agent_orchestrator.context_builder import build_agent_context
from app.services.agent_orchestrator.db_world import render_db_world
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.response_composer import ResponseComposer
from app.services.agent_orchestrator.sql_executor import SqlExecutor, audit_operation
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import (
    AgentExecutionResult,
    AgentFinalResponse,
    AgentOperationType,
    AgentPlan,
    AgentPlanStep,
)

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    def __init__(
        self,
        planner: AgentPlanner | None = None,
        validator: SqlValidator | None = None,
        executor: SqlExecutor | None = None,
        composer: ResponseComposer | None = None,
    ):
        self.planner = planner or AgentPlanner()
        self.validator = validator or SqlValidator()
        self.executor = executor or SqlExecutor()
        self.composer = composer or ResponseComposer()

    async def run(
        self,
        db: Session,
        user: User,
        user_message: str,
        history: list[dict] | None = None,
        chat_mode: str | None = None,
    ) -> AgentFinalResponse:
        db_world = render_db_world(db.get_bind())
        finance_context = build_agent_context(user, db)
        if chat_mode:
            finance_context.setdefault("user", {})["chat_mode"] = chat_mode

        all_results: list[AgentExecutionResult] = []
        execution_payloads: list[dict[str, Any]] = []
        plan = await self.planner.plan(db_world, user_message, finance_context, history=history)
        last_action_plan: AgentPlan | None = None
        last_plan: AgentPlan = plan

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
                return self.composer.compose(db, plan, all_results)

            actionable = [
                s
                for s in plan.steps
                if s.operation_type in {AgentOperationType.select, AgentOperationType.insert, AgentOperationType.update}
            ]
            if not actionable:
                if last_action_plan and all_results:
                    composed_plan = last_action_plan.model_copy(update={"final_response_hint": plan.final_response_hint})
                    return self.composer.compose(db, composed_plan, all_results, fallback_message=plan.final_response_hint or "")
                return self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint or "")

            last_action_plan = plan
            had_repairable_failure = False
            for step in actionable:
                result = self._validate_and_execute(db, user, plan, step)
                if settings.AGENT_DEBUG_TRACE:
                    logger.info(
                        "agent step validation step_id=%s operation=%s allowed=%s executed=%s",
                        step.step_id,
                        step.operation_type.value,
                        result.allowed,
                        result.executed,
                    )
                all_results.append(result)
                execution_payloads.append(result.model_dump(mode="json"))
                if not result.allowed or result.error:
                    if self._is_clearly_malicious(result):
                        return self.composer.compose(db, plan, all_results)
                    had_repairable_failure = True
                    break

            plan = await self.planner.plan(
                db_world,
                user_message,
                finance_context,
                history=history,
                execution_results=execution_payloads,
            )
            if had_repairable_failure:
                continue

        return self.composer.compose(db, last_action_plan or last_plan, all_results, fallback_message=last_plan.final_response_hint or "")

    def _validate_and_execute(
        self,
        db: Session,
        user: User,
        plan: AgentPlan,
        step: AgentPlanStep,
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
        return self.executor.execute(db, user, step, validation, plan.intent)

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
