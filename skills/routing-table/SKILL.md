---
name: routing-table
description: Use when deciding who does a task (which agent, model and provider), splitting work for delegation, writing a scout or worker request, or deciding whether to retry or escalate. Don't use when just doing an assigned task.
---
# Routing table

The machine-readable table is `policy/routing.json`; this is how to use it. Every route is a starting
hypothesis, not a measurement: the usage-cap ledger records what each agent's runs really cost, and routes
change on that evidence (Benjamin approves changes).

## Pick by uncertainty and consequence, not length

A long job can be mechanical (read 200 files for one pattern); a three-line auth fix can need the strongest
reasoner. Spend strong models on judgement. Hand the doing to the cheapest agent that can do it reliably.

1. **You define** the scope, questions, sources, output, exclusions, stop and escalation conditions.
2. **Scripts** enumerate, search, count and validate (the Clerk, or commands in the packet). Never ask a
   model to read an exit code or recompute a total.
3. **A bounded worker** (Worker, Scout, Codex-Scout) interprets only what needs language understanding and
   returns an **evidence packet**.
4. **You synthesise** and decide. Check high-risk or surprising findings at the source; a summary is not proof.
5. **Implementation** follows the packet; new facts that break it mean escalation, not improvisation.

## Who does what

| Task | First route | If that fails or doesn't fit | Accept on |
| --- | --- | --- | --- |
| Monitoring, counts, file inventories, check status | Clerk (scripts) | model only for a new anomaly | script output |
| Summaries, exact quotes, classification, dedupe, inbox triage | Worker (local Qwen, `qwen-job`) | Scout / Codex-Scout | the job's own checks |
| Exhaustive research, repo inventory, "find every place" | Scout (Haiku) / Codex-Scout (Luna) | Builder | evidence packet with coverage |
| Plans, trade-offs, acceptance criteria | Director | Principal / Codex-Principal | explicit trade-offs; B needs Benjamin |
| Routine change to an established pattern | Builder-1/2 (Sonnet) / Codex-Builder (Sol) | Principal | targeted tests, `make check`, allowed paths |
| Multi-file feature or integration | Builder-1 / Codex-Builder | Principal / Codex-Principal | new tests, `make check`, review |
| UI and visual work | Builder-1 or Principal | Codex-Builder | screenshots phone + desktop, axe |
| Difficult debugging, migrations, incidents | Principal (Opus) / Codex-Principal (Astra) | Director | reproduced cause + failing test first |
| Auth, payments, permissions, refunds, data loss | Principal | Codex-Principal | risk tests + review by a *different* agent |
| Client replies | Liaison | Director, then Board | verified facts; human-confirmed send |
| Journals, metrics, lessons | Recorder | Worker | sources cited |
| Studio architecture review after a production phase | Architect (rare; skill `architect-review`) | — | one PR of proposals under `upgrades/` |
| "Done" on B or high-risk work | Clerk evidence | Principal / Codex-Principal reviews | author never accepts own work |

**Only route to active agents.** Scout, Codex-Scout, Codex-Builder and Codex-Principal are `planned` in
`policy/routing.json` until Benjamin activates them; until then use the next route in the row.

## Choosing a provider

Claude and Codex have separate caps (Claude 12% of each five-hour window, Codex 15%, both at most 80% of the
week) and separate allowances. When both a Claude and a Codex agent fit a row, prefer the one whose
provider has more headroom in the digest's **Usage** line. Moving work to the provider with spare allowance
raises throughput; it does not make the work "cheaper", and the percentages are never added together.
A run refused at a cap (exit 5) waits for the window; do not reroute high-risk work to a weaker route just to
avoid waiting.

For independent review of high-risk work, prefer the other provider (a Codex reviewer for Claude-built work
and the reverse): it catches different mistakes. Agreement alone is not acceptance evidence.

## Asking a scout or worker (the request)

State: the question, the exact scope (paths, commit, issue numbers), what to exclude, the output (the
evidence packet below), when to stop, and when to escalate instead of guessing. Chunk long jobs with a
coverage manifest so two scouts never scan the same files and nobody claims coverage they didn't do.

The evidence packet (required fields):
`task_id`, `repo_commit_or_source_snapshot`, `scope_requested`, `scope_checked`, `items_checked`,
`findings` (each: claim, path, line or section, observed date, evidence type), `negative_searches` (term,
scope, limits: absence is not proof), `commands_and_results`, `unknowns_and_contradictions`,
`coverage_gaps`, `next_required_action`.

A cheap scout that forces you to redo the investigation saved nothing: if the packet is thin, tighten the
request once, then escalate.

## Retry and escalation

- One bounded correction for a clear, local error. The same failure again means diagnosis or escalation,
  never a third try.
- Network and rate-limit failures are retried with backoff and are not reasoning failures.
- Escalation goes up only: Worker → Scout/Builder → Principal → Director → Board.

## Parallel work

Parallelise independent work with stable interfaces, each task in its own worktree. Keep dependent schema,
API and implementation work in order. Agents never start sub-agents (Constitution): delegation is a
Paperclip subtask with its own packet, so it is capped, attributed and visible. Parallelism does not create
allowance; it only helps when it raises accepted work or response time after coordination costs.

## Context

Keep durable state in Paperclip documents, not transcripts: the packet, approved plan, source commit,
touched paths, tests, decisions, open risks and next action. A new objective gets a fresh task. Pass
compact indexes and the important excerpts, not whole logs; keep screenshots and raw output as links.
