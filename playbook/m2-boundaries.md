# Milestone 2: enforce boundaries

Status 2026-09-28: steps 1–2 implemented in source (not deployed); the rest is **proposed**.
Every host, Paperclip, GitHub or network change below needs Benjamin's approval, and most need
`sudo` in a real terminal. Order matters: authenticated mode is pointless while agents can read the
control plane's data, and autonomous merge stays forbidden by the Constitution until steps 4–6 are done.

## Findings that set the order (read-only, 2026-09-28)

| Finding | Consequence |
|---|---|
| `paperclip` (the agents' Unix user) is in the `docker` group | Root-equivalent: a container can mount `/` and read `/etc/paperclip.env`, Paperclip data and every credential |
| Agents run as the same Unix user as the Paperclip server | They can read Paperclip's data directory and the server's `/proc/<pid>/environ` (secrets) whatever the auth mode |
| Paperclip `local_trusted`: a request without a bearer token becomes `local-board`, an instance admin (`middleware/auth.js`) | Any local process that omits its agent key has Board authority, including accepting `human_only` confirmations |
| Studio's embedded Postgres is on `127.0.0.1:54330` (`/home/paperclip/.paperclip/...`); `54329` is Benjamin's own Paperclip instance | Paperclip's source hard-codes the embedded login `paperclip`/`paperclip` (a superuser), and the package's default `pg_hba` is `password` on loopback. Any local user can take over Paperclip's data, and a superuser can run shell commands (`COPY ... PROGRAM`) as `paperclip` |
| That database was started on 26 September by the hand-started Paperclip, before the systemd unit; it is outside the service and survived the restart | It still has the `docker` group after step 3 and must be restarted under the service |
| Mothers Postgres container on `0.0.0.0:5432`, dev server on `0.0.0.0:8000`; `bin/worktree-setup` uses a `mothers_carpentry:mothers_carpentry` login | Database reachable from the LAN with a guessable password |
| `worktree-cleanup` trusted agent-writable files for the database name and host | A bad `.studio-worktree` could drop the shared database (fixed, step 1) |
| Paperclip `pause` requires Board authority and cancels active runs; `resume` is allowed to agents holding `agent_config:update` | A human pause is not protected from agents with that grant. No agent has an explicit grant; whether the `ceo` role implies one is **unverified** |
| Rulesets on Studio and Mothers `main`: PR + `check` required, 0 approvals, no code-owner review, no bypass actors | Any token with write access can merge; review and CODEOWNERS are not enforced |
| Claude adapter accepts `adapterConfig.command` (default `claude`) | Agents can be run through a wrapper as a different Unix user without changing Paperclip |
| `authenticated` mode may stay on loopback; only `local_trusted` forces it | Authentication can be enabled without exposing Paperclip further |

## Steps

### 1. Safe cleanup — implemented (`e4881b1`)
`worktree-cleanup` recomputes the database name from the worktree directory, requires the per-worktree
token, refuses system databases and non-loopback servers. Tests: `tests/test_worktree_cleanup.py`.

### 2. DRAIN / STOP — implemented (`bc60632`)
`bin/studio-stop status|drain|stop|resume` (see `lib/stop.py`). Resume restores only agents it paused,
and only if untouched since. Guard blocks agents from it and from the pause/resume endpoints. Once
Paperclip is authenticated (step 5) it needs a Board credential.

### 3. Remove Docker access from agents — done by Benjamin 2026-09-28; one follow-up
`paperclip` is out of `docker` and the restarted server has no `docker` group. The Studio database
(port 54330) still runs from before the unit and keeps the group. Restart it under the service:
```bash
sudo systemctl stop paperclip
sudo kill -INT 1510749          # the old postmaster (fast shutdown); confirm the PID first
sudo systemctl start paperclip  # the server starts its database again, inside the unit
```
Verify: no `paperclip` process has group 967; the database's parent is the Paperclip server; health ok.

### 4. Confine agents to their own Unix user — prototype source ready
- `bin/agent-exec`: runs the Claude CLI as `studio-agent` through
  `sudo -n -E -H -u studio-agent -- setpriv --pdeathsig KILL -- <cli>`, keeping the adapter's
  environment and working directory; it refuses to start without `--settings`.
- The per-role `claude/<role>.json` files now carry Guard and the deny rules themselves (pinned to
  `claude/settings.json` by `tests/test_package.py`), because a confined agent does not read
  `paperclip`'s `~/.claude/settings.json`.
- `deploy/studio-agent/provision.sh` (dry run by default, `--apply` as root): the `studio` group and
  the `studio-agent` user, group-writable `/srv/studio/work` and `/srv/studio/locks`, a git
  `safe.directory` file, and the single sudoers rule (`deploy/studio-agent/sudoers`, checked by `visudo`).
- Then install the Claude CLI for `studio-agent`, switch **one** paused agent's `adapterConfig.command`
  to `/srv/studio/bin/agent-exec`, and run it once.
- Unknown until the prototype runs: whether the adapter writes temporary files `studio-agent` cannot read;
  where Mothers task worktrees are created (not configured explicitly).
- Database port: `deploy/studio-agent/studio-db.nft` restricts TCP to port 54330 on loopback to the
  `paperclip` user. It is not loaded by the script. ufw is active and the `nftables` service is disabled,
  so loading it and keeping it across reboots is Benjamin's decision.
- Rollback: restore `adapterConfig.command` to `claude`; remove `/etc/sudoers.d/studio-agent`.

Status 2026-09-28: `provision.sh --apply` run by Benjamin; Claude CLI 2.1.283 installed for
`studio-agent`; the `paperclip` → sudo → `setpriv` → `studio-agent` chain prints the CLI version.
Boundary check as `studio-agent`: `/etc/paperclip.env`, `/home/paperclip`, the Paperclip server's
`/proc/<pid>/environ` and the Docker socket are all refused; Guard runs; `/srv/studio/work` is
writable. Recorder (paused) has `adapterConfig.command=/srv/studio/bin/agent-exec` (merge PATCH;
env keys and other settings unchanged). No agent run was made: a Recorder run does real work
(journal, commit, PR), so the end-to-end test waits for genuine Recorder work. Rollback: set
`command` back to `claude`. Database port: Benjamin asked for the rule to load at boot. `deploy/studio-agent/studio-db-firewall.service`
(a oneshot unit, before `paperclip.service`) loads `/etc/studio/studio-db.nft`, which is safe to reload.
Install commands are in the unit file's header.

Status 2026-09-29, first live run (Recorder): it failed in 2 seconds with `EACCES`. The unknown above was
real: the adapter writes the agent's instructions, its prompt bundle (skills as symlinks into Paperclip's
home) and any MCP config under `/home/paperclip/.paperclip`, and passes them as
`--append-system-prompt-file`, `--add-dir` and `--mcp-config`. The earlier chain check ran only
`claude --version`. Fix: `agent-exec`, still `paperclip`, runs `bin/agent-stage` (`lib/agent_stage.py`),
which copies those into a per-run folder under `/srv/studio/data/agent-runs` (owned by `paperclip`, group
`studio`, mode 2750; agents cannot write there, so they cannot plant links for `paperclip` to follow),
dereferences the skill links, and rewrites the arguments. If staging fails the run does not start. Folders
older than a day are removed at each start. An MCP config can hold the run's own Paperclip key; the staged
copy is readable by `studio-agent` for up to a day, which a later run could read (agents share one user).
The three failed attempts made no model calls.

Working folder: for a task in a project with a folder, Paperclip starts the run in that folder, not the
agent's configured `cwd`. The "Studio infrastructure" project's folder is the runtime checkout
`/srv/studio/company` (the skills import reads it), which agents cannot write. Rule: Studio work tasks have
no project, so runs use the agent's own folder under `/srv/studio/work`. AGE-9 was taken out of the project
(clearing `projectWorkspaceId` too; `projectId: null` alone is ignored).

### 5. Paperclip authenticated mode (host; you; after 4)
- `/etc/paperclip.env`: `PAPERCLIP_DEPLOYMENT_MODE=authenticated`, a new `BETTER_AUTH_SECRET`,
  `PAPERCLIP_PUBLIC_URL=http://127.0.0.1:3100`; keep loopback binding.
- `paperclipai auth bootstrap-ceo` → one-time invite for your Board login.
- Verify: an unauthenticated request is refused; your login works; a test agent run still authenticates
  with its run key; a `human_only` confirmation cannot be accepted by an agent key.
- Recovery: remove the mode variable and restart (back to `local_trusted`); requires `sudo` only.
- Before this: agree how `studio-stop` and any Board tooling authenticate.

### 6. GitHub: merge credential and reviewer identity (no paid seats)
`Agentic-Builds-Studio-Client-Pages` is on the Team plan with 1 of 1 seats filled; Benjamin will not
pay for an extra seat. GitHub Apps are not members and use no seats, so:
- One GitHub App (for example `studio-merge-gate`) with Contents and Pull requests write on the
  authorised repositories; its private key readable only by the gate's process, not by `studio-agent`.
- Created 2026-09-28: App `abs-merge-gate-1` (ID 5109343), owned by BenjaminMPritchard, public (so it can
  be installed on the organisation), no webhook events; permissions contents and pull requests write,
  checks, statuses and metadata read. Installed on the organisation (verified; all repositories, by Benjamin's
  choice, so future client repositories are covered) and on `BenjaminMPritchard/Agentic-Builds-Studio`
  (owner-attested). The private key is kept off the host until the gate runs as `paperclip` behind a
  narrow sudo rule and every Claude agent runs as `studio-agent`.
- Rulesets on `main`: restrict updates, with the App as the only bypass actor, so agent tokens
  cannot merge.
- Review without a second GitHub identity: use Paperclip's review stage (a different agent, recorded in
  `executionState`), which the gate already checks. This needs a gate change: today it forces at least
  one GitHub approval for B or non-low-risk work; that minimum would move to a completed Paperclip review
  stage decided by an agent other than the assignee.
  Whether an App's own PR approval counts toward GitHub's required reviews is **unverified**; not needed
  under this design.

### 7. Network exposure (decision)
Mothers Postgres and its dev server listen on all interfaces. Options: a host firewall rule limiting
5432/8000 to loopback and `tailscale0`, or binding the Mothers compose file to `127.0.0.1` (a Mothers
change, so it needs your authorisation). No change made.

## After Milestone 2
With steps 3–6 done, the Constitution's precondition for authorising a project's autonomous merge is
met; authorising one is still a separate decision recorded in `policy/autonomous-merge.json`.
