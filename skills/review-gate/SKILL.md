---
name: review-gate
description: Use when reviewing a PR or accepting a task against its Done-when. Don't use when you built the change yourself.
---
# Review gate

Findings format, one per finding: **blocking** or **optional**; `file:line`; how it fails (concrete
input → wrong result); the fix. No vague style comments.

- At most **2 review rounds**. After that the Director decides. Optional findings become
  "Planning notes" on the issue, not more rounds.
- Checklists: **money** (integer pence, server-side amounts, idempotency keys, webhook is source of truth, live keys absent); **stock/reservations** (transaction + row lock, release paths); **personal data** (minimised, retention, no logs); **forms** (validation, spam, errors).
- A migration or a `risk_paths` file means the Principal reviews.
- Accept only against "Done when" with evidence. Never merge: the Board merges.
