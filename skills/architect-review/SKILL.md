---
name: architect-review
description: Use only when running the end-of-project Studio review as the Architect. Don't use in any other role.
---
# Architect review

Inputs: `projects/*/metrics.md`, `lessons.yaml`, `journal.md`, `upgrades/`. Normalise by site type and phase.

1. **Diagnose:** biggest costs, loops, escalations, human waits, Worker pass rates.
2. **Judge** earlier experimental changes: keep, revert, or extend. Revert if the target metric got worse.
3. **Propose** up to 8 changes as `upgrades/<date>-proposal.md` (`templates/upgrade-proposal.md`). Each: evidence, one target metric, predicted effect, risk, how to undo, effect on complexity. Structural (L3) changes need evidence from two or more projects.
4. **Replay** deterministic rule changes against `/srv/studio/data/log/*.jsonl`; re-run `bin/qwen-run --score`.
5. **Open one PR.** Never apply, never merge.

Forbidden (see CONSTITUTION): weakening human gates, widening permissions/secrets/network, raising budgets beyond the cap, removing tests/reviews/Qwen checks, editing the rulebook, deleting history. No personal data in anything you write.
