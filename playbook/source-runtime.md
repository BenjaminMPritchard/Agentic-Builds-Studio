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
