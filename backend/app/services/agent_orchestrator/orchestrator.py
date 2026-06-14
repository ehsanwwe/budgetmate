from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.agent_orchestrator.context_builder import build_agent_context
from app.services.agent_orchestrator.db_world import render_db_world
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.response_composer import ResponseComposer
from app.services.agent_orchestrator.sql_executor import SqlExecutor, audit_operation
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentOperationType, AgentPlan, AgentPlanStep


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

        for _ in range(3):
            if plan.clarification_question:
                return self.composer.compose(db, plan, all_results)

            actionable = [s for s in plan.steps if s.operation_type in {AgentOperationType.select, AgentOperationType.insert}]
            if not actionable:
                return self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint or "")

            progressed = False
            for step in actionable:
                result = self._validate_and_execute(db, user, plan, step)
                all_results.append(result)
                execution_payloads.append(result.model_dump(mode="json"))
                progressed = True
                if not result.allowed or result.error:
                    return self.composer.compose(db, plan, all_results)

            if not progressed:
                break

            if any(r.operation_type == AgentOperationType.insert and r.executed for r in all_results):
                return self.composer.compose(db, plan, all_results)
            if plan.final_response_hint:
                return self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint)

            plan = await self.planner.plan(
                db_world,
                user_message,
                finance_context,
                history=history,
                execution_results=execution_payloads,
            )

        return self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint or "")

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
