# Chat Session Lifecycle

## Clear Chat Contract

`DELETE /api/v1/chat/history` clears user-visible chat history and cancels transient conversational state for the authenticated user.

Response:

```json
{
  "cleared_messages": 2,
  "cancelled_pending_intents": 1,
  "cancelled_advisory_sessions": 1
}
```

## Transient State Cleared

- `pending_agent_intents.status = "pending"`
- Goal intake states such as `collecting_amount`, `collecting_target_date`, and `awaiting_user_choice`
- Advisory mode represented by `pending_agent_intents.payload_json.state = "consultation_active"`
- Amount/date/choice clarifications stored inside pending intent payloads
- Any unconsumed pending intent that depends on old chat context

Cancelled rows are marked:

- `status = "cancelled"`
- `payload_json.state = "cancelled"`
- `payload_json.cancelled_reason = "chat_history_cleared"`
- `consumed_at` and `updated_at` set to the cancellation time

## Durable State Preserved

Normal chat clear does not delete:

- transactions
- goals
- future commitments
- budgets
- categories
- financial memories
- financial facts
- behavior insights
- financial personas
- financial warnings
- financial decision logs
- agent operation events
- SQL audit logs

Financial memories and facts are durable user context. They require an explicit memory/data deletion feature, not normal chat clear.

## New Conversation Boundary

After clear, the next user message should behave as a fresh chat turn:

- Chat history loaded for the planner is empty.
- Cancelled pending intents are ignored because gates load only `status = "pending"`.
- Durable goals and memories may still inform answers when relevant.
- A simple transaction message should register the transaction and avoid unrelated goal/advisory plans.
- Goal-specific advice should appear only when the current message asks about goals/advice or a new active advisory session is created.

## Relevance Guard

Simple expense/income registration should not trigger long advisory responses or unrelated goal-specific savings plans. Near-deadline goals may be mentioned only when the current turn asks for advice, explicitly asks about goals, or a new active advisory session exists.

## Manual Test Checklist

1. Start a goal/advisory flow:
   `میخوام اسپیکر سیم‌دار بخرم به مبلغ ۱۷ میلیون تا دو هفته دیگه`
2. Choose consultation if prompted.
3. Clear chat history from the UI.
4. Send:
   `۳۰۰ هزار پول به تاکسی دادم امروز`
5. Expected: taxi expense is registered; no speaker advisory text and no stale follow-up question.
6. Send:
   `لیست اهداف من و بده`
7. Expected: durable saved goals still appear; an unsaved speaker intake does not appear as a goal.
8. Send:
   `۱۰۰ میلیون`
9. Expected: it does not complete the old pending intent; the assistant asks what the amount is for unless a new pending intent exists.
