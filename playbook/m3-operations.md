# Milestone 3: operate within limits

Order: usage caps first (nothing else should spend model time before they hold), then Clerk repairs, then
workspace safety. Everything here is deterministic code; no step needs an agent run to build or test.

## 1. Usage caps — implemented (this branch), not yet activated

Benjamin's caps (research sections 2–3): studio use at most **12%** of each Claude five-hour window and
**15%** of each Codex one, and at most **80%** of each weekly allowance; the other 20% of the week is his.
`policy/quota.json` holds the numbers; changing them needs his approval.

- **Where it is enforced:** `bin/agent-exec`, which every confined agent run passes through. Before the CLI
  starts, `bin/studio-quota admit` takes a reading and reserves the run's estimated cost; if any check fails
  the run does not start (exit 5: cap reached; exit 6: no reading). Paperclip records the run as failed with
  the reason. A detached `studio-quota release --after-pid` waits for the run to end, takes a second reading
  and releases the reservation.
- **Readings:** `claude -p /usage` as `paperclip` (no model call; the run's token and any API key are
  removed, so it reads the subscription meter). Paperclip's own quota poll fails for both providers on this
  host (its Claude poll scripts an interactive session; its Codex poll passes an option the installed Codex
  rejects), so it is not used.
- **Attribution:** the meter includes Benjamin's own use. Usage that accrues between two readings while any
  studio run is active counts as studio use; otherwise as personal. This over-counts the studio when he works
  at the same time, never the reverse.
- **Checks** (percentage points; `lib/quota.py`): studio 5-hour and weekly use + active reservations + this
  run's estimate + margin within the studio caps; account 5-hour and weekly within 100, keeping the unused
  part of his 20% free; any full model-specific weekly limit refuses.
- **Estimates:** 3 points (5-hour) and 0.5 (weekly) per run until an agent has 3 measured runs, then the
  largest of its last 20 (never below 1 and 0.2). These are starting guesses, not measurements.
- **Limits, stated plainly:** usage is reported late and rounded and a run cannot be stopped mid-request, so
  these are operating caps with conservative admission, not a guarantee against overshoot. A running agent
  is not stopped when a cap is reached; only new runs are refused. Codex has no reader yet, so no Codex run
  can start until one is added (with the routing table).
- **Ledger:** `/srv/studio/data/quota/claude.json` (paperclip, 0600). Agents cannot read or write it.

### Activate (Benjamin, after merge)
Probe first; if the probe fails, do not activate (every run would be refused until it is fixed):
```sh
sudo -u paperclip -H env PATH=/home/paperclip/.local/bin:/usr/local/bin:/usr/bin:/bin \
  /srv/studio/company/bin/studio-quota status --provider claude
```
Expect JSON with the account percentages that `/usage` shows you. Then the usual fast-forward of
`/srv/studio/company`; `agent-exec` picks the change up on the next run. Rollback: tag `pre-m3a`.

## 2. Clerk repairs — implemented (this branch), not yet activated

Defects found reading `lib/clerk.py` (it has only ever run in dry-run):

| Defect | Effect | Fix |
| --- | --- | --- |
| Dry-run recorded events as handled | when dry-run ended, everything it had seen (merged PRs, plan approvals) was never acted on | dry-run receipts last one tick; nothing is persisted |
| Receipt written before the write | a failed Paperclip write was never retried | `once()`: the receipt is kept only after the write succeeds |
| PRs linked by branch-name prefix, only for issues with a `GitHub:` line | Studio issues (AGE-9 / PR #33) were invisible; any matching PR could close an issue | PRs are followed through the issue's `pull_request` work products (the merge gate's format); a branch-name match is only reported to the Director |
| Any merged PR marked the issue done | an issue with several PRs, or still in progress, could be closed early | done only when every recorded PR is closed, one merged, and the issue is already `in_review`; otherwise the Director decides |
| Pacer read Paperclip's quota poll (fails on this host) and paused/resumed agents | never held; would have fought human pauses | removed: `agent-exec` enforces the caps (step 1); the digest reports the ledger |
| Dry-run tick stored the Director-wake hash | the first live tick could skip a due wake | stored only when live |
| Receipts grew forever | slow state file | pruned after 60 days |

Agents record PRs with `agent-bin/studio-record-pr <issue id> <PR URL>` (house rules, task packet and Director
heartbeat updated). It reads the PR from GitHub, writes the `pull_request` and head `commit` work products, and
archives superseded heads; running it again changes nothing. The Clerk also sets a recorded PR's work
product to `merged`/`closed` so the merge gate stops counting it as live.

### Activate (Benjamin, after merge)
The usual fast-forward. The Clerk stays in dry-run (`CLERK_DRY_RUN=1`); read one tick's
`/srv/studio/data/digest.md` before deciding to turn dry-run off, which is a separate decision.
`STUDIO_AUTODEPLOY` must stay unset: its `deploy_sync` step fast-forwards the runtime by itself, which
conflicts with the rule that source changes are activated by hand.

## 3. Workspace safety — implemented (this branch), not yet activated

| Gap | Fix |
| --- | --- |
| A task in a project whose folder is the runtime checkout starts the agent in `/srv/studio/company` (seen with AGE-9); the rule "Studio tasks have no project" was only written down | `agent-exec` refuses to start in `/srv/studio/company` or `/srv/studio/company-*` (exit 2, with the reason) |
| Each confined run left its `/tmp/paperclip-run-*` scratch folder behind: the agent's subfolders are `studio-agent`'s, so Paperclip's clean-up could not remove them | `agent-stage` gives the scratch folder a default ACL, so everything created in it stays removable by `paperclip` |
| Staged copies (including an MCP config that can hold the run's Paperclip key) were kept for 24 hours | run folders are named after the `agent-exec` process and removed once it is gone: by the post-run watcher (`agent-stage --prune`), or at the next run's staging; 24 hours stays as the backstop |

### Activate (Benjamin, after merge)
The usual fast-forward. Then, with every agent paused (they are), remove the scratch folders earlier runs
left behind; this needs root because the agent's files inside are not paperclip's:
```sh
ls -d /tmp/paperclip-run-* && sudo rm -rf /tmp/paperclip-run-*
```
