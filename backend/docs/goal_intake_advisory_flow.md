# Goal Intake Decision Gate + Financial Advisory Flow

## Overview

Phase 5.8 adds a **Goal Intake Decision Gate** that intercepts goal-like chat messages before
they reach the main orchestrator. Instead of immediately inserting a goal, the backend:

1. Collects missing information (amount, target date) via multi-turn conversation.
2. Presents the user with a binary decision: **add as goal** or **receive financial consultation**.
3. Only inserts a goal after the user explicitly chooses "add".
4. If the user chooses consultation, enters a multi-turn advisory conversation (Personal CFO mode).

---

## State Machine

The `GoalIntakeGate` manages a `PendingAgentIntent` record with `intent_type="goal_intake_pending"`.

```
[new goal-like message]
        │
        ▼
  item detected
        │
   amount present? ──── NO ───→ collecting_amount
        │                            │ (user gives amount)
       YES                           ▼
        │                       collecting_target_date
   date present? ──── NO ──────────────┤ (or also skip if date collected)
        │                            │ (user gives date)
       YES                           ▼
        └──────────────────→ awaiting_user_choice
                                     │
                    ┌────────────────┴──────────────────┐
                   "add"                              "consult"
                    │                                    │
                    ▼                                    ▼
              [INSERT goal]                    consultation_active
              [consumed]                              │
                                        (multi-turn advisory)
                                                     │
                                              "ثبتش کن" / "اضافه کن"
                                                     │
                                                     ▼
                                              [INSERT goal]
                                              [consumed]
```

### States

| State | Description |
|---|---|
| `collecting_amount` | Waiting for user to provide target amount |
| `collecting_target_date` | Waiting for user to provide target date |
| `awaiting_user_choice` | All info collected — asking add vs consult |
| `consultation_active` | Advisory conversation ongoing |
| `consumed` | Goal inserted or user cancelled |
| `cancelled` | Replaced by a newer intent or unrelated message |

---

## Goal vs Commitment vs Transaction

| User wording | Classification | Backend action |
|---|---|---|
| میخوام بخرم / قصد دارم / میخوام پس‌انداز کنم | **Goal-like desire** | Gate intercepts → state machine |
| یک هدف اضافه کن + مبلغ + تاریخ | **Explicit goal add** | Gate passes through → orchestrator inserts directly |
| چک دارم / قسط دارم / باید کرایه بدهم | **Future commitment** | Gate passes through → orchestrator inserts future_commitment |
| خریدم / دادم / پرداخت کردم | **Transaction** | Gate passes through → orchestrator inserts transaction |

---

## Decision Gate

When all three fields (item, amount, date) are collected, the gate asks:

> "اطلاعات کامل شد: {item}، {amount}، {date}. می‌خواهی این را به اهداف مالی‌ات اضافه کنم یا اول درباره منطقی بودنش مشاوره بگیری؟"

### Add choice keywords

`اضافه کن`, `ثبت کن`, `بزن تو اهداف`, `هدفش کن`, `ثبتش کن`, `بله`, `آره`, `ok`

### Consult choice keywords

`مشاوره`, `بررسی کن`, `به نظرت`, `منطقیه`, `می‌صرفه`, `راهنمایی`, `نه اول`, `صبر کن`

For ambiguous responses, the gate asks: "می‌خواهی ثبتش کنم یا اول مشاوره بگیری؟"

---

## Financial Advisory Mode

When user chooses consultation, the backend:

1. Switches intent state to `consultation_active`.
2. Builds financial context: budget, spending, income, active goals, upcoming commitments.
3. Calculates required monthly savings = target_amount / months_remaining.
4. Calls LLM with `_ADVISORY_SYSTEM` prompt (Personal CFO persona).
5. Returns a short, human, empathic advisory response with one follow-up question.
6. Continues advisory for subsequent turns until user explicitly says "add".

Advisory roles:
- Personal CFO (مدیر مالی شخصی)
- Financial Psychology Agent (روانشناس مالی)
- Life Financial Planner (برنامه‌ریز مالی بلندمدت)
- Financial Decision Assistant (دستیار تصمیم مالی)

---

## Idempotency

- Pending intent is **user-scoped** — user 1's intent never visible to user 2.
- Goal insert checks for existing active goal with same normalized title + amount before inserting.
- On duplicate: returns "قبلاً ثبت شده بود" message.
- Starting a new goal-like message **cancels** any existing pending intent.
- After `consumed` status, intent is never replayed.

---

## Pending Intent Lifecycle

```
CREATE (status=pending)
  → UPDATES (state transitions, missing field collection)
  → CONSUME (status=consumed) after goal insert or user cancellation
```

The `payload_json` contains:

```json
{
  "item_title": "انگشتر طلا",
  "normalized_title": "انگشتر طلا",
  "target_amount": 100000000,
  "target_date_text": "آخر سال",
  "source_message": "...",
  "state": "awaiting_user_choice"
}
```

---

## Planner Interaction

The planner is NOT called for non-explicit goal-like messages — the gate handles them.

The planner IS called:
- For all non-goal-like messages (commitments, transactions, questions, advice)
- For **explicit** goal add: "یک هدف اضافه کن + details" — gate returns `None`, planner runs

DB World instructs the planner:
- Do not INSERT goals from desire-wording messages ("میخوام بخرم")
- INSERT goals only when user explicitly says "یک هدف اضافه کن" with complete details

---

## Security

- Gate only reads/writes `pending_agent_intents` table (system-only, not planner-visible).
- Goal insert in the gate uses same validation as orchestrator executor.
- LLM classification output is treated as structured hint, not trusted SQL.
- All state transitions enforced in Python, not in the LLM response.

---

## Manual Test Checklist

```
1. میخوام انگشتر طلا بخرم
   → asks amount, no goal inserted

2. حدود ۱۰۰ میلیون
   → asks target date, no goal inserted

3. تا آخر سال
   → asks add or consult, no goal inserted

4. مشاوره بده
   → no goal inserted, advisory response, asks follow-up

5. حالا ثبتش کن
   → one goal inserted, visible in goals, intent consumed

6. (repeat) حالا ثبتش کن
   → no duplicate, "already exists" message

7. یک هدف جدید اضافه کن برای خرید ساعت طلا ۸۰ میلیون آخر سال
   → direct insert (explicit add), exactly one goal

8. میخوام ماشین لباسشویی بخرم ۴۷ میلیون آخر خرداد
   → asks add or consult (not future commitment)

9. چک دارم ماه بعد ۵۰ میلیون
   → future commitment (not goal)

10. دیروز ۴۰۰ هزار تومان خرید کردم
    → transaction
```
