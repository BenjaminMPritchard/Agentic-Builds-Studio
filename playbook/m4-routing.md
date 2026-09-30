# Milestone 4: routing and multi-provider execution

The research (`codex-claude-paperclip-model-routing-research.md`) is the source of truth. Benjamin's
requirement: the routing table covers every relevant agent, Codex agents included.

## 1. The routing table — implemented (this branch), not yet activated

- `policy/routing.json`: every agent (provider, model, effort, active or planned, what it is for), twelve
  task classes with first route, fallback, reviewer, escalation and acceptance (research 7.2), and the
  rules for provider choice, retries, parallel work and the evidence packet (7.1, 7.3, 8).
- `skills/routing-table/SKILL.md`: the same decisions written for the Director and the Principal.
- `task-packet` now defers to it; the packet template has a **Route** line; the Director's instructions
  name the skill. `tests/test_routing.py` keeps the table consistent (known agents, an active route for every
  task class, no retired or paid models, caps equal to `policy/quota.json`, the skill naming every agent).

Planned agents (not routable until activated): **Scout** (Claude Haiku 4.5), **Codex-Scout** (GPT-6
Luna), **Codex-Builder** (GPT-6 Sol), **Codex-Principal** (GPT-6 Astra).

### Activate (after merge)
The usual fast-forward, then (Board API, done by Claude): rescan the Studio skills and attach
`routing-table` to the Director and the Principal with `POST /api/agents/:id/skills/sync`, which leaves
the rest of each agent's settings alone.

## 2. Scout (Claude Haiku 4.5)

A `claude_local` agent through `agent-exec`, like the others: its own instructions (`agents/scout/`), a
read-mostly settings file, Haiku 4.5. Only Paperclip configuration and instructions; no host step.

## 3. Codex runtime (host steps, then code)

What Codex agents need before any can run, found on 2026-09-29:

| Need | State |
| --- | --- |
| Codex CLI for `studio-agent` | Installed only for Benjamin (0.156.1). Host step: install for `studio-agent` |
| ChatGPT sign-in | Device login into a Studio `CODEX_HOME` that `studio-agent` can read (Paperclip's managed Codex home is under `/home/paperclip`, which confined runs cannot read) |
| Confinement | `agent-exec` and the sudo rule allow only the Claude CLI; extend both to the Codex CLI, same `studio-agent` user and staging |
| Guard | Codex hooks are stable in 0.156; wire `bin/guard` as a pre-tool hook so Codex runs meet the same rules as Claude runs |
| Usage cap (15% / 80%) | `studio-quota` has no Codex reader, so Codex runs are refused today. Add one from the Codex App Server rate-limit buckets (`account/rateLimits/read`), inspecting every bucket (research 5.2) |
| Adapter | `codex_local` with `engine: "cli"` and `command` pointing at the Codex wrapper; `OPENAI_API_KEY` stays empty (no API billing) |

## 4. Model versions (decision for Benjamin)

Director, Principal and Architect run `claude-opus-5`; the research's shortlist names `claude-opus-5-5`,
which needs Claude Code 2.1.280 or later for `studio-agent`. Proposal: move them after checking that
version, then compare on real tasks before anything else changes.

## 5. Calibration

Routes are hypotheses. The usage-cap ledger already records each agent's measured cost per run; after a few
runs per agent, compare routes on accepted work per point of allowance (research 10–11) and change the table
with Benjamin's approval.
