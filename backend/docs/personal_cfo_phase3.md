# Personal CFO Phase 3 Foundation

Phase 3 adds the missing durable data foundation for future Personal CFO behavior without implementing forecasting, simulations, or advanced warning engines.

## Tables

- `financial_personas`: one user-scoped persona summary per user.
- `financial_memories`: durable user-scoped financial memories.
- `behavior_insights`: user-scoped behavior signals.
- `financial_facts`: structured facts extracted from finance conversations.
- `financial_warnings`: foundation table for future warnings.
- `financial_decision_logs`: foundation table for important financial decisions.

The existing `goals` table remains the app-level goal table. Phase 3 does not duplicate it with another life-goal table.

## Agent Access

The selected LLM planner can see only the safe DB World generated from table policy. It may propose inserts into allowed memory/fact/insight/warning/decision tables, but the backend validates allowed columns, injects the authenticated `user_id`, and stores only backend-approved fields.

The planner must not store secrets, unrelated sensitive personal details, auth data, or admin data.

## Transparency Endpoints

All endpoints are authenticated and user-scoped:

- `GET /api/v1/personal-cfo/persona`
- `GET /api/v1/personal-cfo/memories`
- `GET /api/v1/personal-cfo/behavior-insights`
- `GET /api/v1/personal-cfo/facts`
- `GET /api/v1/personal-cfo/warnings`
- `GET /api/v1/personal-cfo/decision-logs`

## Migration

Migration `008_add_personal_cfo_phase3_tables` adds `financial_facts`, `financial_warnings`, and `financial_decision_logs`.
