from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.agent_orchestrator.context_builder import build_agent_context
from app.services.agent_orchestrator.deterministic_plans import build_aggregate_plan, build_transaction_plan
from app.services.agent_orchestrator.db_world import render_db_world
from app.services.agent_orchestrator.planner import AgentPlanner
from app.services.agent_orchestrator.response_composer import ResponseComposer
from app.services.agent_orchestrator.sql_executor import SqlExecutor, audit_operation
from app.services.agent_orchestrator.sql_validator import SqlValidator
from app.services.agent_orchestrator.types import AgentExecutionResult, AgentFinalResponse, AgentOperationType, AgentPlan, AgentPlanStep
from app.services.agent_orchestrator.message_parser import extract_amount
from app.services.personal_cfo.behavior_service import detect_basic_behavior_signals


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
        early_cfo_response = self._handle_personal_cfo_signal(db, user, user_message)
        if early_cfo_response and not build_aggregate_plan(user_message) and not extract_amount(user_message):
            return early_cfo_response

        plan = build_aggregate_plan(user_message)
        if not plan:
            plan = build_transaction_plan(user_message)
        if not plan:
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
                final = self.composer.compose(db, plan, all_results)
                detect_basic_behavior_signals(db, user.id, user_message, execution_payloads)
                return final
            if plan.intent.startswith("aggregate:"):
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

        final = self.composer.compose(db, plan, all_results, fallback_message=plan.final_response_hint or "")
        detect_basic_behavior_signals(db, user.id, user_message, execution_payloads)
        return final

    def _handle_personal_cfo_signal(self, db: Session, user: User, user_message: str) -> AgentFinalResponse | None:
        signals = detect_basic_behavior_signals(db, user.id, user_message, [])
        insight_types = {signal.get("insight_type") for signal in signals}
        if "stress_spending" in insight_types:
            return AgentFinalResponse(
                message="متوجه شدم که استرس می تواند یکی از محرک های خرج شما باشد. فعلا این را به عنوان یک الگوی احتمالی ثبت می کنم تا در تحلیل های بعدی دقیق تر بررسی شود.",
                metadata={"intent": "personal_cfo_signal", "signals": list(insight_types)},
            )
        if "debt_anxiety" in insight_types:
            return AgentFinalResponse(
                message="متوجه شدم که نسبت به بدهی حساسیت و نگرانی بالایی داری. این را به عنوان یک نکته مالی شخصی ثبت کردم تا پیشنهادهایم محتاطانه تر باشد.",
                metadata={"intent": "personal_cfo_signal", "signals": list(insight_types)},
            )
        if "liquidity_pressure" in insight_types or "end_of_month_overspending" in insight_types:
            return AgentFinalResponse(
                message="متوجه شدم آخر ماه فشار نقدینگی داری. این را به عنوان یک الگوی احتمالی ثبت کردم تا در تحلیل های بعدی خرج های آخر ماه را دقیق تر بررسی کنیم.",
                metadata={"intent": "personal_cfo_signal", "signals": list(insight_types)},
            )
        return None

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
