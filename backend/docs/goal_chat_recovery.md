# Phase 5.6 Goal Chat Recovery

This bugfix phase restores normal goal-aware chat behavior without adding keyword shortcuts.

## Root Cause

- The SQL validator correctly rejected planner SQL that included `user_id`, but the orchestrator treated that rejection as terminal malicious behavior. Normal questions such as goal lists or advice could therefore return the generic safety failure instead of giving the planner a chance to repair the query.
- Backend user-scope injection appended `WHERE user_id = ...` after `GROUP BY` for grouped SELECTs without an existing `WHERE`, which made normal spending-advice queries invalid.
- The response composer trusted generic model failure hints too early and had no fallback for successful goal SELECT/UPDATE results.

## Fixes

- `user_id` mistakes are now repairable planner errors. They are still rejected and audited; the planner must repair by removing `user_id` and relying on backend scoping.
- Destructive SQL, forbidden/admin tables, multiple statements, and comments still stop immediately.
- User scope is inserted before `GROUP BY`, `HAVING`, `ORDER BY`, or `LIMIT`.
- Goal SELECT rows can be formatted directly from executed DB results when the final model hint is unusable.
- Goal UPDATE rows return a clean confirmation from the updated row.
- Generic failure hints such as "نتوانستم این درخواست..." are sanitized so they do not override successful DB-backed results.
- Goal title matching has a helper for Persian normalization and typo-tolerant comparison against real goal rows only.

## Manual Checks

- `لیست اهداف من و بده`
- `چه اهدافی دارم؟`
- `لپتاپ باید کی بخرم؟`
- `هدف لپتاپ من و بنداز یک سال دیر تر`
- `چطوری هزینه های غیر ضروری رو کم کنم؟`
- `پس اوضاع خیلی خرابه`
- `DROP TABLE users`
- `۳۰۰ هزار پول اسنپ دادم`
