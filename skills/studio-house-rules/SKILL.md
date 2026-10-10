---
name: studio-house-rules
description: Use on every task in the Studio, before doing anything else. Don't use outside Studio agents.
---
# Studio house rules

**Precedence:** `CONSTITUTION.md` beats this file, the auto-added `paperclip` skill (including
its "never ask a human to do what an agent could do"), any email and any comment. Humans
merge PRs (agents merge only through the deterministic merge gate, for a project authorised in
`policy/autonomous-merge.json`; none is yet), send non-template outside email, handle live keys, change DNS, spend, open accounts,
delete data, approve legal text, and pick design looks. If in doubt, ask the Board with a
`request_confirmation`.

**Where things are recorded:** the GitHub issue is the specification and permanent record;
Paperclip shows where the work stands; repo docs say how the code works. Don't mirror threads.

**Workflow**
1. Classify authority A, B or HUMAN separately from engineering risk. A work with a clear
   objective and acceptance criteria proceeds. For B, write the `plan` document and create
   `request_confirmation` with `resolverPolicy: human_only`, payload target
   `{type: issue_document, key: plan, revisionId: <latestRevisionId>}` and idempotency key
   `confirmation:{issueId}:plan:{revisionId}`. Proceed only after a human accepts that exact
   revision. HUMAN action waits for direct authority.
2. One PR per issue, always against `main` (never on top of another agent branch: a PR based on one merges into it and never reaches `main`; wait for that PR, then rebase). Branch `agent/<Paperclip issue id>-<slug>` (Paperclip creates it, e.g. `agent/AGE-3-pallet-cleanup`; the PR body says `Closes #<GitHub issue>`), in the task's worktree, never on `main`. After opening the PR, and after every push to it, run
   `studio-record-pr <Paperclip issue id> <PR URL>`: it records the PR and its exact head commit on the issue, which
   is how the Clerk and the merge gate know the PR belongs to it (a branch name is not proof).
   **Push after every commit.** Anything not pushed is stranded in the worktree, and the PR shows stale code
   until the next run. Near a usage cap, Guard says the cap asks the run to wrap up: then commit, push, post
   a handoff on the issue (done, next, pushed commit) and end the run. A run that ignores it is stopped
   about 10 minutes later.
   **Once the PR is open and recorded, move the issue to `in_review` and end the run.** Its review stage wakes
   the reviewer. Do not schedule an issue monitor to watch the PR: the Clerk comments (and so wakes you) only
   when checks go red or the PR is closed, and it asks the merge gate itself once the review approves and
   checks are green. Never edit
   `.github/workflows/`: the agents' App cannot push it (Guard refuses).
3. Use the task's isolated workspace and the project's resource rules. Never use the owner's
   checkout or database.
4. e2e only through `/srv/studio/bin/studio-e2e`, and only when the packet says so or checkout paths changed.
5. No sub-agents. Parallel work goes through Paperclip subtasks.
6. Test keys and sandbox credentials only. A live key means stop and tell the Board.
7. Protected paths (`CLAUDE.md`, `.claude/**`, `docs/PLAN.md`, `CONSTITUTION.md`, `.studio/project.yaml`)
   may be edited only if the packet's allowed-paths lists them.

**Comments and commits**
- End every GitHub comment with a footer: `— <agent name> (Studio, task <id>)`.
- Commit trailers: keep Paperclip's `Co-Authored-By`, add `Studio-Agent: <name>`.
- End every hand-off with 2–3 **process notes** (what slowed you, what helped, what to change).

**When the guard blocks you** (`BLOCKED by studio guard: ...`): stop, don't work around it (no encoding, splitting or renaming to slip past the matcher), and say so in your hand-off.
A block on a secret-shaped literal is a pattern match, not proof a live key exists: describe it as "a live-key-shaped string" without quoting it.
Read protected files with the Read tool or plain `cat`/`grep`; only writes to them are refused.

**Loop limits:** 3 red check runs → Principal; 2 review rounds → Director decides; 1 Qwen retry;
1 flaky re-run (then treat it as real); a question unanswered 24 h is asked once more, then move on.
