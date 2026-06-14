# Backend Agent Orchestrator

Phase 3 keeps chat-side financial actions inside a backend-native orchestration layer under
`app/services/agent_orchestrator`.

Flow:

1. `chat.py` saves the user message and calls `AgentOrchestrator`.
2. The orchestrator builds a compact finance context and a safe DB World.
3. The selected LLM planner asks for strict `AgentPlan` JSON and is responsible for all financial intent detection.
4. The orchestrator executes validated steps and sends execution results back to the selected provider for multi-step planning.
5. Each proposed SQL step is validated by `SqlValidator`.
6. `SqlExecutor` executes only validated operations, scopes SELECTs to the authenticated user, injects `user_id` for inserts, and writes audit rows.
7. `ResponseComposer` returns clean Persian text. SQL, JSON plans, step ids, unresolved placeholders, and audit details are not exposed.

Provider:

- Active chat/orchestrator planning uses `AI_PROVIDER=openai` or `AI_PROVIDER=ollama`.
- OpenAI authentication uses only `OPENAI_API_KEY`; `OPENAI_KEY` is not supported.
- `OPENAI_MODEL` selects the OpenAI model and defaults to `gpt-4o-mini` when unset.
- Ollama uses `OLLAMA_BASE_URL`, defaulting to `http://localhost:11434`.
- Ollama uses `OLLAMA_MODEL`, defaulting to `gpt-oss:20b`.
- If `AI_PROVIDER` is missing and `OPENAI_API_KEY` exists, OpenAI is used.
- If `AI_PROVIDER` is missing and `OPENAI_API_KEY` is missing, Ollama is used with `gpt-oss:20b`.
- If `AI_PROVIDER=openai`, missing `OPENAI_API_KEY` is a configuration error and the planner fails closed with a safe Persian response.
- There is no OpenClaw fallback in the active chat/orchestrator path.
- Startup logging reports only provider and model names, never secrets.

OpenAI mode:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
```

Ollama mode:

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gpt-oss:20b
```

DB World:

- Built from actual SQLAlchemy metadata.
- Filtered through `table_policy.py`.
- Exposes only allowed tables and safe columns.
- Tells the model to SELECT real categories before choosing a `category_id`.
- Includes goals, future commitments, and safe Personal CFO tables when they exist: persona, memories, behavior insights, facts, warnings, and decision logs.

Table policy:

- `categories`: SELECT only.
- `transactions`: SELECT and INSERT; always backend-scoped to current user.
- `budgets`: SELECT only.
- `goals`: SELECT, INSERT, and safe UPDATE for title, target/current amount, deadline, status/archive fields, and notes. Goal DELETE requests are represented as archive updates, not raw DELETE.
- `future_commitments`: SELECT, INSERT, and safe UPDATE for pending obligations, due dates/months, amount, status, and relationship fields.
- `users`: minimal current-user profile SELECT only.
- `financial_memories`, `behavior_insights`, `financial_facts`, `financial_warnings`, `financial_decision_logs`: safe user-scoped SELECT/INSERT where policy allows it.
- `financial_personas`: user-scoped SELECT only.
- admin/auth/billing/activity/audit tables are hidden or system-only.

SQL validator:

- Fails closed.
- Rejects multiple statements, comments, destructive/admin SQL, forbidden tables, forbidden columns, unsafe inserts, and LLM-provided `user_id`.
- Allows conservative parameterized SELECT, INSERT, and explicitly policy-approved UPDATE proposals.
- Allows grouped aggregate SELECTs and joins only when every referenced table and column is allowed.
- UPDATE is only enabled for tables and columns explicitly listed in `table_policy.py`. Raw DELETE remains blocked.

Backend deterministic responsibilities:

- The backend does not infer financial intent before the planner.
- There is no active deterministic transaction planner, category keyword map, or old action-spec execution path in chat.
- Deterministic code is limited to SQL validation, user scoping, parameterized execution, auditing, and final formatting from executed DB rows.
- Persian amount/date normalization is a value-cleanup helper after the LLM has extracted values; it is not an intent planner.
- The response composer can combine multiple executed SELECT results, such as income and expense totals from the same user question.
- Values and category names come only from executed, user-scoped SELECT results.
- Decision advice must be planner-driven and grounded in executed reads of budget, current spending/income, goals, future commitments, and relevant CFO context.
- Emotional-spending requests should not encourage spending; the planner should query context, propose behavior insight storage when appropriate, and ask for clarification only when required data is missing.
- `APP_TIMEZONE` controls relative Persian dates and defaults to `Asia/Tehran`.
- Final response sanitization blocks unresolved placeholder tokens such as `[total_amount]`.

Audit log:

- `AgentSqlAuditLog` records allowed, rejected, and errored planned operations.
- The LLM cannot read or write this table directly.

Future phases should extend the planner prompts, context builder, and response composer for Personal CFO behavior without weakening `table_policy.py` or `sql_validator.py`.

Goal-aware decision phase:

- The selected LLM planner remains responsible for deciding whether a message is a goal operation, future commitment, purchase decision, emotional-spending request, or transaction event.
- The backend does not use keyword shortcuts for goal/gift/tour/laptop/home-party examples.
- Goal updates must SELECT current goals first and choose a real goal id from returned rows. Low-confidence or multiple matches should produce a specific clarification.
- Goal deletion/archiving uses `UPDATE goals SET status='archived', is_active=false WHERE id=:id`.
- Future obligations such as an unpaid later installment are stored in `future_commitments` with `status='pending'` and included in future budget analysis.
- High-value purchase responses should mention budget/goal/commitment tradeoffs and must not blindly approve the purchase.

Phase 5.5 context completion:

- The compact CFO context now includes active goals, future commitments, next-month commitments, commitments until next year, financial facts, memories, behavior insights, persona, warnings, and a current-month budget summary.
- Direct questions such as "what goals do I have?", "what plans do I have next year?", and "what costs do I have next month?" should be answered through planner-proposed SELECTs over goals, `future_commitments`, `financial_facts`, and `financial_memories`.
- Planned future purchases are not current transactions. The planner should ask for an amount if missing and use chat history to connect a follow-up amount to the pending planned purchase.
- Mixed events should only execute complete operations. For example, a bought pen can be recorded while an incomplete friend transfer remains a specific clarification.
- `financial_personas`, `financial_memories`, `behavior_insights`, `financial_facts`, and `financial_warnings` have limited user-scoped UPDATE policies only for safe status/profile fields.
- The frontend exposes `/future-commitments` and the chat UI aligns user messages to the right and assistant messages to the left while preserving RTL text direction.

Phase 5.6 goal chat recovery:

- Normal goal and Personal CFO advice questions should not fall into the generic safe-failure response.
- If the planner mistakenly includes `user_id` in a SELECT/WHERE/params for a user-scoped table, the operation is rejected and audited, but the orchestrator treats it as repairable and asks the planner for a corrected backend-scoped query. Destructive/admin SQL still fails immediately.
- User scope is inserted before `GROUP BY`, `HAVING`, `ORDER BY`, or `LIMIT`, so grouped spending/category queries stay valid after backend scoping.
- Goal SELECT results have a safe formatter fallback that lists active goals with target amount, current amount, remaining amount, progress, and deadline when OpenAI returns a placeholder or generic failure hint after successful reads.
- Goal UPDATE results have a safe formatter fallback that confirms the updated goal from the actual row.
- Goal fuzzy matching is available only as a helper over real selected/stored goal titles. It normalizes Persian/Arabic characters, half-spaces, whitespace, and common laptop variants such as `لپتاپ`, `لپ تاب`, `لپ‌تاپ`, `لپتاب`, `لپباپ`, and `laptop`. It does not decide intent or bypass the selected LLM planner.

Manual Phase 3 checks:

- `هفته پیش یک پروژه زدم که پولش سه روز پیش اومد چهارده میلیون تومان بود`
- `چهل هزار تومن صبح پول اتوبوس دادم`
- `این ماه چقدر خرج کردم چقدر در آوردم`
- `بیشترین خرج تو ماه گذشته مربوط به چی بوده`
- `DROP TABLE users;`
