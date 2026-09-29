# GitHub identities and merge rules

Status 2026-09-28: plan agreed with Benjamin; steps are marked done as they complete.

## Why

Agents currently use Benjamin's own GitHub token: the Mothers agent PR `agent/38-…` was authored by
`BenjaminMPritchard`. To GitHub an agent *is* Benjamin, so any bypass Benjamin has, agents have, and
every agent holds his personal token. Paid seats are ruled out (the client organisation is on the Team
plan, 1 of 1 seats). GitHub Apps are free and use no seats, so there are three identities:

| Identity | What it may do | Merge `main`? |
|---|---|---|
| **Benjamin** (`BenjaminMPritchard`) | everything; merges by hand | yes, by pull request |
| **`abs-merge-gate-1`** (App 5109343) | read PRs and checks; merge | yes, by pull request, only via the merge gate |
| **`abs-agents`** (App 5110225) | push branches, open and comment on PRs and issues, read checks | **no** |

## Order of steps

### 1. Rulesets on `main` (Benjamin) — safe to add now
Status 2026-09-28: Studio repository done ("Agentic Builds Studio Agents": Restrict updates; bypass Repository
admin and `abs-merge-gate-1`, mode *always*, harmless because "Protect Main" has no bypass and requires a PR).
Organisation: **not yet in force** on Mothers (its effective rules show no `update` rule).
Bypass actors skip *every* rule in a ruleset they bypass, so the merge restriction is its own ruleset.

**Ruleset 1: keep the existing one unchanged** ("Protect Main" on Studio, "Protect main (Customer
Projects)" on Mothers). Restrict deletions; block force pushes; require a pull request (0 approvals,
merge method "Merge"); require status check `check` (Studio: branch must be up to date).
**Bypass list: empty**, so everyone, including both Apps and Benjamin, needs a PR and a green `check`.

**Ruleset 2: new, "Merges: gate or Benjamin only".**
- Enforcement status: **Active**
- Target branches: **Add target → Include default branch**
- Branch rules: tick **Restrict updates** only
- Bypass list → **Add bypass**:
  - Studio repository (personal account): `abs-merge-gate-1` and **Repository admin**
  - Client organisation (organisation ruleset, so every future client repository is covered):
    `abs-merge-gate-1` and **Organization admin**
  - For each bypass entry set the mode to **For pull requests only** (nobody pushes to `main` directly)
- Where:
  - Studio: https://github.com/BenjaminMPritchard/Agentic-Builds-Studio/settings/rules → **New ruleset →
    New branch ruleset**
  - Organisation: https://github.com/organizations/Agentic-Builds-Studio-Client-Pages/settings/rules →
    **New ruleset → New branch ruleset**, Target repositories: **All repositories**

Until step 5 is done this does not stop agents, because they still act as Benjamin.

### 2. Create the agents' App (Benjamin)
Status 2026-09-28: created as `abs-agents` (ID 5110225), no webhook events, installed on all organisation
repositories (Studio repository install owner-attested). **Issues: Read and write is missing.**
https://github.com/settings/apps/new
- Name: `abs-agents` (or similar); Homepage: the Studio repository URL
- Webhook: **Active unticked**; no callback URL
- Repository permissions: **Contents: Read and write**, **Pull requests: Read and write**,
  **Issues: Read and write**, **Checks: Read**, **Actions: Read** (CI logs), **Metadata: Read**.
  Leave **Workflows: No access** (agents cannot change CI) and everything else "No access".
- Where can it be installed: **Any account**
- Create; note the App ID; **Generate a private key** (keep it off the host for now)
- **Install** on `BenjaminMPritchard` → `Agentic-Builds-Studio`, and on
  `Agentic-Builds-Studio-Client-Pages` → **All repositories**
- **Do not** add it to any ruleset bypass list

### 3. `agent-exec` gives each run an agents' App token (Claude) — implemented, not activated
Before dropping to `studio-agent`, `agent-exec` (running as `paperclip`) asks `bin/agent-github-token`
for a one-hour token for the run's account and passes it as `GH_TOKEN`, replacing any inherited token;
git uses it through `gh`. The account is the agent's `STUDIO_AGENT_GITHUB_OWNER` setting
(default: the client organisation). If the App is configured and no token can be made, the run does not
start.

Tokens last one hour, and the Architect's runs can be longer, with its pull request at the end. So each run
also gets a **grant**: a random ID that `agent-exec` records, as `paperclip`, in `/srv/studio/data/agent-grants`
(readable by `paperclip` only), naming the run's account and expiring after 8 hours. In the run, `gh` is
`agent-bin/gh` and git's credential helper is `bin/agent-git-credential`; both ask `bin/agent-gh-token` for a
token, which uses the starting token for 45 minutes and then renews through
`sudo -u paperclip /srv/studio/bin/agent-github-token --grant ID`, the only form the sudo rule allows. The grant,
not the agent, decides the account; the agent never sees the key; renewed tokens still cannot merge; nothing
renews after the grant expires. All agents share the `studio-agent` user, so one run could read another
concurrent run's environment, including its grant and token. Every token has the same App permissions, so
this changes which account's repositories a run could reach, not what it could do there. Separate users per
role would close it.

Activation (Benjamin), after the runtime is on the commit that adds this:
```bash
sudo install -o root -g root -m 0440 /srv/studio/company/deploy/studio-agent/sudoers /etc/sudoers.d/studio-agent
sudo visudo -cf /etc/sudoers.d/studio-agent
sudo -u studio-agent sudo -n -l | grep agent-github-token     # the new rule, and nothing broader
# PATH passed on the sudo command line survives secure_path (agent-exec relies on this for the gh wrapper):
sudo PATH=/srv/studio/company/agent-bin:/usr/bin /usr/bin/printenv PATH    # expect the agent-bin path first
sudo -u paperclip sudo -n -u studio-agent PATH=/srv/studio/company/agent-bin:/usr/bin \
  /usr/bin/setpriv --pdeathsig KILL -- /home/studio-agent/.local/bin/claude --version   # the rule accepts it
```

### 4. Install the keys on the host (Benjamin) — only after every Claude agent is confined
Status 2026-09-29: done. All three files are root:paperclip 0640. As `paperclip`, each App issued a
token: `abs-agents` for both accounts, `abs-merge-gate-1` for the Studio repository. The policy now names
the merge App (this PR).
While any agent still runs as `paperclip`, it could read keys readable by `paperclip`. After step 5:
```bash
sudo install -D -o root -g paperclip -m 0640 ~/Downloads/<merge-gate>.pem /etc/studio/merge-gate-app.pem
sudo install -D -o root -g paperclip -m 0640 ~/Downloads/<agents>.pem     /etc/studio/agents-app.pem
echo '{"app_id": <agents App ID>, "key_path": "/etc/studio/agents-app.pem"}' | \
  sudo install -D -o root -g paperclip -m 0640 /dev/stdin /etc/studio/agents-app.json
rm ~/Downloads/<merge-gate>.pem ~/Downloads/<agents>.pem
```
Then Claude adds `"github_app": {"app_id": 5109343, "key_path": "/etc/studio/merge-gate-app.pem"}` to
`policy/autonomous-merge.json` by PR.

### 5. Move every Claude agent to `agent-exec` and remove Benjamin's token (Claude, with approval)
One agent at a time: set `adapterConfig.command` to `/srv/studio/bin/agent-exec`, set
`STUDIO_AGENT_GITHUB_OWNER` where the agent works on the Studio repository, and remove `GH_TOKEN`
(Benjamin's token) from its settings. Recorder is already on `agent-exec`.

Status 2026-09-29: done (Benjamin ran the update). All seven Claude agents run through `agent-exec` with
no `GH_TOKEN`; Architect and Recorder have `STUDIO_AGENT_GITHUB_OWNER=BenjaminMPritchard`; all still
paused. Until step 4 they have no GitHub access. Rollback revisions (`POST
/api/agents/<id>/config-revisions/<revision>/rollback`): Recorder `dd7fb8ef`, Architect `ffc1af35`,
Director `aafb8c4a`, Principal `27eca6de`, Builder-1 `3b1644b4`, Builder-2 `5c7c0250`, Liaison `72b4ca63`.
Still open: the Clerk (a `process` agent) holds Benjamin's `GH_TOKEN`, and Architect and Recorder hold
`GH_TOKEN_SITE_READ`; both must be replaced before step 6.

### 5b. The Clerk uses the agents' App (Claude, then Benjamin)
The Clerk is a script run as `paperclip`, not a Claude agent. Its `gh` calls (listing agent PRs, posting
approved plans on GitHub issues) now use an `abs-agents` token for the repository's owner, cached for 50
minutes, instead of any inherited token. Once that is activated, remove `GH_TOKEN` from the Clerk's
settings in Paperclip.

### 6. Revoke the old token (Benjamin)
Every agent has held Benjamin's personal token. Once no agent uses it, revoke it on GitHub and give
the host's own tools a fresh one if they still need one.

Status 2026-09-29: done. The Clerk's `GH_TOKEN` was removed and the runtime activated (`ae0c667`, then
`a387d9e` and `48e337a` for token renewal). Paperclip itself also used a token: with no company secret named
`GITHUB_TOKEN`/`GH_TOKEN`, it falls back to the server's `GH_TOKEN` (`/etc/paperclip.env`) to clone and fetch
project repositories, and Mothers is private. That is now `paperclip-checkout-read`, a fine-grained token on
the client organisation, all repositories, Contents read-only. The Paperclip secret "Github Studio Ops
External" (Architect's and Recorder's `GH_TOKEN_SITE_READ`) holds the same token, as version 2. Benjamin
revoked studio-ops-internal, studio-ops-external and every other fine-grained token, and deleted the unused
secrets "Ops Internal", "Coord" and "Build Token".

| Who | GitHub access |
|---|---|
| Claude agents | `abs-agents` App, per run, renewed through a run grant; cannot merge |
| Architect, Recorder (site reads) | `paperclip-checkout-read`, read-only, as `GH_TOKEN=$GH_TOKEN_SITE_READ gh ...` |
| Clerk | `abs-agents` App, per repository owner |
| Merge gate | `abs-merge-gate-1` App |
| Paperclip server (checkouts) | `paperclip-checkout-read` |

`paperclip-checkout-read` is still Benjamin's identity, read-only. Replacing it with an App token would need
Paperclip's managed GitHub connection, not yet explored.

## Result
Agents can push branches and open PRs as `abs-agents`, but cannot merge. `main` changes only by PR,
with a green `check`, merged by Benjamin or by `abs-merge-gate-1` when the merge gate allows it under
`policy/autonomous-merge.json`.
