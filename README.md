# studio-company

The AI company infrastructure for building client websites, run on [Paperclip](https://github.com/paperclipai/paperclip).
Design and reasoning: `docs/paperclip/v1-setup-guide.md` and `findings.md` in the Mothers repo, branch
`claude/mothers-website-paperclip-design-it0ugo`. Rules: [`CONSTITUTION.md`](CONSTITUTION.md).

```
You (Board) → Paperclip web UI → Director → Principal / Builder-1/2 / Liaison / Worker (Qwen) / Clerk (scripts)
                                   ├ Recorder (milestones)   └ Architect (end of project)
Projects: Mothers Carpentry (first). GitHub is the engineering source of truth; Paperclip shows work state.
```

This repo is generic machinery. A project adds a Paperclip project and a `.studio/project.yaml`
(template: `templates/project.yaml`; Mothers: `projects/mothers-carpentry/project.yaml`), never new agents.

## What's here

| Path | What |
|---|---|
| `CONSTITUTION.md` | Human-only rulebook (CODEOWNERS: Benjamin) |
| `agents/<name>/` | `AGENTS.md`, `HEARTBEAT.md`, `TOOLS.md` per agent (Paperclip "External" instructions) |
| `skills/` | 7 Studio skills + `architect-review` |
| `claude/` | Shared `settings.json` (deny rules + guard hooks) and per-agent effort caps |
| `bin/guard` | PreToolUse hook: blocks main/force pushes, merges, live keys, protected paths, unapproved email, DNS, Paperclip config changes, dropping non-worktree databases, direct e2e |
| `bin/clerk` | Scripts-only coordinator: GitHub→Paperclip sync, merge/unblock gates, plan gate, pacer, loop limits, digest, log, weekly backup |
| `bin/qwen-run`, `qwen/` | Worker: Ollama + JSON schema + checks; 13 jobs, golden sets, `--score` |
| `bin/studio-e2e`, `worktree-setup/cleanup`, `pacer`, `install` | e2e lock, per-worktree databases, heavy-run pacing, deploy |
| `package/` | Paperclip configuration payloads (agents, routines, policies, budgets) |
| `projects/`, `playbook/`, `upgrades/` | Recorder and Architect output |
| `deploy/paperclip.service` | systemd user unit for Paperclip |

## Director model: events, not a loop

The Director has no timer. The Clerk (every 10 min, no LLM) writes a ≤1,500-token `digest` on the
"Director inbox" issue and wakes the Director with `--force-fresh-session` only when something needs
a decision, and only once per distinct situation.

## Test (no Paperclip, GitHub or Claude needed)

```bash
python -m unittest discover -s tests -t .      # ~30 tests, ~15 s; stdlib only
bin/qwen-run --score                           # needs Ollama + qwen3.5:4b; ~5 min; rewrites qwen/enabled.json
```

Tests use a fake Paperclip API and a fake Ollama (`tests/fakes.py`).

## Deploy (follow the guide's parts in order)

1. **Guide Part 2** (you): `paperclip` Linux user, `/srv/studio`, tools, Claude Code + `claude setup-token`, Ollama env, GitHub branch protection and three fine-grained tokens. Nothing here changes your system.
2. Clone to `/srv/studio/company`, then `bin/install` (dry run) and `bin/install --apply`.
3. **Guide Part 3**: `npx paperclipai onboard --yes`; `deploy/paperclip.service`.
4. **Guide Part 5 in the Paperclip web page**: company "Studio", secrets (test keys only), agents from `package/payloads/agent-*.json`, budgets, External instructions, `skills:sync`, routines. Click Test Environment on each.
5. **Guide Part 6**: Mothers project; open the first small PR adding `.studio/project.yaml`; create the work items in `projects/mothers-carpentry/work-items.md`.
6. **Guide Part 8**: 24-hour side-by-side with `CLERK_DRY_RUN=1`, then the W2 pilot, then cutover.

### Paperclip install notes (found during setup, 2026-09-26)

- `sudo -iu paperclip bash -c '...'` expands `$vars` in the login shell first; put multi-step checks in a script file and run `sudo -u paperclip bash file.sh`.
- `npx paperclipai onboard --yes` can fail to start with `Postgres init script exited with code 127`:
  the bundled embedded Postgres needs `libicuuc.so.60` symlinks that its `postinstall` did not create.
  Fix: `cd ~/.npm/_npx/*/node_modules/@embedded-postgres/linux-x64 && node scripts/hydrate-symlinks.js` as the `paperclip` user, then `npx paperclipai run`.
- Doctor reports no usable systemd *user* manager for `paperclip`, so `deploy/paperclip.service` may need to be a system unit (`User=paperclip`) instead.
- A leftover embedded Postgres from earlier experiments can hold port 54329; Paperclip moves to the next free port.

Run `bin/qwen-run --score` on the target machine and read `qwen/enabled.json` before relying on the Worker.

## Open items (marked `TODO(check)` in the code)

Every Paperclip endpoint or field the guide itself lists as unverified is isolated in `lib/paperclip.py`
(issue/document/comment/run list paths), `bin/guard` (`CONFIRMATION_PATH`), `lib/pacer.py` (usage-limit
error text and reset time), `package/payloads` (worktree policy fields, instructions/skills keys, routine
command). Verify against the running instance (guide §10), fix the one line, re-run the tests' fakes.
Also: writing `.studio-allowed-paths` from a task packet into a worktree is not automated yet: until it is,
protected-path edits need `STUDIO_ALLOWED_PATHS` set by hand or the Board doing the edit.
