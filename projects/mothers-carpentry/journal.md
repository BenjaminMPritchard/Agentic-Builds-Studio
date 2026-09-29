# Journal: Mothers Carpentry

## Pre-Studio history (from GitHub, back-filled 2026-09-29)

Before the Studio existed, the project ran as a single long-context Opus planning session
plus one Claude Code building session per phase, each ending in a PR against `main`.

- **2026-09-23** — PR #18 merged: Phase 0 skeleton (Django + DRF + PostgreSQL backend,
  React/Vite/TS frontend scaffold).
- **2026-09-24** — five phases merged in one day: PR #21 Phase 1 catalogue, PR #24 Phase 2
  basket, PR #25 Phase 3b delivery, PR #26 Phase 4 payment, PR #27 Phase 5 fulfilment, PR #32
  Phase 6 legal pages and retention, PR #33 Phase 5b refunds. (Phase 3a, Parcel2Go research,
  had no separate merge; it fed straight into 3b.)
- **2026-09-25** — PR #35 collection-time booking, PR #36 return-cost estimates, PR #37 Phase
  6c owner back office, all merged. State at `main` 36e7dea: phases 0–6, 3a/3b, 5b, collection
  slots, return costs and the back office are in; 13 of 22 sub-issues closed. 6b design (#29)
  is blocked on Benjamin and Terrie choosing the look; 6d, Phase 7 and Phase 8 wait on 6b, a
  revised plan and a hosting decision.
- Same day, a Claude Code design session (branch `claude/mothers-website-paperclip-design-it0ugo`,
  not merged to `main`) inspected the project's own cost and wrote `docs/paperclip/findings.md`
  — the basis for standing this project up in the Studio.

## 2026-09-25: entered the Studio
- State at `main` 36e7dea (PR #37, Phase 6c). Phases 0–6, 3a/3b, 5b, collection slots, return
  costs and the back office are merged; 13 of 22 sub-issues closed. 6b design (#29) waits on the
  owner's choices; 6d, Phase 7 and Phase 8 wait on 6b, a revised plan and a hosting decision.
- Cost to date (findings §3.1): about $1,412 over ~42 hours; 54% went on coordination, mostly an
  Opus planning session re-reading a long context on an hourly check. Reason for the Studio's
  event-driven Director and the script-only Clerk.
- Back-fill of the full log is a Recorder task (work-items.md).

## 2026-09-28: two more merges outside the phase plan
- PR #39 merged: switch off pallet delivery (#38) — Benjamin's decision recorded in findings
  §2 ("Pallet clean-up") acted on: migration seed reverted, a stale-return-cost test added, a
  lint fix. This was the Studio's pilot pallet clean-up work item (W2, work-items.md).
- PR #40 merged: bind dev Postgres and dev servers to 127.0.0.1 (infrastructure fix, unrelated
  to a phase).
