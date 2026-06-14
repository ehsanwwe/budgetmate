# Personal CFO Phase 5.5

This phase completes the data/context foundation needed before the full Personal CFO protocol.

## Data Foundation

Already present tables:

- `financial_personas`
- `financial_memories`
- `behavior_insights`
- `financial_facts`
- `financial_warnings`
- `financial_decision_logs`
- `goals`
- `future_commitments`

No new database migration was required in Phase 5.5 because migrations 007-009 already provide the required tables and goal/future-commitment fields.

## Context Integration

`build_agent_context()` now includes a richer `personal_cfo` payload:

- active goals
- pending future commitments
- next-month commitments
- commitments until next year
- financial memories
- financial facts
- behavior insights
- persona summary
- active warnings
- current-month budget summary

The selected LLM planner remains responsible for intent detection. Backend deterministic logic is still limited to validation, execution, scoping, auditing, date/amount normalization, and response sanitization.

## Goal And Future Questions

The planner prompt and DB World now explicitly instruct OpenAI to answer future-plan and goal questions by selecting:

- `goals`
- `future_commitments`
- `financial_facts`
- `financial_memories`

Normal Personal CFO questions should not fall back to the generic safe-failure message. If data is missing, the model should answer that no registered plan exists or ask a specific clarification.

## Planned Purchase Follow-Ups

Future purchase wording should create a planned obligation, not a current transaction. If the amount is missing, the planner asks for it. A later amount-only reply should use chat history to create a `future_commitments` row for the pending planned purchase.

## Frontend

- Added `/future-commitments`.
- Added sidebar/mobile navigation item: `تعهدات آینده`.
- The page lists commitments with filters for pending, paid, cancelled, next month, and until next year.
- Chat message alignment was fixed for Persian RTL UI: user messages align right; assistant messages align left; text remains RTL.

## Manual Checklist

- `تو سال آینده چه برنامه هایی دارم`
- `اهداف آینده من چیست`
- `چه اهدافی دارم`
- `در ماه آینده چه هزینه هایی دارم`
- `تا سال آینده هزینه ای دارم`
- planned purchase, then amount-only follow-up
- pen expense plus incomplete friend transfer
- Personal CFO follow-up such as `پس اوضاع خیلی خرابه`
- going-out decision advice
- frontend `تعهدات آینده` page and chat bubble alignment
