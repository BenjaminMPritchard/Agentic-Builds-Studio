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
start. Tokens last one hour; longer runs lose GitHub access and must be re-woken.

### 4. Install the keys on the host (Benjamin) — only after every Claude agent is confined
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

### 5b. The Clerk uses the agents' App (Claude, then Benjamin)
The Clerk is a script run as `paperclip`, not a Claude agent. Its `gh` calls (listing agent PRs, posting
approved plans on GitHub issues) now use an `abs-agents` token for the repository's owner, cached for 50
minutes, instead of any inherited token. Once that is activated, remove `GH_TOKEN` from the Clerk's
settings in Paperclip.

### 6. Revoke the old token (Benjamin)
Every agent has held Benjamin's personal token. Once no agent uses it, revoke it on GitHub and give
the host's own tools a fresh one if they still need one.

## Result
Agents can push branches and open PRs as `abs-agents`, but cannot merge. `main` changes only by PR,
with a green `check`, merged by Benjamin or by `abs-merge-gate-1` when the merge gate allows it under
`policy/autonomous-merge.json`.
