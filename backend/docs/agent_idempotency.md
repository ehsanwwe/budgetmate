# Agent Idempotency & Write-Safety (Phase 5.7)

## Problem

Before Phase 5.7, the agent orchestrator had four interrelated bugs:

| Bug | Symptom |
|-----|---------|
| History replay | Old chat turns triggered new INSERT/UPDATE operations (e.g. "ماشین لباسشویی" inserted every time the user re-opened chat) |
| Response leakage | Confirmation sentences from prior turns ("موعد خرید لپتاپ به یک ماه بعد منتقل شد") reappeared in unrelated answers |
| Goal vs commitment misclassification | "میخام بخرم" (goal intent) stored as `future_commitments` instead of `goals` |
| Goal deadline not persisting | LLM confirmed update but DB remained unchanged |

---

## Solutions

### 1. Current-Turn Execution Guard (`source_scope`)

`AgentPlanStep` now carries a `source_scope` field:

```python
class SourceScope(str, Enum):
    current_message  = "current_message"   # safe to write
    pending_intent   = "pending_intent"    # safe to write (future use)
    history_context  = "history_context"   # SELECT only — writes BLOCKED
```

The orchestrator rejects any `INSERT`/`UPDATE` step where `source_scope == history_context` before it reaches the SQL executor. This is a hard enforcement layer independent of the LLM prompt.

### 2. History passed as a labeled system block

The planner now passes prior conversation history as a single `role: system` message:

```
CONVERSATION HISTORY — FOR CONTEXT ONLY.
Do NOT create INSERT or UPDATE operations from this history.
Use it only to resolve references in the CURRENT message below.

[USER]: ...
[ASSISTANT]: ...
```

The current user message is then sent as a separate `role: user` message labeled:

```
CURRENT USER MESSAGE (only this message may trigger new INSERT/UPDATE operations):
...
```

This prevents the LLM from confusing history turns with the active request.

### 3. Idempotency — two-layer deduplication

**Layer 1 — Per-turn fingerprint set** (`seen_fingerprints: set[str]`)  
Prevents the same logical write from executing twice within a single orchestrator run (e.g. two planner iterations both trying to insert the same goal).

**Layer 2 — Cross-turn `agent_operation_events` table**  
Every successful `INSERT`/`UPDATE` records a SHA-256 fingerprint in `agent_operation_events`. Before executing a write, the executor checks for a matching fingerprint within the last 60 minutes. Duplicates are skipped and logged.

**Fingerprint computation:**
- Keyed on `(user_id, operation_type, table_name, key_params)`
- Excludes ephemeral fields: `description`, `notes_json`, `metadata_json`, `source`, `content_json`, `evidence_json`, `confidence`
- Normalizes amounts (so "47 ملیون" and `47000000` produce the same hash)
- Normalizes strings to lowercase

### 4. Response leakage prevention

`_strip_leaked_operations()` in `response_composer.py` strips trailing operation-confirmation sentences from SELECT-only hints using this regex:

```
[.،\s]+[^.،]{0,80}(?:منتقل شد|آپدیت شد|به‌روزرسانی شد|تغییر کرد|ثبت شد|ذخیره شد|اضافه شد)[^.،]{0,60}$
```

This runs only on SELECT-only turns (no writes executed in the current turn).

### 5. Update verification

Before composing a success response for UPDATE operations, the composer re-reads the updated row from the DB to confirm the write actually persisted. If the row is missing, an explicit failure message is returned instead of a false confirmation.

### 6. Semantic classification in planner prompt

The planner system prompt includes an explicit semantic classification section:

- **TRANSACTION**: already-completed payment (`خریدم`, `دادم`, `پرداخت کردم`) → `INSERT INTO transactions`
- **FUTURE COMMITMENT**: known upcoming obligation (`چک دارم`, `باید بدم`, `اجاره ماه بعد`) → `INSERT INTO future_commitments`
- **GOAL**: desired future purchase/saving (`میخام بخرم`, `دارم جمع میکنم`, `هدفم اینه`) → `INSERT INTO goals`

---

## Database Tables

### `agent_operation_events`
Audit log of all successful agent write operations, used for cross-turn deduplication.

| Column | Type | Notes |
|--------|------|-------|
| `id` | int PK | |
| `user_id` | int FK → users | |
| `operation_fingerprint` | varchar(64) | SHA-256 prefix |
| `operation_type` | varchar(20) | `insert` / `update` |
| `table_name` | varchar(80) | |
| `target_record_id` | int nullable | inserted/updated row id |
| `status` | varchar(30) | `executed` / `skipped_duplicate` |
| `payload_json` | json | key params for audit |
| `created_at` | datetime | |

Indexed on `(user_id, operation_fingerprint)` for fast dedup lookups.

### `pending_agent_intents` (foundation table)
Stores multi-turn intents that require user confirmation before execution. Not yet wired to the orchestrator — reserved for Phase 5.8+.

---

## Cleanup Script

If duplicate `future_commitments` were created before this fix, run:

```bash
cd backend
python scripts/cleanup_duplicate_commitments.py          # dry-run (shows what would be deleted)
python scripts/cleanup_duplicate_commitments.py --execute  # actually deletes
python scripts/cleanup_duplicate_commitments.py --user-id 42 --execute  # single user
```

The script keeps the oldest row (lowest `id`) per `(user_id, title, amount)` group.

---

## Testing

Phase 5.7 tests live in `backend/tests/test_agent_phase57.py` (24 tests covering all guarantees above).

## Chat Clear Lifecycle

`pending_agent_intents` now has an active lifecycle in the goal-intake gate:

- `pending`: active transient conversation state.
- `consumed`: completed by a successful user choice, such as inserting the goal.
- `cancelled`: deactivated by chat-history clear or replacement with a newer active intent.

`DELETE /chat/history` cancels all pending rows for that user. This prevents amount-only follow-ups or consultation prompts from completing stale state after the user has cleared the chat. It does not delete durable finance records, memories, facts, persona, warnings, or audit logs.

Chat-session lifecycle tests live in `backend/tests/test_chat_session_lifecycle.py` and cover pending-intent cancellation, advisory cancellation, durable-data preservation, cancelled-intent ignore behavior, and the clear-history endpoint response.
