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
