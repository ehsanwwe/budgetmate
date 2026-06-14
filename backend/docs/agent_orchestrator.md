# Backend Agent Orchestrator

Phase 1 moves chat-side financial actions into a backend-native orchestration layer under
`app/services/agent_orchestrator`.

Flow:

1. `chat.py` saves the user message and calls `AgentOrchestrator`.
2. The orchestrator builds a compact finance context and a safe DB World.
3. The OpenAI planner asks for strict `AgentPlan` JSON and is responsible for intent detection.
5. Each proposed SQL step is validated by `SqlValidator`.
6. `SqlExecutor` executes only validated operations, scopes SELECTs to the authenticated user, injects `user_id` for transaction inserts, and writes audit rows.
7. `ResponseComposer` returns clean Persian text. SQL, JSON plans, step ids, unresolved placeholders, and audit details are not exposed.

Provider:

- Active chat/orchestrator planning uses OpenAI only.
- OpenAI authentication uses only `OPENAI_API_KEY`.
- `OPENAI_MODEL` selects the model and defaults to `gpt-4o-mini`.
- If `OPENAI_API_KEY` is missing, the planner fails closed with a safe Persian response.
- There is no fallback provider in the active chat/orchestrator path.
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

Backend deterministic responsibilities:

- The backend does not infer financial intent before the planner.
- Deterministic code is limited to SQL validation, user scoping, parameterized execution, auditing, and final formatting from executed DB rows.
- The response composer can combine multiple executed SELECT results, such as income and expense totals from the same user question.
- Values and category names come only from executed, user-scoped SELECT results.
- `APP_TIMEZONE` controls relative Persian dates and defaults to `Asia/Tehran`.
- Final response sanitization blocks unresolved placeholder tokens such as `[total_amount]`.

Audit log:

- `AgentSqlAuditLog` records allowed, rejected, and errored planned operations.
- The LLM cannot read or write this table directly.

Future phases should extend the planner prompts, context builder, and response composer for Personal CFO behavior without weakening `table_policy.py` or `sql_validator.py`.
