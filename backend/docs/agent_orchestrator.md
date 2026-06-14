# Backend Agent Orchestrator

Phase 1 moves chat-side financial actions into a backend-native orchestration layer under
`app/services/agent_orchestrator`.

Flow:

1. `chat.py` saves the user message and calls `AgentOrchestrator`.
2. The orchestrator builds a compact finance context and a safe DB World.
3. Deterministic handlers answer common aggregate questions directly from the database when possible.
4. The planner asks the configured AI provider for strict `AgentPlan` JSON only when model planning is needed.
5. Each proposed SQL step is validated by `SqlValidator`.
6. `SqlExecutor` executes only validated operations, scopes SELECTs to the authenticated user, injects `user_id` for transaction inserts, and writes audit rows.
7. `ResponseComposer` returns clean Persian text. SQL, JSON plans, step ids, unresolved placeholders, and audit details are not exposed.

Provider selection:

- OpenAI authentication uses only `OPENAI_API_KEY`.
- If `AI_PROVIDER=openai`, `OPENAI_API_KEY` is required.
- If `AI_PROVIDER` is empty and `OPENAI_API_KEY` exists, OpenAI is selected automatically.
- `OPENAI_MODEL` is used when present; otherwise the first configured `openai/*` model in the existing model waterfall is used.
- `AI_PROVIDER=openclaw` keeps OpenClaw as an explicit fallback/alternative.
- Startup logging reports only provider and model names, never secrets.

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

Deterministic aggregate composer:

- Handles current/previous week and current/previous month totals for income and expense.
- Handles top expense category for current/previous month.
- Values and category names come only from executed, user-scoped SELECT results.
- `APP_TIMEZONE` controls relative Persian dates and defaults to `Asia/Tehran`.
- Final response sanitization blocks unresolved placeholder tokens such as `[total_amount]`.

Audit log:

- `AgentSqlAuditLog` records allowed, rejected, and errored planned operations.
- The LLM cannot read or write this table directly.

Future phases should extend the planner prompts, context builder, and response composer for Personal CFO behavior without weakening `table_policy.py` or `sql_validator.py`.
