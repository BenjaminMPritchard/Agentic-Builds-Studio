# Bringing the Mothers work into Paperclip (plan for Benjamin's review)

Status: **proposal, nothing applied.** Inventory read on 2026-09-29 from GitHub
(`Agentic-Builds-Studio-Client-Pages/Mothers-Carpentry-Webpage`) and Paperclip. Replaces the 6b note in
`work-items.md` ("6b stays in its cloud session"): every piece of Mothers work moves to Paperclip, and the
Director plans it instead of the cloud planning thread (#23).

## What exists today

**Cloud sessions.** All stopped on Benjamin's instruction of 2026-09-25 ~19:15 UTC (#23's last comment): the
hourly Routine is deleted and #38, 6b, 6d and Phase 7 were interrupted. Nothing wakes them. Their work is on
the branches below; nothing else of value lives only in a session.

**Open GitHub issues:** #1 roadmap, #3 owner accounts, #4 owner decisions (every row answered), #14 Phase 7,
#15 Phase 8, #16 owner pre-launch tasks, #17 later ideas, #23 planning assistant, #29 Phase 6b, #31 Phase 6d.
No open PRs. 6c (#30), #12, #13, #28, #34 and #38 are merged.

**Branches with unmerged work** (everything else is 0 ahead):

| Branch | Ahead / behind `main` | What it holds |
| --- | --- | --- |
| `phase-6b-design` | 2 / 19 | Step 1 of 6b: three looks (`?look=fen`, `grain`, `dovetail`) on shared tokens, and a dev-only CC0 photo seed |
| `agent/14-phase-7a` | 3 / 7 | Phase 7a steps 1–3: rate limits and shared cache, CSRF test, live-site security settings (6 steps to go; plan approved on #14) |
| `claude/affectionate-edison-hv676j` | 4 / 93 | "Fix ShopConfig import pipeline" and "owner information collection"; edits `0001_initial.py`, so it predates most of the build |
| `claude/mothers-website-paperclip-design-it0ugo` | 2 / 7 | `docs/paperclip/findings.md` and a v1 setup guide: Studio material, not site code |
| `studio/project-yaml` | 1 / 7 | `.studio/project.yaml` (a protected path in the site repo) |

**Paperclip today** (project "Mothers Carpentry (Driftwood & Dovetail)"): AGE-5 6d (Builder-1, backlog),
AGE-6 7a (Principal, blocked), AGE-7 7b (Principal, backlog), AGE-8 Phase 8 (Builder-1, backlog), AGE-3
Director inbox. None has formal blockers, and none records a PR as a work product.

## Proposed tasks

Assignments follow each GitHub issue's "Session settings" until the routing table exists (6b says Opus →
Principal; 6d says Sonnet → Builder-1). **B** = Benjamin approves the plan revision before building;
**HUMAN** = only Benjamin (or Terrie through him) can do it.

| Task | GitHub | Assignee | Class | Blocked by | Notes |
| --- | --- | --- | --- | --- | --- |
| **6b-1** Look-independent 6b work | #29 | Principal | B (plan exists and was accepted on #29) | — | Resume `phase-6b-design`: bring `main` in; step 4 photos (Pillow thumbnails, `srcset`, lazy loading, checked against 6c's photo admin); expose `collection_only` read-only in the product API. Keep `?look=` working. The 25 Sep note on #29 is the scope |
| **Pick the look** | #29 step 1 | Benjamin | HUMAN | — | Benjamin and Terrie choose one of the three looks and the two layout choices; record it as a comment on #29 |
| **6b-2** Apply the chosen look | #29 | Principal | B | 6b-1, Pick the look | Tokens, wordmark, header/footer, pages, emails, 404/500, screenshots; #29's "Done when" |
| AGE-6 **7a** (existing) | #14 | Principal | B (approved) | — | Resume `agent/14-phase-7a`: steps 4–9. Security settings do not depend on the look, so this can run beside 6b-1 |
| AGE-5 **6d** (existing) | #31 | Builder-1 | B | 6b-2 | #31 depends on 6b merged |
| AGE-7 **7b** (existing) | #14 | Principal | B | AGE-5, AGE-6 | Phase 7 depends on the design and SEO phases |
| **Show Terrie** | #16 | Benjamin | HUMAN | 6b-2 | #16's checkpoint: before any live account or paid step |
| **Open the launch accounts** | #3 | Benjamin | HUMAN | Show Terrie | Email service, domain, hosting (Render), image storage |
| AGE-8 **Phase 8** (existing) | #15 | Builder-1 | B | AGE-7, Open the launch accounts | Never switches to live keys |
| **Branch triage** | — | Director | A (report only) | — | For the three stray branches: say what each holds, whether it is superseded, and recommend close / port / PR. No merges |

Every task description carries its `GitHub: Agentic-Builds-Studio-Client-Pages/Mothers-Carpentry-Webpage#N`
line; blockers are set with Paperclip's `blockedByIssueIds`; agents record PRs with `studio-record-pr`.

**Not imported:** #1 (roadmap; the Director reads it), #4 (answered; agents read it), #17 (later ideas).
**#23** gets a closing comment pointing to Paperclip; the Director and the Liaison take over its jobs.

## Before any Mothers task can run (host step, Benjamin)

Project tasks run in a Paperclip-managed git worktree. Today the project's clone and its worktrees live under
`/home/paperclip`, which confined agents (`studio-agent`) cannot enter, and a commit in a worktree also writes
into the main clone's `.git`. So a run would fail at once. Fix, prepared as a separate PR with a script and a
test run:
- keep the project's clone at `/srv/studio/projects/mothers/repo` and its worktrees at
  `/srv/studio/projects/mothers/worktrees` (owner `paperclip`, group `studio`, setgid, default ACLs so both
  users can write), and point the project workspace (`cwd`) and `worktreeParentDir` there;
- let `studio-agent`'s git trust that folder (`safe.directory`);
- check `/srv/studio/bin/worktree-setup` and `worktree-cleanup` against the new paths.

## Capacity

With the caps active, the studio may use 12 points of each Claude five-hour window; each run is estimated at
3 points until measured, plus a 1-point margin, so about **three runs per window** at first. 6b-1 and 7a can
run in parallel; the estimates tighten after three measured runs per agent. The Worker (local Qwen) does not
count.

## Decisions for Benjamin

1. Split 6b as above (6b-1 now, the look with you and Terrie, 6b-2 after)?
2. Resume 7a (AGE-6) beside 6b-1?
3. Assignments as the GitHub issues say (Principal for 6b and 7, Builder-1 for 6d and 8) until the routing table?
4. Director triages the three stray branches (report only)?
5. Close #23 with a pointer to Paperclip, and archive the cloud sessions yourself?

## Applying it (after approval)

A script creates the new tasks, updates AGE-5 to AGE-8 and sets the blockers through the Board API, printing a
dry run first; you review the dry run, then it applies. No agent is resumed by the import; each first run is
still your call.
