# Personal CFO Phase 2 Foundation

Phase 2 adds durable, user-scoped context for future Personal CFO behavior. It does not implement forecasting, warning systems, goal simulation, or decision analysis.

Tables:

- `financial_personas`: one active persona per user, including optional risk tolerance, debt sensitivity, anxiety level, discipline score, saving preference, and emotional spending triggers.
- `financial_memories`: active finance-relevant memories such as goals, preferences, constraints, income/expense patterns, behavioral triggers, and risk notes.
- `behavior_insights`: validated behavior insights such as stress spending, debt anxiety, liquidity pressure, and end-of-month overspending.
- `persona_update_logs`: backend audit trail for persona updates.

Services:

- `persona_service.py`: get/create persona, confidence-based persona updates, agent serialization.
- `memory_service.py`: create/search/deactivate user-scoped memories.
- `behavior_service.py`: deterministic validated signal detection and insight upsert.
- `profile_extractor.py`: optional LLM-based soft extraction that fails closed and never writes directly.
- `cfo_context_builder.py`: compact persona, memory, and behavior context for the agent.

Endpoints:

- `GET /api/v1/personal-cfo/persona`
- `PATCH /api/v1/personal-cfo/persona`
- `GET /api/v1/personal-cfo/memories`
- `POST /api/v1/personal-cfo/memories`
- `DELETE /api/v1/personal-cfo/memories/{memory_id}`
- `GET /api/v1/personal-cfo/behavior-insights`

Privacy rules:

- All rows are scoped to the authenticated user.
- The LLM cannot directly write persona, memory, or insight rows.
- The DB World does not expose these tables to the planner.
- Only finance-relevant signals are stored; unrelated sensitive details and secrets are ignored.

Manual checks:

- `من آخر ماه همیشه پول کم میارم` creates a liquidity/end-of-month insight or memory and returns a concise Persian response.
- `وقتی استرس دارم خرید میکنم` creates a `stress_spending` insight and behavioral trigger memory.
- `من از بدهی خیلی میترسم` updates debt sensitivity and creates a `debt_anxiety` insight.
