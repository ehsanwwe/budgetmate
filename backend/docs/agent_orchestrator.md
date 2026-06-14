# Backend Agent Orchestrator

Phase 1 moves chat-side financial actions into a backend-native orchestration layer under
`app/services/agent_orchestrator`.

Flow:

1. `chat.py` saves the user message and calls `AgentOrchestrator`.
2. The orchestrator builds a compact finance context and a safe DB World.
3. The planner asks the configured AI provider for strict `AgentPlan` JSON only.
4. Each proposed SQL step is validated by `SqlValidator`.
5. `SqlExecutor` executes only validated operations, scopes SELECTs to the authenticated user, injects `user_id` for transaction inserts, and writes audit rows.
6. `ResponseComposer` returns clean Persian text. SQL, JSON plans, step ids, and audit details are not exposed.

DB World:

- Built from actual SQLAlchemy metadata.
- Filtered through `table_policy.py`.
- Exposes only allowed tables and safe columns.
- Tells the model to SELECT real categories before choosing a `category_id`.

Table policy:

- `categories`: SELECT only.
- `transactions`: SELECT and INSERT; always backend-scoped to current user.
- `budgets` and `goals`: SELECT only in Phase 1.
- `users`: minimal current-user profile SELECT only.
- admin/auth/billing/activity/audit tables are hidden or system-only.

SQL validator:

- Fails closed.
- Rejects multiple statements, comments, destructive/admin SQL, forbidden tables, forbidden columns, unsafe inserts, and LLM-provided `user_id`.
- Allows only conservative parameterized SELECT and INSERT proposals.

Audit log:

- `AgentSqlAuditLog` records allowed, rejected, and errored planned operations.
- The LLM cannot read or write this table directly.

Future phases should extend the planner prompts, context builder, and response composer for Personal CFO behavior without weakening `table_policy.py` or `sql_validator.py`.
