# Goal-Aware Financial Decision Orchestration

This phase extends the OpenAI-first database agent with goals, future commitments, and decision-aware spending advice.

## Active Planner Contract

- OpenAI remains the first planner for finance chat messages.
- The backend does not use keyword shortcuts for goals, gifts, tours, emotional spending, or purchase feasibility.
- The planner receives the safe DB World, compact finance context, active goals, future commitments, memories, behavior insights, facts, and warnings.
- The backend validates, scopes, executes, audits, and sanitizes every proposed operation.

## Goals

The existing `goals` table remains the app goal source of truth. It now includes:

- `status`
- `is_active`
- `notes_json`
- `created_at`
- `updated_at`

Allowed agent operations:

- `SELECT` safe goal fields.
- `INSERT` a goal only when `title` and positive `target_amount` are available.
- `UPDATE` safe fields: `title`, `target_amount`, `current_amount`, `deadline`, `status`, `is_active`, `notes_json`.

Goal delete/archive behavior:

- Raw SQL `DELETE` is blocked.
- The planner should SELECT goals first and archive the matched goal with `status='archived'` and `is_active=false`.
- If matching is ambiguous, the planner should ask a specific clarification.

## Future Commitments

New table: `future_commitments`.

Purpose: future payments and obligations mentioned in chat, such as the unpaid next-month part of a tour purchase.

Core fields:

- `title`
- `amount`
- `due_date`
- `due_month`
- `category_id`
- `related_transaction_id`
- `related_goal_id`
- `description`
- `status`
- `source`
- `metadata_json`

Allowed agent operations:

- `SELECT` pending commitments for analysis.
- `INSERT` future obligations from chat.
- `UPDATE` safe fields, including `status` for paid/cancelled changes.

All operations are user-scoped and the backend injects `user_id`.

## Decision Advice

For spending questions like party budgets, emotional spending, gifts, tours, or “do I have room”, the planner should query:

- monthly budget
- current spending and income
- active goals
- future commitments
- relevant Personal CFO context

The final answer should give a practical cap/range or tradeoff analysis grounded in executed DB results. It should not approve high spending without checking context.

## Emotional Spending

For sadness, stress, or mood-driven spending:

- Do not encourage overspending.
- Suggest a small grounded cap or cooling-off rule.
- Store a finance-relevant behavior insight when appropriate.
- Keep language non-judgmental and avoid therapy claims.

## Manual Checklist

- `امروز افسرده ام میخام هزینه کنم افسردگیم بره به نظرت چقدر بودجه خرج کنم`
- `برای مهمانی که جمعه دعوت هستم چقدر بودجه میتونم خرج کنم`
- `یک کادو برای مهمونی امشب خریدم ۲۵ ملیون به نظرت کمه طرف دوست صمیمیم هست`
- `یک تور خریدم که نصفش و این ماه دادم ۳۰ ملیون تومان ما بقی در ماه بعدی پرداخت میشه ۵۰ ملیون تومان`
- `یک خانه میخام بخرم به قیمت ۱۲ ملیارد تومان`
- `این ماه میتونم به خرید لپتاپ برسم`
- `هدف خرید لپتاپ را به یک سال بعد تغییر بده`
- `یک هدف جدید اضافه بکن برای خرید ماشین شاسی بلند تا اواسط پاییز`
- `سه روز پیش من یک آب معدنی خریدم هجده هزار تومان`
- `DROP TABLE users;`
