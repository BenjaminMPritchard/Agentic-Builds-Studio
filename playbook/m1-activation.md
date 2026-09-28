# Milestone 1 runtime activation procedure

Status: **proposed; not approved and not run.** Activation moves the runtime checkout
`/srv/studio/company` from `4a914cf` to an approved `TARGET` commit. Instructions, Guard,
Claude settings and Clerk code all load from that checkout, so the move is the activation.
The procedure changes nothing else: the Paperclip service, auth, agents' config, human pauses,
the obsolete runtime `origin`, the untracked `.claude/`, data, logs and Mothers are untouched.

Preconditions (owner-attested 2026-09-28): Clerk `STUDIO_AUTODEPLOY=0`, `CLERK_DRY_RUN=1`;
Clerk, Principal and Liaison paused by a human. The merge policy authorises no project.

Steps marked **(you)** need `sudo` in a real terminal. The others are read-only checks the
implementation agent can run.

## 0. Choose TARGET

- **Recommended:** push `feat/studio-m1-truthful-source`, open a PR and merge it yourself.
  `TARGET` is then the resulting `main` commit, so the runtime equals `main`. Both merge
  styles still fast-forward from `4a914cf`.
- **Alternative:** `TARGET` = the reviewed branch head. The runtime then runs unmerged commits
  until `main` catches up.

## 1. Pre-flight (read-only)

```bash
S='/home/benjamin/Agentic Builds Studio'; R=/srv/studio/company; TARGET=<approved sha>
git -c safe.directory=$R -C $R rev-parse HEAD                   # must be 4a914cf5d4bdc319968312c115e91aa789125f7e
git -c safe.directory=$R -C $R status --short                   # must be exactly: ?? .claude/
stat -c '%n %s %Y' $R/.claude/settings.local.json               # record; must be identical after
git -C "$S" merge-base --is-ancestor 4a914cf "$TARGET" && echo ff-ok
git -C "$S" worktree add --detach /tmp/claude-1000/m1-target "$TARGET" \
  && (cd /tmp/claude-1000/m1-target && python -W ignore -m unittest discover -s tests -t .) ; \
  git -C "$S" worktree remove --force /tmp/claude-1000/m1-target
curl -sS http://127.0.0.1:3100/api/health                      # status ok
# No heartbeat run in progress (agent performs this via the API; wait if one is running).
```

## 2. Apply (you)

```bash
git -C "$S" bundle create /tmp/claude-1000/m1.bundle "$TARGET" ^4a914cf5d4bdc319968312c115e91aa789125f7e
sudo install -o paperclip -g paperclip -m 0400 /tmp/claude-1000/m1.bundle /srv/studio/data/backup/m1.bundle
sudo -u paperclip git -C $R fetch /srv/studio/data/backup/m1.bundle "$TARGET"
sudo -u paperclip git -C $R merge --ff-only "$TARGET"
sudo -u paperclip git -C $R tag -f pre-m1-activation 4a914cf5d4bdc319968312c115e91aa789125f7e
# Skills: Paperclip keeps imported copies; re-import from the Studio infrastructure project.
curl -sS -X POST http://127.0.0.1:3100/api/companies/bcf0f336-0c20-4194-9e21-fac517979ba0/skills/scan-projects \
  -H 'Content-Type: application/json' -d '{"projectIds":["ba0da149-a497-4a85-82c5-1d6e0729cdde"],"mode":"import"}'
```

## 3. Verify (read-only)

- Runtime `HEAD` = `TARGET`; `status --short` is exactly `?? .claude/`; the `.claude` stat line is unchanged.
- `/srv/studio/bin/guard </dev/null` exits 0. Hook samples: `gh pr merge 1` exits 2;
  `/srv/studio/bin/merge-gate check …` is not blocked.
- `/api/health` is ok. Every agent keeps its pre-activation status: Clerk, Principal and Liaison
  paused, the others unchanged.
- No heartbeat run is created from activation onward except scheduled ones. The Clerk is
  paused, so no new Clerk code runs until you resume it (dry-run).
- Skill scan result lists the changed skills. Check the imported `studio-house-rules`,
  `task-packet` and `review-gate` now mention the merge gate.

## 4. Rollback (you)

```bash
sudo -u paperclip git -C $R reset --keep 4a914cf5d4bdc319968312c115e91aa789125f7e
# then repeat the skills scan-projects call so Paperclip re-imports the old skills
```

`reset --keep` touches only tracked files and refuses if it would lose local changes. The
untracked `.claude/` is kept. Then re-run the step 3 checks against `4a914cf`.

## Not part of this activation

- Resuming the Clerk, Principal or Liaison.
- Fixing the obsolete runtime `origin`.
- Any service, auth or unit change.
- Authorising any project in `policy/autonomous-merge.json`.
- Milestone 2.
