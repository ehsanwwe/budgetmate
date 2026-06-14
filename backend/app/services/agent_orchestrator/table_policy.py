from __future__ import annotations

from app.services.agent_orchestrator.types import TablePolicy


POLICIES: dict[str, TablePolicy] = {
    "categories": TablePolicy(
        table_name="categories",
        business_name="financial categories available to the current user",
        allowed_select=True,
        allowed_insert=False,
        user_scoped=False,
        selectable_columns={"id", "name", "icon", "color", "is_default", "user_id"},
        forbidden_columns=set(),
        max_select_rows=50,
    ),
    "transactions": TablePolicy(
        table_name="transactions",
        business_name="current user's income and expense transactions",
        allowed_select=True,
        allowed_insert=True,
        user_scoped=True,
        user_id_column="user_id",
        selectable_columns={"id", "category_id", "amount", "type", "description", "date", "created_at"},
        insertable_columns={"category_id", "amount", "type", "description", "date"},
        forbidden_columns={"user_id"},
        max_select_rows=100,
    ),
    "budgets": TablePolicy(
        table_name="budgets",
        business_name="current user's monthly budget records",
        allowed_select=True,
        allowed_insert=False,
        user_scoped=True,
        user_id_column="user_id",
        selectable_columns={"id", "month", "year", "amount", "currency"},
        forbidden_columns={"user_id"},
        max_select_rows=24,
    ),
    "goals": TablePolicy(
        table_name="goals",
        business_name="current user's active savings goals",
        allowed_select=True,
        allowed_insert=False,
        user_scoped=True,
        user_id_column="user_id",
        selectable_columns={"id", "title", "target_amount", "current_amount", "deadline"},
        forbidden_columns={"user_id"},
        max_select_rows=50,
    ),
    "chat_messages": TablePolicy(
        table_name="chat_messages",
        business_name="limited current chat history",
        allowed_select=True,
        allowed_insert=False,
        user_scoped=True,
        user_id_column="user_id",
        selectable_columns={"id", "role", "content", "created_at"},
        forbidden_columns={"user_id"},
        max_select_rows=20,
        system_only=True,
    ),
    "users": TablePolicy(
        table_name="users",
        business_name="minimal current user profile",
        allowed_select=True,
        allowed_insert=False,
        user_scoped=True,
        user_id_column="id",
        selectable_columns={"id", "name", "first_name", "last_name", "language", "income_range", "monthly_income", "chat_mode"},
        forbidden_columns={
            "phone",
            "is_blocked",
            "created_at",
            "agreement_accepted_at",
            "agreement_version",
            "onboarding_completed",
            "onboarding_completed_at",
        },
        max_select_rows=1,
    ),
    "activity_logs": TablePolicy(
        table_name="activity_logs",
        business_name="system activity log",
        system_only=True,
    ),
    "agent_sql_audit_logs": TablePolicy(
        table_name="agent_sql_audit_logs",
        business_name="system audit log for agent database operations",
        system_only=True,
    ),
    "admin_users": TablePolicy(
        table_name="admin_users",
        business_name="admin authentication records",
        system_only=True,
    ),
}


FORBIDDEN_TABLES = {
    "admin_users",
    "activity_logs",
    "agent_sql_audit_logs",
    "token_wallets",
    "token_usage_logs",
    "token_purchases",
    "user_subscriptions",
}


def get_policy(table_name: str) -> TablePolicy | None:
    return POLICIES.get(table_name.lower())


def llm_visible_policies() -> list[TablePolicy]:
    return [
        policy
        for policy in POLICIES.values()
        if not policy.system_only and (policy.allowed_select or policy.allowed_insert)
    ]
