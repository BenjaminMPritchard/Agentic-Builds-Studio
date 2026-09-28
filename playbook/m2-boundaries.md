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
| Embedded Postgres on `127.0.0.1:54329` | Reachable by every local user; its authentication method is **unverified** (not tested on purpose) |
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

### 3. Remove Docker access from agents (host; you)
```bash
sudo gpasswd -d paperclip docker
sudo systemctl restart paperclip        # supplementary groups apply to new processes only
id paperclip                            # expect no docker
grep ^Groups /proc/$(systemctl show -p MainPID --value paperclip)/status   # no 967
```
All agents are paused, so the restart interrupts nothing. Side effect, intended: agents can no longer
run Mothers' `make db-up`/`db-down` (the latter would stop the shared database). Your own Docker use is
unaffected. Rollback: `sudo gpasswd -a paperclip docker && sudo systemctl restart paperclip`.

### 4. Confine agents to their own Unix user (design; prototype on one agent first)
- New user `studio-agent` with no login shell privileges beyond its work; not in `docker`.
- `bin/agent-exec` wrapper set as each Claude agent's `adapterConfig.command`: runs `claude` as
  `studio-agent` through one narrow sudoers rule, passing through only the adapter's variables
  (Claude OAuth token, `PAPERCLIP_API_KEY`/run id, `GH_TOKEN`) and the working directory.
- Worktrees and `/srv/studio/work/*` shared through a group so both users can write.
- Result: agents cannot read Paperclip's data directory, its process environment or `/etc/paperclip.env`.
- Still open: the embedded database port. Its authentication must be checked by you (privileged read)
  and, if it accepts a default password or `trust`, hardened before step 5 means anything.
- Process adapters (Clerk, Worker) run deterministic Studio code; they can stay as `paperclip` for now.
- Rollback: restore `adapterConfig.command` to `claude` per agent.

### 5. Paperclip authenticated mode (host; you; after 4)
- `/etc/paperclip.env`: `PAPERCLIP_DEPLOYMENT_MODE=authenticated`, a new `BETTER_AUTH_SECRET`,
  `PAPERCLIP_PUBLIC_URL=http://127.0.0.1:3100`; keep loopback binding.
- `paperclipai auth bootstrap-ceo` → one-time invite for your Board login.
- Verify: an unauthenticated request is refused; your login works; a test agent run still authenticates
  with its run key; a `human_only` confirmation cannot be accepted by an agent key.
- Recovery: remove the mode variable and restart (back to `local_trusted`); requires `sudo` only.
- Before this: agree how `studio-stop` and any Board tooling authenticate.

### 6. GitHub: merge credential and reviewer identity (you create accounts/apps)
- A GitHub App (for example `studio-merge-gate`) installed on the authorised repos; its key readable only
  by the gate's process, not by agents.
- Ruleset on `main`: restrict updates, with the App as the only bypass actor, so agent tokens cannot merge.
- A separate reviewer identity (second account or App) listed in `trusted_reviewers`.
- Then optionally enforce code-owner review with you as a bypass actor.

### 7. Network exposure (decision)
Mothers Postgres and its dev server listen on all interfaces. Options: a host firewall rule limiting
5432/8000 to loopback and `tailscale0`, or binding the Mothers compose file to `127.0.0.1` (a Mothers
change, so it needs your authorisation). No change made.

## After Milestone 2
With steps 3–6 done, the Constitution's precondition for authorising a project's autonomous merge is
met; authorising one is still a separate decision recorded in `policy/autonomous-merge.json`.
