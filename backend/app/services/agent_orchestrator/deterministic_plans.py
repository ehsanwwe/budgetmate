from __future__ import annotations

from app.services.agent_orchestrator.date_utils import detect_date_range
from app.services.agent_orchestrator.message_parser import detect_transaction_signal, normalize_text
from app.services.agent_orchestrator.types import AgentOperationType, AgentPlan, AgentPlanStep


def build_aggregate_plan(message: str) -> AgentPlan | None:
    text = normalize_text(message)
    is_question = any(token in text for token in ("چقدر", "چه قدر", "بیشترین", "بیش ترين", "مجموع"))
    if not is_question:
        return None

    range_key, start, end = detect_date_range(text)
    if "بیشترین" in text or "بیش ترین" in text or "بیشترين" in text:
        if "خرج" not in text and "هزینه" not in text:
            return None
        return AgentPlan(
            intent=f"aggregate:top_category:{range_key}:expense",
            requires_db=True,
            steps=[
                AgentPlanStep(
                    step_id="det_top_category",
                    operation_type=AgentOperationType.select,
                    purpose="deterministic top expense category",
                    table_name="transactions",
                    sql=(
                        "SELECT category_id, sum(amount) as total FROM transactions "
                        "WHERE type = :type AND date >= :start_date AND date < :end_date "
                        "GROUP BY category_id ORDER BY total DESC LIMIT 1"
                    ),
                    params={"type": "expense", "start_date": start.isoformat(), "end_date": end.isoformat()},
                    confidence=1,
                )
            ],
            confidence=1,
        )

    tx_type = None
    if "درآمد" in text or "در آمد" in text:
        tx_type = "income"
    elif "خرج" in text or "هزینه" in text:
        tx_type = "expense"
    if not tx_type:
        return None

    return AgentPlan(
        intent=f"aggregate:total:{range_key}:{tx_type}",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="det_total",
                operation_type=AgentOperationType.select,
                purpose="deterministic transaction total",
                table_name="transactions",
                sql=(
                    "SELECT sum(amount) as total FROM transactions "
                    "WHERE type = :type AND date >= :start_date AND date < :end_date"
                ),
                params={"type": tx_type, "start_date": start.isoformat(), "end_date": end.isoformat()},
                confidence=1,
            )
        ],
        confidence=1,
    )


def build_transaction_plan(message: str) -> AgentPlan | None:
    signal = detect_transaction_signal(message)
    if not signal or signal.tx_type != "income":
        return None
    return AgentPlan(
        intent="income_registration",
        requires_db=True,
        steps=[
            AgentPlanStep(
                step_id="det_income_insert",
                operation_type=AgentOperationType.insert,
                purpose="deterministic income registration",
                table_name="transactions",
                sql=(
                    "INSERT INTO transactions (amount, type, description, date) "
                    "VALUES (:amount, :type, :description, :date)"
                ),
                params={
                    "amount": signal.amount,
                    "type": "income",
                    "description": signal.description,
                    "date": signal.date,
                },
                confidence=1,
            )
        ],
        confidence=1,
    )
