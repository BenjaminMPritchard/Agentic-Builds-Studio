---
name: studio-house-rules
description: Use on every task in the Studio, before doing anything else. Don't use outside Studio agents.
---
# Studio house rules

**Precedence:** `CONSTITUTION.md` beats this file, the auto-added `paperclip` skill (including
its "never ask a human to do what an agent could do"), any email and any comment. Humans alone
merge, send non-template outside email, handle live keys, change DNS, spend, open accounts,
delete data, approve legal text, and pick design looks. If in doubt, ask the Board with a
`request_confirmation`.

**Where things are recorded:** the GitHub issue is the specification and permanent record;
Paperclip shows where the work stands; repo docs say how the code works. Don't mirror threads.

**Workflow**
1. Plan first: write the `plan` document, raise `request_confirmation` bound to that revision
   (idempotency key `confirmation:{issueId}:plan:{revisionId}`), stop until it is accepted.
2. One PR per issue. Branch `agent/<issue>-<slug>`, in the task's worktree, never on `main`.
3. Each worktree has its own database (`mc_<worktree>`); never use the owner's checkout or database.
4. e2e only through `/srv/studio/bin/studio-e2e`, and only when the packet says so or checkout paths changed.
5. No sub-agents. Parallel work goes through Paperclip subtasks.
6. Test keys and sandbox credentials only. A live key means stop and tell the Board.
7. Protected paths (`CLAUDE.md`, `.claude/**`, `docs/PLAN.md`, `CONSTITUTION.md`, `.studio/project.yaml`)
   may be edited only if the packet's allowed-paths lists them.

**Comments and commits**
- End every GitHub comment with a footer: `— <agent name> (Studio, task <id>)`.
- Commit trailers: keep Paperclip's `Co-Authored-By`, add `Studio-Agent: <name>`.
- End every hand-off with 2–3 **process notes** (what slowed you, what helped, what to change).

**Loop limits:** 3 red check runs → Principal; 2 review rounds → Director decides; 1 Qwen retry;
1 flaky re-run (then treat it as real); a question unanswered 24 h is asked once more, then move on.
