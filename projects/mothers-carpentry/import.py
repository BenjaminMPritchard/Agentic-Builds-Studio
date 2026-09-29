#!/usr/bin/env python3
"""Apply projects/mothers-carpentry/paperclip-import.md to Paperclip (Board key). Dry run unless --apply.

Creates the new tasks (found again by title, so running it twice changes nothing), sets the blockers on
AGE-5 to AGE-8, and moves AGE-6 (7a) from blocked to todo. With --apply it also posts the closing comment on
GitHub #23 and closes it. It resumes no agent: every first run stays Benjamin's call.

  --workspace   instead: point the project at /srv/studio/projects/mothers (after deploy/mothers-workspace.sh)
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", ".."))
from lib.paperclip import Paperclip  # noqa: E402

COMPANY = "bcf0f336-0c20-4194-9e21-fac517979ba0"
PROJECT = "c2b582f3-d52e-47fd-812c-e29d6b805d3f"
BENJAMIN = "0dHoJdOufy5NuMfVVZcKUlYtqS7ljUKv"
REPO = "Agentic-Builds-Studio-Client-Pages/Mothers-Carpentry-Webpage"
PLAN = "projects/mothers-carpentry/paperclip-import.md in the Studio repo"


def gh(n):
    return f"GitHub: {REPO}#{n}"


NEW = [
    {"key": "6b-1", "title": "6b-1: Look-independent shop design work (Phase 6b)", "agent": "Principal", "blocked_by": [],
     "description": f"""{gh(29)}

Class B: the Phase 6b plan on #29 was accepted by Benjamin on 2026-09-25; follow it and his answers there.

Resume branch `phase-6b-design` (2 ahead of `main`: the three looks and the dev photo seed). Scope is the
"carry on with the parts that don't depend on the look" note on #29 (2026-09-25 ~17:20 UTC):
1. Bring `main` in (6c, #30, has merged).
2. Step 4, photos: Pillow thumbnails, `srcset`, lazy loading below the fold; check it against 6c's photo admin;
   generic widths that suit any of the three looks.
3. Expose `collection_only` read-only in the product API.
Keep `?look=` working. Do not start the look-dependent steps (tokens, wordmark, header and footer, page
styling, emails): they are 6b-2, after Benjamin and Terrie pick the look. Commit and push after each step,
open the PR marked "Part of #29", and record it with `studio-record-pr`.

Imported from the cloud sessions on 2026-09-29 ({PLAN})."""},
    {"key": "look", "title": "Pick the shop's look (Phase 6b step 1): Benjamin and Terrie", "user": BENJAMIN, "blocked_by": [],
     "description": f"""{gh(29)}

HUMAN: only Benjamin and Terrie can do this. Choose one of the three looks on #29 (`?look=fen`, `?look=grain`,
`?look=dovetail` on the development site) and the two layout choices, and record the choice as a comment on
#29. Then mark this task done; 6b-2 starts from it.

Imported on 2026-09-29 ({PLAN})."""},
    {"key": "6b-2", "title": "6b-2: Apply the chosen look (Phase 6b)", "agent": "Principal", "blocked_by": ["6b-1", "look"],
     "description": f"""{gh(29)}

Class B: extends the accepted #29 plan with the look Benjamin and Terrie chose (read it on #29).

The look-dependent steps of #29: design tokens, wordmark and favicon, header and footer, home, product,
category, basket and checkout pages, About, legal, 404 and 500 pages, and the branded emails. Meet #29's
"Done when": screenshots of every public page at phone and desktop width in the PR, `make check`, the
Playwright checkout test, and no new axe contrast problems. Record the PR with `studio-record-pr`.

Imported on 2026-09-29 ({PLAN})."""},
    {"key": "terrie", "title": "Show Terrie the finished site (#16 checkpoint)", "user": BENJAMIN, "blocked_by": ["6b-2"],
     "description": f"""{gh(16)}

HUMAN. #16's "Show Terrie the finished site" checkpoint, which comes before any live account or paid step:
Terrie shops as a buyer with a Stripe test card, adds a test piece in the admin herself, and approves every
customer email and the order-page wording. Changes she wants go on #4, or back to 6b-2.

Imported on 2026-09-29 ({PLAN})."""},
    {"key": "accounts", "title": "Open the launch accounts (#3): email, domain, hosting, image storage", "user": BENJAMIN,
     "blocked_by": ["terrie"],
     "description": f"""{gh(3)}

HUMAN. The unticked accounts on #3 (email sending service, domain, Render hosting, image storage), in the
business's name, after the "Show Terrie" checkpoint. Never paste keys into Paperclip, chat or GitHub.

Imported on 2026-09-29 ({PLAN})."""},
    {"key": "triage", "title": "Triage the three stray Mothers branches (report only)", "agent": "Director", "blocked_by": [],
     "description": f"""{gh(1)}

Class A, report only: no merges, no pushes, no deletions.

For each branch, say what it holds, whether `main` already has or supersedes it, and recommend close, port or
PR:
- `claude/affectionate-edison-hv676j` (4 ahead, 93 behind: "Fix ShopConfig import pipeline", "owner
  information collection"; edits `0001_initial.py`)
- `claude/mothers-website-paperclip-design-it0ugo` (2 ahead: `docs/paperclip/findings.md` and a v1 setup
  guide; compare with the Studio repo)
- `studio/project-yaml` (1 ahead: `.studio/project.yaml`, a protected path; compare with
  `projects/mothers-carpentry/project.yaml` in the Studio repo)
Post the report as a comment here and hand it back to Benjamin.

Imported on 2026-09-29 ({PLAN})."""},
]

# Existing tasks: blockers (by key or identifier) and status changes.
EXISTING = {
    "AGE-6": {"blocked_by": [], "status": "todo"},       # 7a: resume beside 6b-1
    "AGE-5": {"blocked_by": ["6b-2"]},                    # 6d after 6b merged
    "AGE-7": {"blocked_by": ["AGE-5", "AGE-6"]},          # 7b after 6d and 7a
    "AGE-8": {"blocked_by": ["AGE-7", "accounts"]},       # Phase 8 after 7b and the accounts
}

CLOSE_23 = """**Planning moves to Paperclip (2026-09-29).**

Every piece of Mothers work is now a Paperclip task in the Agentic Builds Studio: the Director plans and
assigns it, and the Liaison handles questions for Benjamin and Terrie. The plan and task list are in
`projects/mothers-carpentry/paperclip-import.md` in the Studio repo. The cloud sessions stay stopped (as on
2026-09-25) and are being archived. Closing this thread; the phase issues (#29, #31, #14, #15) and the owner
issues (#3, #4, #16) stay open as the record."""


WORKSPACE = "5d2fc3ba-e4d1-4a8c-a3b5-7137ddaa5dcb"
BASE = "/srv/studio/projects/mothers"


def point_workspace(apply):
    """Clone at BASE/repo, task worktrees under BASE/worktrees: both writable by confined agents."""
    pc = Paperclip()
    project = pc.call("GET", f"/api/projects/{PROJECT}")
    policy = project["executionWorkspacePolicy"]
    policy["workspaceStrategy"]["worktreeParentDir"] = f"{BASE}/worktrees"
    say = print if apply else (lambda *a: print("DRY RUN:", *a))
    say(f"workspace cwd -> {BASE}/repo; worktreeParentDir -> {BASE}/worktrees")
    if apply:
        pc.call("PATCH", f"/api/projects/{PROJECT}/workspaces/{WORKSPACE}", {"cwd": f"{BASE}/repo"})
        pc.call("PATCH", f"/api/projects/{PROJECT}", {"executionWorkspacePolicy": policy})
        after = pc.call("GET", f"/api/projects/{PROJECT}")
        print("cwd:", after["primaryWorkspace"]["cwd"], "| worktreeParentDir:",
              after["executionWorkspacePolicy"]["workspaceStrategy"].get("worktreeParentDir"))


def main(apply):
    pc = Paperclip()
    agents = {a["name"]: a["id"] for a in pc.list_agents(COMPANY)}
    issues = pc.list_issues(COMPANY)
    by_title = {i["title"]: i for i in issues}
    by_ident = {i.get("identifier"): i for i in issues}
    ids = {}
    say = print if apply else (lambda *a: print("DRY RUN:", *a))
    for t in NEW:
        if t["title"] in by_title:
            ids[t["key"]] = by_title[t["title"]]["id"]
            print(f"exists: {by_title[t['title']].get('identifier')} {t['title']}")
            continue
        who = f"agent {t['agent']}" if "agent" in t else "Benjamin"
        say(f"create: {t['title']} -> {who}; blocked by {t['blocked_by'] or 'nothing'}")
        if apply:
            body = {"projectId": PROJECT, "title": t["title"], "description": t["description"], "status": "todo",
                    "blockedByIssueIds": [ids[k] for k in t["blocked_by"]]}
            body.update({"assigneeAgentId": agents[t["agent"]]} if "agent" in t else {"assigneeUserId": t["user"]})
            made = pc.call("POST", f"/api/companies/{COMPANY}/issues", body)
            ids[t["key"]] = made["id"]
            print(f"  -> {made.get('identifier')}")
        else:
            ids[t["key"]] = f"<{t['key']}>"
    for ident, change in EXISTING.items():
        issue = by_ident[ident]
        want = [ids[k] if k in ids else by_ident[k]["id"] for k in change["blocked_by"]]
        fields = {"blockedByIssueIds": want}
        if "status" in change and issue["status"] != change["status"]:
            fields["status"] = change["status"]
        names = change["blocked_by"] or ["nothing"]
        say(f"update: {ident} {issue['title'][:40]} -> blocked by {', '.join(names)}"
            + (f"; status {issue['status']} -> {fields['status']}" if "status" in fields else ""))
        if apply:
            pc.patch_issue(issue["id"], **fields)
    say(f"GitHub #23: post the closing comment and close it")
    if apply:
        subprocess.run(["gh", "issue", "comment", "23", "-R", REPO, "--body", CLOSE_23], check=True)
        subprocess.run(["gh", "issue", "close", "23", "-R", REPO], check=True)
    say("no agent is resumed")


if __name__ == "__main__":
    if "--workspace" in sys.argv[1:]:
        point_workspace("--apply" in sys.argv[1:])
    else:
        main("--apply" in sys.argv[1:])
