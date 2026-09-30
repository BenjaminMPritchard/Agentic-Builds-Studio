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

## 3. Codex runtime — implemented (this branch), not yet activated

| Need | Done |
| --- | --- |
| One Codex binary for everyone | `deploy/codex-setup.sh` installs Benjamin's Codex (0.156.1, a static binary) as root-owned `/usr/local/bin/codex` |
| Guard and the Constitution for Codex | `/etc/codex/requirements.toml` (from `deploy/codex/requirements.toml`), managed settings nobody can override: Guard as the only pre-tool hook for shell, patches and MCP tools (no per-hook trust step), `multi_agent` and `multi_agent_v2` off (no sub-agents), sandbox limited to read-only and workspace-write. `agent-exec` refuses a Codex run unless all of these are pinned, and refuses Codex's bypass flags |
| Guard understands Codex edits | `bin/guard` checks `apply_patch` the way it checks Edit/Write: every file the patch adds, updates, deletes or moves against protected paths and `main`, added lines for live keys. (Also fixed for Claude: a new file in a new folder on `main` was not caught) |
| Confinement | `agent-exec` with `STUDIO_AGENT_PROVIDER=codex` runs `/usr/local/bin/codex` as `studio-agent` through the same staging, scratch sharing, App token and quota steps; a new sudo rule allows exactly that binary |
| Sign-in | ChatGPT device login, once, as `studio-agent` into `/srv/studio/data/codex-home` (Codex rewrites `auth.json` owner-only on every token refresh, so one user must own it). Paperclip writes skills there. No API key anywhere: `OPENAI_API_KEY` is empty and `agent-exec` removes it |
| 15% / 80% cap | `studio-quota` reads Codex with `account/rateLimits/read` from `codex app-server` (no model call), run as `studio-agent`; windows found by length (300 and 10080 minutes), other buckets count toward account headroom only. Verified live against Benjamin's account on 2026-09-30 (5-hour 100%, week 37%: correctly refused) |
| Agents | Codex-Scout (GPT-6 Luna), Codex-Builder (GPT-6 Sol), Codex-Principal (GPT-6 Astra): instructions in `agents/codex-*`, payloads in `package/payloads/`; CLI engine, no bypass, no fast mode, `/srv/studio/projects` writable for commits in project worktrees |

The docs do not say outright that `requirements.toml` applies to `codex exec`; the first Codex run proves it with
a deliberate Guard check before any real work. Codex reviews go through Paperclip's review stage (Codex has
no `/code-review`, and sub-agents are off).

### Activate (Benjamin, after #44 and this PR are merged)
1. The usual fast-forward.
2. `sudo bash /srv/studio/company/deploy/codex-setup.sh`, then the sign-in it prints (as `studio-agent`).
3. Work folders: `sudo install -d -o paperclip -g studio -m 2775 /srv/studio/work/{scout,codex-scout,codex-builder,codex-principal}`.
Claude then creates the four agents paused, checks `studio-quota status --provider codex`, and marks them
active in `policy/routing.json` once the first Guard check passes.

## 4. Model versions — done 2026-09-30

Director, Principal and Architect run `claude-opus-5`; the research's shortlist names `claude-opus-5-5`,
which needs Claude Code 2.1.280 or later for `studio-agent`. Checked: `studio-agent` runs 2.1.283 (from Scout's run
log). Benjamin approved; the three agents were moved to `claude-opus-5-5` with a `model`-only update (Paperclip merges
it and keeps hidden secrets); effort levels unchanged.

## 5. Calibration

Routes are hypotheses. The usage-cap ledger already records each agent's measured cost per run; after a few
runs per agent, compare routes on accepted work per point of allowance (research 10–11) and change the table
with Benjamin's approval.

## First Scout run (2026-09-30): AGE-18, branch triage

Run `388b38ef`, Haiku 4.5, about 2.5 minutes, admitted by the usage caps, in a Mothers project worktree under
`/srv/studio/projects/mothers` (the first run to use it). Useful in shape, wrong on its headline: it called
`claude/affectionate-edison-hv676j` "critical bug fixes, app crashes without them, none in main", but the
bugs were in that branch's own ShopConfig code, which never reached `main`. Checking at the source caught it,
as research 7.1 requires of the requester. It also marked its task `done` instead of handing it back, wrote
no `evidence` document, and skipped the Studio-repo comparison. Instructions now say: write the document,
hand back as `in_review`, never `done`; check claims about `main` against `main`; fetch the other repository
when asked to compare. Lesson for routing: a scout's finding that would cause code to be ported, merged or
deleted is checked by the requester before anyone acts on it.

## 6. Efficiency records, first increment (research 11) — implemented (this branch)

- **Per-run usage** (`bin/studio-quota`): when a run ends (released, process gone, no reading, too old), the
  controller appends one record to `/srv/studio/data/quota/<provider>-runs.jsonl`: Paperclip run id, agent,
  studio points used per window (a bound), reservation, window ids, how it ended. `agent-exec` passes
  `PAPERCLIP_RUN_ID`.
- **Run records** (`lib/records.py`, Clerk step `record_runs`): every finished run once, append-only, in
  `/srv/studio/data/records/runs.jsonl`: identity, issue, wake reason, status, timing, resolved model,
  billing type, tokens as reported, Paperclip's API-equivalent estimate, joined with its usage record.
  Written in dry-run too (records are evidence, not Paperclip state).
- **Report** (`clerk report` → `records/report.md`): per agent: runs, outcomes, median and p90 duration,
  Claude and Codex points per run in separate columns, output tokens, where the runs' issues stand.
- **Not yet** (stated in the report): first-pass acceptance and rework share (need review outcomes per work
  package), human minutes, latency against targets, local energy, project-interval and completion reports.

## Codex Guard check (2026-09-30): AGE-19, Codex-Scout on GPT-6 Luna

- First runs failed before starting: `config.toml` in the Codex home was 0600 (fixed in #52), then Codex refused
  a non-repository folder (`--skip-git-repo-check` added to the Codex agents' `extraArgs`; the adapter does not
  add it twice).
- **Guard governs `codex exec`:** a live-key command, a patch creating `CONSTITUTION.md` and a push to `main`
  were all refused with the Studio Guard's own messages. The managed hooks in `/etc/codex/requirements.toml` apply.
- **`multi_agent = false` does not remove `spawn_agent`.** Guard now refuses sub-agent tools by name, and the
  Codex hook matcher covers every tool. Re-run `deploy/codex-setup.sh` to install the new requirements file.
- Codex-Scout reported it had no Paperclip controls to set its task's status (it did comment). To look into
  before any Codex agent is made routable.
- Re-check after #53: steps 1–3 refused again; Codex-Scout declined to call `spawn_agent` (Studio rule), so the
  block stands on the Guard tests and the `.*` hook matcher. **Why Codex had no Paperclip tools:** Paperclip
  writes its MCP gateways into `config.toml` with `headers = {...}`, which Codex 0.156 ignores (it reads
  `http_headers`), so the tools had no credentials. `agent-exec` now renames the key in `[mcp_servers.*]` tables.
- Final check after #56: Codex-Scout commented on AGE-19 and handed it back to Benjamin with `studio-task`.
  **Codex-Scout, Codex-Builder and Codex-Principal are active in the routing table from 2026-09-30.**
- First real Codex task (AGE-6, Phase 7a, Codex-Principal): stopped before any change and handed back. Codex's
  sandbox mounted `/srv/studio/projects/mothers/repo/.git` read-only (no worktree, no commits), and `gh` read
  Paperclip's `GH_CONFIG_DIR` (`/home/paperclip/.config/gh`, unreadable). Codex-Builder and Codex-Principal are
  back to `planned` until both are fixed; Codex-Scout stays active. 7a returns to the Claude Principal.
- Fix for both (IMPLEMENTED, not yet verified in a live run): `agent-exec` extends a Codex agent's
  `sandbox_workspace_write.writable_roots` in place with every repository's `.git` up to three levels below its
  roots (`/srv/studio/projects/mothers/repo/.git`). Codex keeps `<root>/.git` read-only and follows a worktree's
  gitdir pointer to it, but a `.git` named as a writable root of its own is writable: checked with
  `codex sandbox` (no model use) for a commit in the repository and in a worktree. `agent-exec` also sets
  `GH_CONFIG_DIR=/home/studio-agent/.config/gh` for every run. The builders go back to `active` after one real
  Codex-Builder task commits and opens its PR.
- Known, not new: the `studio` group can already write every project's `.git` (hooks, config), for Claude agents
  too. Paperclip runs git in those repositories as `paperclip` (workspace worktrees), so a planted hook or
  filter would run as `paperclip`. Tracked separately; this fix does not widen it.
