# Backend Agent Orchestrator

Phase 3 keeps chat-side financial actions inside a backend-native orchestration layer under
`app/services/agent_orchestrator`.

Flow:

1. `chat.py` saves the user message and calls `AgentOrchestrator`.
2. The orchestrator builds a compact finance context and a safe DB World.
3. The OpenAI planner asks for strict `AgentPlan` JSON and is responsible for all financial intent detection.
4. The orchestrator executes validated steps and sends execution results back to OpenAI for multi-step planning.
5. Each proposed SQL step is validated by `SqlValidator`.
6. `SqlExecutor` executes only validated operations, scopes SELECTs to the authenticated user, injects `user_id` for inserts, and writes audit rows.
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
- Includes safe Personal CFO tables when they exist: persona, memories, behavior insights, facts, warnings, and decision logs.

Table policy:

- `categories`: SELECT only.
- `transactions`: SELECT and INSERT; always backend-scoped to current user.
- `budgets` and `goals`: SELECT only.
- `users`: minimal current-user profile SELECT only.
- `financial_memories`, `behavior_insights`, `financial_facts`, `financial_warnings`, `financial_decision_logs`: safe user-scoped SELECT/INSERT where policy allows it.
- `financial_personas`: user-scoped SELECT only.
- admin/auth/billing/activity/audit tables are hidden or system-only.

SQL validator:

- Fails closed.
- Rejects multiple statements, comments, destructive/admin SQL, forbidden tables, forbidden columns, unsafe inserts, and LLM-provided `user_id`.
- Allows conservative parameterized SELECT and INSERT proposals on policy-approved tables.
- Allows grouped aggregate SELECTs and joins only when every referenced table and column is allowed.
- UPDATE remains disabled in this phase unless a table policy explicitly enables it later.

Backend deterministic responsibilities:

- The backend does not infer financial intent before the planner.
- There is no active deterministic transaction planner, category keyword map, or old action-spec execution path in chat.
- Deterministic code is limited to SQL validation, user scoping, parameterized execution, auditing, and final formatting from executed DB rows.
- Persian amount/date normalization is a value-cleanup helper after the LLM has extracted values; it is not an intent planner.
- The response composer can combine multiple executed SELECT results, such as income and expense totals from the same user question.
- Values and category names come only from executed, user-scoped SELECT results.
- `APP_TIMEZONE` controls relative Persian dates and defaults to `Asia/Tehran`.
- Final response sanitization blocks unresolved placeholder tokens such as `[total_amount]`.

Audit log:

- `AgentSqlAuditLog` records allowed, rejected, and errored planned operations.
- The LLM cannot read or write this table directly.

Future phases should extend the planner prompts, context builder, and response composer for Personal CFO behavior without weakening `table_policy.py` or `sql_validator.py`.

Manual Phase 3 checks:

- `هفته پیش یک پروژه زدم که پولش سه روز پیش اومد چهارده میلیون تومان بود`
- `چهل هزار تومن صبح پول اتوبوس دادم`
- `این ماه چقدر خرج کردم چقدر در آوردم`
- `بیشترین خرج تو ماه گذشته مربوط به چی بوده`
- `DROP TABLE users;`
