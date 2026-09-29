# Paperclip authenticated mode

Status 2026-09-29: done. Runtime `84ec6d7` with the sudoers file installed; Paperclip in `authenticated`
mode, private exposure, sign-up closed; Benjamin claimed the Board (instance admin, company owner); Board key
saved in `~/.config/studio/paperclip-board-key` (0600). Verified: no key gets 401 as Benjamin and as
`studio-agent`; the key works (`studio-stop status`); all agents still paused with unchanged `pausedAt`; no run
started. The first attempt did not switch because the lines never reached `/etc/paperclip.env`; the step now
checks `grep -c` before restarting. Not yet exercised: an agent run's key through `agent-exec`, and the merge
gate reading with an agent's key. `CONSTITUTION.md` updated with Benjamin's approval.

## Why

In `local_trusted` mode Paperclip treats every request from this host without a key as the Board, an instance
admin. That includes the confined agents: `studio-agent` can reach `127.0.0.1:3100`. Guard blocks the obvious
calls, but Guard is defence in depth. In `authenticated` mode a request without a key or login session gets no
authority. The server stays on loopback with private exposure; that combination is allowed (checked in the
2026.916.1 server: only public exposure needs a public base URL).

| Caller | After the switch |
|---|---|
| Agent runs (Claude agents, Clerk, Worker) | unchanged: Paperclip gives each run its own key (the Clerk's actions are already recorded as the Clerk, not the Board) |
| Guard inside agent runs | unchanged: uses the run's key |
| Benjamin in the UI | email and password login |
| `studio-stop`, operator checks | a Board API key in `~/.config/studio/paperclip-board-key`, mode 0600 (`lib/paperclip.py` reads it when no key is in the environment; a file others can read is refused) |
| Merge gate called by an agent | the sudo rule keeps the agent's `PAPERCLIP_API_KEY` and `PAPERCLIP_RUN_ID`, nothing else; the gate only reads |

Switching also turns on secrets strict mode: saving agent settings with a plain value whose name looks secret is
refused. None of the current plain values do.

## Stage B: the switch (Benjamin)

Before: the runtime includes stage A and `/etc/sudoers.d/studio-agent` matches `deploy/studio-agent/sudoers`.
Every agent paused, no run active, health ok.

```bash
sudo install -o root -g root -m 0440 /srv/studio/company/deploy/studio-agent/sudoers /etc/sudoers.d/studio-agent
sudo visudo -cf /etc/sudoers.d/studio-agent
```

1. Switch and restart:
   ```bash
   sudo cp -p /etc/paperclip.env /root/paperclip.env.pre-auth
   printf 'PAPERCLIP_DEPLOYMENT_MODE=authenticated\nPAPERCLIP_DEPLOYMENT_EXPOSURE=private\n' | sudo tee -a /etc/paperclip.env >/dev/null
   sudo grep -c '^PAPERCLIP_DEPLOYMENT_' /etc/paperclip.env      # must print 2; stop otherwise
   sudo systemctl restart paperclip && sleep 15
   curl -sS http://127.0.0.1:3100/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["status"], d["deploymentMode"], d["deploymentExposure"])'
   ```
   Expect `ok authenticated private`.
2. Claim the Board. Open the Paperclip UI on the same host as the claim link (normally http://127.0.0.1:3100), create an account (email and password) and stay signed in.
   Then open the one-time claim link from the log (valid 24 hours):
   ```bash
   sudo journalctl -u paperclip --since "15 min ago" -o cat | grep -o 'http://[^[:space:][:cntrl:]]*/board-claim/[^[:space:][:cntrl:]]*' | tail -1
   ```
   Your account becomes instance admin and owner of the company; the implicit `local-board` admin is removed.
3. Close sign-up and restart:
   ```bash
   printf 'PAPERCLIP_AUTH_DISABLE_SIGN_UP=true\n' | sudo tee -a /etc/paperclip.env >/dev/null
   sudo systemctl restart paperclip && sleep 15
   ```
4. Create the Board API key and save it where the Studio's tools look:
   ```bash
   export PAPERCLIP_AUTH_STORE=$HOME/.config/studio/cli-auth.json
   npx --yes paperclipai@2026.916.1 auth login --api-base http://127.0.0.1:3100 --no-browser
   # open the printed URL while signed in and approve
   python3 -c 'import json,os; p=os.environ["PAPERCLIP_AUTH_STORE"]; c=json.load(open(p))["credentials"]; t=next(iter(c.values()))["token"]; f=os.path.expanduser("~/.config/studio/paperclip-board-key"); fd=os.open(f, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600); os.write(fd, (t+"\n").encode()); os.close(fd); print("saved")'
   rm "$PAPERCLIP_AUTH_STORE"; unset PAPERCLIP_AUTH_STORE
   ```
5. Checks (Claude runs the first and last):
   - No key, as Benjamin and as `studio-agent`, gets nothing:
     `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3100/api/companies` and
     `sudo -u studio-agent curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:3100/api/companies`,
     both 401 or 403.
   - `/srv/studio/bin/studio-stop status` works with the key.
   - All agents still paused with their original `pausedAt`; no run started.
   - Delete the backup, which holds the checkout token: `sudo rm /root/paperclip.env.pre-auth`.

The first agent run afterwards is the first live test of run keys through `agent-exec` and of the merge gate
reading with an agent's key.

## Rollback

```bash
sudo sed -i '/^PAPERCLIP_DEPLOYMENT_MODE=/d; /^PAPERCLIP_DEPLOYMENT_EXPOSURE=/d; /^PAPERCLIP_AUTH_DISABLE_SIGN_UP=/d' /etc/paperclip.env
sudo systemctl restart paperclip
```
`local_trusted` grants the Board without consulting the database, so this works even if the login or the claim
failed. Accounts and keys stay in the database, unused, until the next switch.

## Afterwards

`CONSTITUTION.md` states the `local_trusted` gap. Once stage B is verified, Claude proposes the change and
Benjamin approves it; the Constitution is changed only with his explicit approval.
