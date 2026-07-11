from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.services.agent_orchestrator.table_policy import llm_visible_policies
from app.services.agent_orchestrator.types import AgentOperationType, SchemaColumnInfo, SchemaTableInfo


def build_safe_schema(engine: Engine) -> list[SchemaTableInfo]:
    inspector = inspect(engine)
    result: list[SchemaTableInfo] = []

    for policy in llm_visible_policies():
        if not inspector.has_table(policy.table_name):
            continue

        fk_by_column: dict[str, str] = {}
        for fk in inspector.get_foreign_keys(policy.table_name):
            referred_table = fk.get("referred_table")
            constrained = fk.get("constrained_columns") or []
            referred_cols = fk.get("referred_columns") or []
            if referred_table and constrained:
                fk_by_column[constrained[0]] = f"{referred_table}.{referred_cols[0] if referred_cols else 'id'}"

        columns: list[SchemaColumnInfo] = []
        for column in inspector.get_columns(policy.table_name):
            name = column["name"]
            if name not in policy.selectable_columns or name in policy.forbidden_columns:
                continue
            columns.append(
                SchemaColumnInfo(
                    name=name,
                    type=str(column["type"]),
                    nullable=bool(column.get("nullable")),
                    foreign_key=fk_by_column.get(name),
                )
            )

        operations: list[AgentOperationType] = []
        if policy.allowed_select:
            operations.append(AgentOperationType.select)
        if policy.allowed_insert:
            operations.append(AgentOperationType.insert)
        if policy.allowed_update:
            operations.append(AgentOperationType.update)
        if policy.allowed_delete:
            operations.append(AgentOperationType.delete)

        result.append(
            SchemaTableInfo(
                table_name=policy.table_name,
                business_name=policy.business_name,
                allowed_operations=operations,
                columns=columns,
                user_scoped=policy.user_scoped,
                user_id_column=policy.user_id_column if policy.user_scoped else None,
                max_select_rows=policy.max_select_rows,
            )
        )

    return result
