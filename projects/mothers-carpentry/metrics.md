# Metrics: Mothers Carpentry

## Pre-Studio build (to 2026-09-25), from findings.md §3.1

| Phase | Agent tier | Cost (USD, API list) | Notes |
|---|---|---|---|
| Planning (coordination), to 2026-09-25 | Opus | 766 | 54% of spend; 82% of all spend was cache read/write |
| 16 building sessions | Sonnet/Opus | 647 | Phase 4 was $252, 6c $73 |
| **Total**, ~42 hours of project time | | **1,412** | £1,070 at £1=$1.32 |

By token type across all pre-Studio sessions: cache reads 47%, cache writes 35%, output 18%,
fresh input ~0%.

| Session | Cost (USD) | Notes |
|---|---|---|
| Planning session | 751 | cache reads 37%, writes 41%, output 21% |
| Phase 4 (payment) | 252 | long session plus repeated real-browser Stripe runs |
| Phase 6c (back office) | 73 | 81% cache reads |

The planning session alone spent about $3.40/hour when nothing was happening (09:12–14:29 UTC,
$18 over 5.3 hours of hourly checks) — about £60/day just for checking. This is the concrete
number behind the Studio's event-driven Director and script-only Clerk (lessons.yaml L1).

## Since the Studio (2026-09-25 onward)

Source: the Clerk appends live figures from `/srv/studio/data/log/mothers-carpentry.jsonl`.
No entries recorded yet for this project as of this back-fill (2026-09-29); this table will be
extended as the Clerk logs sessions.
