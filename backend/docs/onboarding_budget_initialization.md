# Onboarding Budget Initialization

When a user completes onboarding for the first time, BudgetMate initializes the current monthly budget from the maximum value of the selected income range.

Examples:

- `40to80` -> `80,000,000` toman
- `۴۰ تا ۸۰ میلیون` -> `80,000,000` toman
- `20to40` -> `40,000,000` toman
- `کمتر از ۱۰ میلیون` / `lt10` -> `10,000,000` toman
- `gt80` -> `80,000,000` toman, because the configured option has no higher bound

The implementation lives in:

- `app/services/income_range.py` for parsing and code-to-maximum mapping
- `app/services/onboarding_budget.py` for current-month budget creation/update
- `app/routers/onboarding.py` for calling the initializer from `POST /onboarding/complete`

The initializer is idempotent:

- On first onboarding completion, it creates the current Jalali month budget if none exists.
- If a current-month budget already exists before first completion, it updates that row instead of creating a duplicate.
- If onboarding was already completed, it does not overwrite the user's existing budget.

The rule is deliberately not based on average income. The highest number in the selected range is the initial monthly budget.
