"""Deterministic autonomous merge gate.

`evaluate(policy, request, evidence)` is pure: it returns the list of reasons the merge is refused
(empty means every condition was proven). `collect` reads the evidence from Paperclip and GitHub;
`run` collects, evaluates, records the decision and, only when asked and allowed, merges with
GitHub's `--match-head-commit` so a head that moved after evaluation is rejected server-side.

Authority comes from Paperclip (task packet, plan confirmations, review state) and from the
human-owned `policy/autonomous-merge.json`. Engineering evidence comes from GitHub. No model
takes part in the decision. Anything missing, malformed or ambiguous refuses.
"""
import fnmatch
import functools
import json
import os
import re
import subprocess
import time
from datetime import datetime

from lib import github_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_PATH = os.path.join(ROOT, "policy", "autonomous-merge.json")

# Never merged autonomously in any project, whatever its policy says.
ALWAYS_PROTECTED = ["CONSTITUTION.md", "CLAUDE.md", ".claude/**", "docs/PLAN.md", ".studio/project.yaml",
                    ".studio-allowed-paths", ".github/**", "CODEOWNERS", "policy/**"]
BLOCKING_LABELS = {"needs-human", "needs-board", "b2", "deviation", "do-not-merge"}
MERGE_METHODS = {"squash", "merge", "rebase"}
PASSING = {"success", "neutral", "skipped"}
AUTHORITY = re.compile(r"^\s*(?:[-*]\s*)?\*\*Authority:\*\*\s*(.*?)\s*$", re.M)
RISK = re.compile(r"^\s*(?:[-*]\s*)?\*\*Engineering risk:\*\*\s*(.*?)\s*$", re.M)
SCOPE = re.compile(r"^\s*(?:[-*]\s*)?\*\*Scope paths:\*\*\s*(.*?)\s*$", re.M)
PR_URL = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+)/pull/(\d+)/?$")


def match(path, pattern):
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-2])
    return fnmatch.fnmatch(path, pattern)


def load_policy(path=POLICY_PATH):
    with open(path) as f:
        return json.load(f)


def project_policy(policy, project_id):
    """The project's merge policy, or a reason it has none. Validates shape; fails closed."""
    if not isinstance(policy, dict) or policy.get("version") != 1 or not isinstance(policy.get("projects"), dict):
        return None, "merge policy is missing or malformed"
    p = policy["projects"].get(project_id or "")
    if not isinstance(p, dict) or p.get("enabled") is not True:
        return None, "autonomous merge is not authorised for this project"
    for key, kind in (("repo", str), ("base_branch", str), ("merge_method", str), ("authority_classes", list),
                      ("required_checks", list), ("required_approvals", int), ("trusted_reviewers", list),
                      ("protected_paths", list), ("authorised_by", str), ("authorised_on", str)):
        if not isinstance(p.get(key), kind) or isinstance(p.get(key), bool):
            return None, f"project merge policy field '{key}' is missing or malformed"
    if p["merge_method"] not in MERGE_METHODS or not p["required_checks"] \
            or not set(p["authority_classes"]) <= {"A", "B"} or p["required_approvals"] < 0:
        return None, "project merge policy has invalid values"
    if "mergeable_paths" in p and not isinstance(p["mergeable_paths"], list):
        return None, "project merge policy field 'mergeable_paths' is malformed"
    return p, None


def single(pattern, text, what):
    found = pattern.findall(text or "")
    if len(found) != 1:
        return None, f"task packet must state {what} exactly once (found {len(found)})"
    return found[0].strip(), None


INACTIVE_PRODUCT = {"closed", "archived", "failed", "merged"}


def linked_prs(issue):
    """(repo, number, head branch) for each live GitHub pull-request work product on the issue.
    Metadata and URL must agree; a product that cannot be read counts as ambiguous (None)."""
    out = []
    for w in issue.get("workProducts") or []:
        if not isinstance(w, dict) or w.get("type") != "pull_request" or w.get("status") in INACTIVE_PRODUCT:
            continue
        meta = w.get("metadata") or {}
        m = PR_URL.match(w.get("url") or "")
        key = (str(meta.get("repo") or "").lower(), meta.get("number"))
        if w.get("provider") != "github" or not m or key != (m.group(1).lower(), int(m.group(2))):
            out.append(None)
        else:
            out.append((*key, meta.get("headRef")))
    return out


def recorded_commit(issue, repo, sha, branch):
    """True if the issue records this exact head as a commit work product."""
    return any(isinstance(w, dict) and w.get("type") == "commit" and w.get("provider") == "github"
               and str((w.get("metadata") or {}).get("repo") or "").lower() == repo
               and (w.get("metadata") or {}).get("sha") == sha
               and (w.get("metadata") or {}).get("branch") == branch
               for w in issue.get("workProducts") or [])


def plan_approved(plan, interactions):
    """True only for an accepted human-only confirmation, resolved by a user, on the current plan revision."""
    revision = plan.get("latestRevisionId") if isinstance(plan, dict) else None
    if not revision:
        return False
    return any(i.get("kind") == "request_confirmation" and i.get("status") == "accepted"
               and i.get("effectiveResolverPolicy") == "human_only"
               and i.get("resolvedByUserId") and not i.get("resolvedByAgentId")
               and ((i.get("payload") or {}).get("target") or {}).get("type") == "issue_document"
               and ((i.get("payload") or {}).get("target") or {}).get("key") == "plan"
               and ((i.get("payload") or {}).get("target") or {}).get("revisionId") == revision
               for i in interactions)


def _when(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def paperclip_approvers(issue, activity, repo, sha, branch):
    """Actors whose Paperclip review decisions approve this exact head, and reasons to refuse.

    The author is executionState.returnAssignee (the current assignee changes to the reviewer).
    A decision is an activity entry whose executionState carries a new lastDecisionId. It counts only
    if it approves, was made by someone other than the author, and came after the head commit was first
    recorded on the issue. Any changes-requested decision after that point refuses."""
    if not isinstance(activity, list):
        return set(), ["could not read the issue's activity"]
    author = ((issue.get("executionState") or {}).get("returnAssignee") or {}).get("agentId")
    recorded = [_when(w.get("createdAt")) for w in issue.get("workProducts") or []
                if isinstance(w, dict) and w.get("type") == "commit" and w.get("provider") == "github"
                and str((w.get("metadata") or {}).get("repo") or "").lower() == repo
                and (w.get("metadata") or {}).get("sha") == sha and (w.get("metadata") or {}).get("branch") == branch]
    recorded = [t for t in recorded if t]
    if not recorded:
        return set(), []
    head_time, previous, approvers, reasons = min(recorded), None, set(), []
    for a in sorted((a for a in activity if isinstance(a, dict) and _when(a.get("createdAt"))),
                    key=lambda a: _when(a["createdAt"])):
        state = (a.get("details") or {}).get("executionState")
        if not isinstance(state, dict) or not state.get("lastDecisionId") or state["lastDecisionId"] == previous:
            continue
        previous = state["lastDecisionId"]
        if _when(a["createdAt"]) <= head_time:
            continue
        if state.get("lastDecisionOutcome") == "changes_requested":
            reasons.append("Paperclip review requested changes after the head was recorded")
        elif state.get("lastDecisionOutcome") == "approved" and a.get("actorType") in ("agent", "user") \
                and a.get("actorId") and author and a["actorId"] != author:
            approvers.add(a["actorId"])
    return approvers, reasons


def paperclip_review_complete(issue):
    """No review policy, or every stage completed with an approving last decision."""
    policy = issue.get("executionPolicy")
    if not policy:
        return True
    stages = policy.get("stages") if isinstance(policy, dict) else None
    if not isinstance(stages, list):
        return False
    if not stages:
        return True
    state = issue.get("executionState") or {}
    done = set(state.get("completedStageIds") or [])
    return state.get("status") == "completed" and state.get("lastDecisionOutcome") == "approved" \
        and all(isinstance(s, dict) and s.get("id") in done for s in stages)


def evaluate(policy, request, ev):
    """Reasons to refuse. Empty list = merge allowed. `request` = {issue_id, repo, pr, head_sha}."""
    reasons = []

    def no(reason):
        reasons.append(reason)

    issue, pr = ev.get("issue") or {}, ev.get("pr") or {}
    repo, number, sha = (request.get("repo") or "").lower(), request.get("pr"), request.get("head_sha") or ""
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return ["expected head SHA must be a full 40-character commit id"]
    if not issue or issue.get("id") != request.get("issue_id"):
        return ["could not read the Paperclip issue"]
    if not pr:
        return ["could not read the pull request"]

    # Project authorisation (human-owned policy in the Studio repo).
    if issue.get("companyId") != (policy or {}).get("company_id"):
        return ["issue belongs to a different Paperclip company"]
    proj, why = project_policy(policy, issue.get("projectId"))
    if why:
        return [why]
    if proj["repo"].lower() != repo:
        return [f"repository {request.get('repo')} is not the one authorised for this project"]

    # Task authority.
    authority, why = single(AUTHORITY, issue.get("description"), "its Authority")
    if why:
        no(why)
    elif authority not in ("A", "B"):
        no(f"authority '{authority}' cannot merge autonomously")
    plan = ev.get("plan")
    interactions = ev.get("interactions")
    if not isinstance(interactions, list):
        no("could not read the issue's interactions")
        interactions = []
    if plan and authority == "A":
        no("issue has a plan document, so it is B work; its packet says A")
    if authority in ("A", "B") and authority not in proj["authority_classes"]:
        no(f"project does not authorise autonomous merge for class {authority}")
    if authority == "B":
        if not plan:
            no("B work has no plan document")
        elif not plan_approved(plan, interactions):
            no("B plan's current revision has no accepted human-only confirmation")
    if any(i.get("status") == "pending" for i in interactions):
        no("issue has an unresolved confirmation")
    risk, why = single(RISK, issue.get("description"), "its Engineering risk")
    risk = risk if risk in ("low", "medium", "high") else "high"

    # Paperclip state and linkage.
    if issue.get("status") != "in_review":
        no(f"issue status is {issue.get('status')}, not in_review")
    if any(b.get("status") != "done" for b in issue.get("blockedBy") or []):
        no("issue has unresolved blockers")
    if not paperclip_review_complete(issue):
        no("Paperclip review policy is not complete and approved")
    links = linked_prs(issue)
    if len(links) != 1 or links[0] is None or links[0][:2] != (repo, number):
        no("issue must record exactly this pull request as its only open PR work product")
    elif links[0][2] != pr.get("head_ref"):
        no("pull request branch differs from the branch recorded on the issue")
    if not recorded_commit(issue, repo, sha, pr.get("head_ref")):
        no("issue does not record the expected head SHA as a commit work product")
    identifier = issue.get("identifier") or ""
    if not identifier or not (pr.get("head_ref") or "").lower().startswith(f"agent/{identifier.lower()}-"):
        no(f"branch {pr.get('head_ref')} is not agent/{identifier}-<slug>")

    # Pull request identity and exact head.
    if (pr.get("base_repo") or "").lower() != repo or (pr.get("head_repo") or "").lower() != repo:
        no("pull request is not within the authorised repository (fork or wrong base)")
    if pr.get("number") != number:
        no("pull request number does not match")
    if pr.get("state") != "open" or pr.get("draft") or pr.get("merged"):
        no("pull request is not open and ready")
    if pr.get("base_ref") != proj["base_branch"]:
        no(f"pull request targets {pr.get('base_ref')}, not {proj['base_branch']}")
    if pr.get("head_sha") != sha:
        no("pull request head moved: it is not the expected SHA")
    if pr.get("mergeable") is not True or pr.get("mergeable_state") != "clean":
        no(f"GitHub does not report the pull request as cleanly mergeable ({pr.get('mergeable_state')})")
    labels = {str(x).lower() for x in pr.get("labels") or []}
    if labels & BLOCKING_LABELS:
        no(f"pull request is labelled {', '.join(sorted(labels & BLOCKING_LABELS))}")

    # Files: complete list, protected paths, optional allow-list, B plan scope.
    files = ev.get("files")
    if not isinstance(files, list) or not files or len(files) != pr.get("changed_files"):
        no("could not read the complete list of changed files")
        files = []
    paths = sorted({p for f in files for p in (f.get("filename"), f.get("previous_filename")) if p})
    protected = ALWAYS_PROTECTED + proj["protected_paths"]
    for p in paths:
        if any(match(p, pat) for pat in protected):
            no(f"pull request touches protected path {p}")
        if proj.get("mergeable_paths") and not any(match(p, pat) for pat in proj["mergeable_paths"]):
            no(f"{p} is outside the project's autonomously mergeable paths")
    if authority == "B" and plan:
        scope, why = single(SCOPE, plan.get("body"), "its Scope paths")
        globs = [g.strip().strip("`") for g in (scope or "").split(",") if g.strip()]
        if why or not globs:
            no("approved B plan must declare its Scope paths once")
        else:
            for p in paths:
                if not any(match(p, g) for g in globs):
                    no(f"{p} is outside the approved plan's scope (B2: needs human approval)")

    # Checks on the exact head.
    runs, statuses = ev.get("check_runs"), ev.get("statuses")
    if not isinstance(runs, list) or not isinstance(statuses, list):
        no("could not read checks for the head commit")
        runs, statuses = [], []
    for r in runs:
        if r.get("head_sha") != sha:
            no(f"check {r.get('name')} is not for the expected head")
        elif r.get("status") != "completed" or r.get("conclusion") not in PASSING:
            no(f"check {r.get('name')} is {r.get('conclusion') or r.get('status')}")
    for s in statuses:
        if s.get("state") != "success":
            no(f"status {s.get('context')} is {s.get('state')}")
    for name in proj["required_checks"]:
        ok = any(r.get("name") == name and r.get("head_sha") == sha and r.get("conclusion") == "success" for r in runs) \
            or any(s.get("context") == name and s.get("state") == "success" for s in statuses)
        if not ok:
            no(f"required check {name} has not passed on the expected head")

    # Independent review on the exact head.
    needed = proj["required_approvals"]
    if authority == "B" or risk != "low":
        needed = max(needed, 1)
    reviews = ev.get("reviews")
    if not isinstance(reviews, list):
        no("could not read reviews")
        reviews = []
    latest = {}
    for r in reviews:  # oldest first; comments and dismissals do not replace a decision
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED"):
            latest[r.get("user")] = r
    if any(r.get("state") == "CHANGES_REQUESTED" for r in latest.values()):
        no("changes were requested")
    trusted = {u.lower() for u in proj["trusted_reviewers"]}
    approvals = [u for u, r in latest.items() if r.get("state") == "APPROVED" and r.get("commit_id") == sha
                 and u and u.lower() in trusted and u.lower() != (pr.get("author") or "").lower()]
    pc_approvers, pc_reasons = paperclip_approvers(issue, ev.get("activity"), repo, sha, pr.get("head_ref"))
    reasons.extend(pc_reasons)
    have = len(approvals) + len(pc_approvers)
    if have < needed:
        no(f"needs {needed} independent approval(s) on the expected head (trusted GitHub reviewers or Paperclip "
           f"review decisions by someone other than the author, after the head was recorded); has {have}")
    return reasons


# ---- evidence collection ---------------------------------------------------------------------------

def gh_env(token):
    """Environment for gh: the gate's App token when there is one, never an inherited GITHUB_TOKEN."""
    env = dict(os.environ)
    if token:
        env.pop("GITHUB_TOKEN", None)
        env["GH_TOKEN"] = token
    return env


def gh_api(path, paginate=False, token=None):
    args = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
    if paginate:
        args[2:2] = ["--paginate", "--slurp"]
    r = subprocess.run(args, capture_output=True, text=True, timeout=60, env=gh_env(token))
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:200])
    data = json.loads(r.stdout or "null")
    if paginate:  # --slurp returns one element per page
        out = []
        for page in data:
            out.extend(page if isinstance(page, list) else page.get("check_runs", []))
        return out
    return data


def collect(pc, request, gh=gh_api):
    """Evidence for `evaluate`. Missing pieces stay None so evaluation refuses."""
    ev = {}
    issue = pc.get_issue(request["issue_id"])
    ev["issue"] = issue
    ev["plan"] = pc.get_document(issue["id"], "plan")
    ev["interactions"] = pc.interactions(issue["id"])
    ev["activity"] = pc.issue_activity(issue["id"])
    repo, n, sha = request["repo"], request["pr"], request["head_sha"]
    p = gh(f"repos/{repo}/pulls/{n}")
    ev["pr"] = {
        "number": p.get("number"), "state": p.get("state"), "draft": p.get("draft"), "merged": p.get("merged"),
        "base_repo": ((p.get("base") or {}).get("repo") or {}).get("full_name"),
        "head_repo": ((p.get("head") or {}).get("repo") or {}).get("full_name"),
        "base_ref": (p.get("base") or {}).get("ref"), "head_ref": (p.get("head") or {}).get("ref"),
        "head_sha": (p.get("head") or {}).get("sha"), "author": (p.get("user") or {}).get("login"),
        "labels": [x.get("name") for x in p.get("labels") or []],
        "mergeable": p.get("mergeable"), "mergeable_state": p.get("mergeable_state"),
        "changed_files": p.get("changed_files"),
    }
    ev["files"] = [{"filename": f.get("filename"), "previous_filename": f.get("previous_filename")}
                   for f in gh(f"repos/{repo}/pulls/{n}/files?per_page=100", paginate=True)]
    ev["check_runs"] = [{"name": r.get("name"), "head_sha": r.get("head_sha"), "status": r.get("status"),
                         "conclusion": r.get("conclusion")}
                        for r in gh(f"repos/{repo}/commits/{sha}/check-runs?filter=latest&per_page=100", paginate=True)]
    combined = gh(f"repos/{repo}/commits/{sha}/status")
    ev["statuses"] = [{"context": s.get("context"), "state": s.get("state")} for s in (combined or {}).get("statuses", [])]
    ev["reviews"] = [{"user": (r.get("user") or {}).get("login"), "state": r.get("state"), "commit_id": r.get("commit_id")}
                     for r in gh(f"repos/{repo}/pulls/{n}/reviews?per_page=100", paginate=True)]
    return ev


def record(data_dir, entry):
    """Append the decision to the audit log. Raises if it cannot be written."""
    os.makedirs(os.path.join(data_dir, "log"), exist_ok=True)
    with open(os.path.join(data_dir, "log", "merge-gate.jsonl"), "a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **entry}) + "\n")


def run(pc, request, do_merge=False, policy=None, gh=gh_api, merge_cmd=None, data_dir=None):
    """Collect, evaluate, record, and merge only if allowed and asked. Returns (allowed, reasons, merged)."""
    data_dir = data_dir or os.environ.get("STUDIO_DATA", "/srv/studio/data")
    proj, token = None, None
    try:
        policy = load_policy() if policy is None else policy
        app = policy.get("github_app") if isinstance(policy, dict) else None
        if app is not None:  # the policy names the merge App: use only its token, or refuse
            if not (isinstance(app, dict) and isinstance(app.get("app_id"), int) and isinstance(app.get("key_path"), str)):
                raise ValueError("github_app in the merge policy is malformed")
            token = github_app.installation_token(request["repo"], app["app_id"], app["key_path"])
            if gh is gh_api:
                gh = functools.partial(gh_api, token=token)
        ev = collect(pc, request, gh=gh)
        reasons = evaluate(policy, request, ev)
        proj, _ = project_policy(policy, ev["issue"].get("projectId"))
    except Exception as e:  # any failure to read evidence refuses
        reasons = [f"could not collect evidence: {type(e).__name__}: {str(e)[:160]}"]
    allowed = not reasons and proj is not None
    entry = {**request, "allowed": allowed, "reasons": reasons, "merge_requested": do_merge}
    record(data_dir, entry)  # no audit record, no merge
    if not (allowed and do_merge):
        return allowed, reasons, False
    cmd = merge_cmd or ["gh", "pr", "merge", str(request["pr"]), "--repo", request["repo"],
                        f"--{proj['merge_method']}", "--match-head-commit", request["head_sha"]]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=gh_env(token))
    merged = r.returncode == 0
    reasons = [] if merged else [f"GitHub refused the merge: {(r.stderr or '').strip()[:160]}"]
    try:
        record(data_dir, {**request, "merged": merged, "detail": (r.stderr or r.stdout).strip()[:200]})
    except OSError as e:  # the merge already happened (or not); report truthfully rather than crash
        reasons.append(f"merge result could not be written to the audit log: {e}")
    return allowed, reasons, merged
