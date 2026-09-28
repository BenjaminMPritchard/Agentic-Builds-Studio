# Source and runtime relationship

Inspection date: 2026-09-27. This is a snapshot, not a claim about a later
running service.

| Item | Inspected value |
|---|---|
| Source checkout | `/home/benjamin/Agentic Builds Studio`, `main`, `7f462eb08d572924befb74a925de82a580daee27` before Milestone 1 edits |
| Source remote | `git@github.com:BenjaminMPritchard/Agentic-Builds-Studio.git` |
| Runtime checkout | `/srv/studio/company`, `main`, `4a914cf5d4bdc319968312c115e91aa789125f7e` |
| Runtime remote | `/home/benjamin/studio/studio-company` (obsolete local path) |
| Runtime worktree | No tracked modifications; untracked `.claude/settings.local.json` |
| Tracked content difference | 29 shared files differ; two source-only files (`lib/deploy.py`, `tests/test_deploy.py`) |
| Service template on host | `/etc/systemd/system/paperclip.service` uses unpinned `npx --yes paperclipai run` |
| Running Paperclip | `systemctl show`: active/running, started 2026-09-26; `/api/health`: `2026.916.1`, `local_trusted`, status `ok` |
| Running Studio code | Runtime checkout is `4a914cf`; independently verifying the code loaded by every process remains pending |
| Locally cached Paperclip package | `paperclipai@2026.916.1`, matching the health endpoint |
| Paperclip company | `Agentic Builds Studio`, one company, ID `bcf0f336-0c20-4194-9e21-fac517979ba0` |
| Projects | `Studio infrastructure` (`ba0da149-a497-4a85-82c5-1d6e0729cdde`); `Mothers Carpentry (Driftwood & Dovetail)` (`c2b582f3-d52e-47fd-812c-e29d6b805d3f`) |
| Mothers repository recorded by Paperclip | `https://github.com/Agentic-Builds-Studio/Mothers-Carpentry-Webpage.git` |
| Agents | 9 existing: Director, Principal, Builder-1, Builder-2, Architect, Liaison, Recorder, Worker, Clerk. Claude roles use `claude_local`; Worker and Clerk use `process`. Liaison and Principal were paused at inspection. |

The runtime-only `.claude/` file was inventoried by name only and was not read,
copied or deleted. Preserve it, credentials, logs, data, human pauses and
recovery state during any future deployment. Runtime HEAD is an ancestor of
source HEAD, but the obsolete remote and protected runtime state still make
an unplanned fast-forward unsafe.

## Deliberate deployment gate

Before activation, complete the remaining read-only runtime inventory:
workspace state, agent instructions/configuration, live adapter behaviour and
currently loaded Studio code. Preserve the
runtime-only file and all protected state. Decide a reconciled Git remote and
commit transition, record the rollback target, drain autonomous starts, and
run tests on the intended commit. Runtime activation, service changes and any
authentication change require the human approvals named in the implementation
plan. After activation verify the exact running commit, service health,
Paperclip, agents and absence of unexpected wakes.

`lib/deploy.py` and `STUDIO_AUTODEPLOY=1` are historical machinery. Ordinary
Clerk reconciliation must not activate source changes; disable this path before
live reconciliation is expanded in Milestone 3.

## Load path and activation scope (2026-09-28, read-only)

| Item | Inspected value |
|---|---|
| Claude agent instructions | Each `claude_local` agent uses `instructionsBundleMode=external` with `instructionsFilePath=/srv/studio/company/agents/<role>/AGENTS.md` |
| Guard and Claude settings | `/srv/studio/bin` → `/srv/studio/company/bin` and `/srv/studio/claude` → `/srv/studio/company/claude` (symlinks made by `bin/install`); `claude/settings.json` runs `/srv/studio/bin/guard` |
| Clerk and Worker | `process` adapters run `/srv/studio/bin/clerk tick` and `/srv/studio/bin/qwen-run`; `bin/clerk` imports `lib/` from the same checkout |
| Clerk mode | Env values are redacted by the API. `/srv/studio/data/log/studio.jsonl`: the last 200 events are `digest` with `dry: true`. `STUDIO_AUTODEPLOY` is not observable because the running code predates that step |
| Runtime vs source | `4a914cf..HEAD`: 43 files (36 modified, 7 added). This includes undeployed `main` work from PRs #3–#11 (Clerk `deploy_sync`, quota-window pacer that pauses/resumes Claude agents, Director-merge Guard exception later revoked by Milestone 1) |
| Live read contracts | Source `lib/paperclip.py` against the live API: agents (9), runs (`limit` honoured), paginated issues (`blockedBy` on every item), issue detail (`blocks`, `documentSummaries`), interactions, costs by agent/project and quota windows all parsed. Anthropic quota windows `ok` (3 windows); OpenAI quota read fails with a Codex app-server `--ask-for-approval untrusted` argument error |

Consequence: moving `/srv/studio/company` to a new commit **is** activation.
Instructions, Guard, Claude settings and Clerk code change together on the next
heartbeat or tool call. Rollback is moving the checkout back to `4a914cf`.
Before any move, `CLERK_DRY_RUN=1` must remain set and `STUDIO_AUTODEPLOY` must
be confirmed unset or not `1`; otherwise the new Clerk may fetch the obsolete
runtime `origin` and fast-forward itself.
