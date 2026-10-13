"""The Clerk: scripts only, no LLM. One `tick` runs each step below; every step is idempotent
and isolated (an error in one is logged and does not stop the rest).

Issue lists use Paperclip's offset paging. Dependency transitions remain owned by
Paperclip; Clerk does not move blocked issues to todo.
Statuses used: backlog/todo/in_progress/in_review/blocked/done.
"""
import hashlib
import json
import os
import re
import subprocess
import time

from lib import deploy, github_app, merge_gate, notify, phone, quota, records, watchdog

GH_LINK = re.compile(r"GitHub:\s*([\w.-]+/[\w.-]+)#(\d+)")
RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"}
RED_LIMIT = 3
CAP_REFUSED = re.compile(r"studio-quota: \w+ cap reached")
RESUME_AFTER = 20 * 60  # seconds after a cap refusal before the agent is woken to try again
CAP_RESET = re.compile(r"\(resets (.+)\)\s*$")
CODEX_RESET = re.compile(r"^([A-Z][a-z]{2}) (\d{1,2}) (\d{2}):(\d{2}) UTC$")
STRANDED = "retry budget is spent"
STRANDED_REVIEW = "pending execution-review participant"  # Paperclip's comment when it blocks a review that never ran
REVIEW_STALL = 30 * 60  # seconds without a reviewer run before the Clerk steps in  # Paperclip's comment when it blocks an issue whose runs never started
STUCK_AFTER = 6 * 3600  # seconds a blocked task may sit untouched, with nothing open blocking it, before the Director hears
UNBLOCK_GRACE = 2 * 60  # seconds after the window resets, so the new reading is in
DIGEST_MAX_CHARS = 6000  # about 1,500 tokens
RECEIPT_DAYS = 60
GATE_LOOKBACK_DAYS = 14
QUOTA_DIR = os.environ.get("STUDIO_QUOTA_DIR", "/srv/studio/data/quota")
QUOTA_LEDGER = os.path.join(QUOTA_DIR, "claude.json")
QUOTA_POLICY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "policy", "quota.json")


APP_CONFIG = os.environ.get("STUDIO_AGENTS_APP_CONFIG", "/etc/studio/agents-app.json")
_tokens = {}  # owner -> (token, expires); App tokens last an hour


def gh_env(repo, config=APP_CONFIG, mint=github_app.account_installation_token, now=time.time):
    """Environment for a gh call on `repo`. When the agents' App is configured, gh uses that App's token
    for the repository's owner, never an inherited personal token; if no token can be made the call fails.
    Without the App config the environment is inherited unchanged."""
    if not os.path.exists(config):
        return None
    owner = repo.split("/", 1)[0]
    token, expires = _tokens.get(owner, (None, 0))
    if now() >= expires:
        with open(config) as f:
            cfg = json.load(f)
        token = mint(owner, cfg["app_id"], cfg["key_path"])
        _tokens[owner] = (token, now() + 50 * 60)
    env = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "GITHUB_TOKEN")}
    return {**env, "GH_TOKEN": token}


def gh_json(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60,
                       env=gh_env(args[args.index("--repo") + 1]))
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:200])
    return json.loads(r.stdout or "null")


class Clerk:
    def __init__(self, pc, company_id, data_dir, gh=gh_json, dry_run=False, director_id=None,
                 principal_id=None, recorder_id=None, now=time.time, deploy_repo=None, infra_project_id=None,
                 gate=merge_gate.run, merge_policy=merge_gate.load_policy):
        self.pc, self.cid, self.data, self.gh, self.dry = pc, company_id, data_dir, gh, dry_run
        self.gate, self.merge_policy = gate, merge_policy
        self.director, self.principal, self.recorder, self.now = director_id, principal_id, recorder_id, now
        self.deploy_repo, self.infra_project = deploy_repo, infra_project_id
        self.state_path = os.path.join(data_dir, "clerk-state.json")
        self.state = _load(self.state_path)
        self.dry_seen = set()  # dry-run receipts live only for this tick, so nothing is lost when dry-run ends
        self.needs_director, self.needs_board, self.notes = [], [], []

    # ---- plumbing -----------------------------------------------------------------
    def log(self, event, slug="studio", **kw):
        os.makedirs(os.path.join(self.data, "log"), exist_ok=True)
        rec = {"ts": int(self.now()), "event": event, **kw}
        with open(os.path.join(self.data, "log", f"{slug}.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")

    def act(self, what, fn, *a, **kw):
        """A write to Paperclip. In dry-run it is only logged."""
        self.log("dry_run" if self.dry else "act", what=what)
        return None if self.dry else fn(*a, **kw)

    def handled(self, key):
        return key in self.state.get("done", {}) or key in self.dry_seen

    def mark(self, key):
        if self.dry:
            self.dry_seen.add(key)
        else:
            self.state.setdefault("done", {})[key] = int(self.now())

    def seen(self, key):
        """True if key was already handled; otherwise marks it. For notes only: actions use once()."""
        if self.handled(key):
            return True
        self.mark(key)
        return False

    def once(self, key, what, fn, *a, **kw):
        """Do a Paperclip write at most once. The receipt is kept only after the write succeeds, so a failed
        write is retried next tick; in dry-run nothing is written and nothing is kept."""
        if self.handled(key):
            return False
        self.act(what, fn, *a, **kw)
        self.mark(key)
        return True

    def save(self):
        cutoff = self.now() - RECEIPT_DAYS * 86400
        self.state["done"] = {k: t for k, t in self.state.get("done", {}).items() if t >= cutoff}
        _save(self.state_path, self.state)

    # ---- the tick -----------------------------------------------------------------
    def tick(self):
        issues = self.pc.list_issues(self.cid)
        by_id = {i["id"]: i for i in issues}
        for step in (self.deploy_sync, self.github_sync, self.merge_approved, self.plan_gate, self.ensure_review, self.caps, self.resume_capped, self.unblock_capped,
                     self.restart_reviews, self.stuck_to_director, self.tell_benjamin, self.watchdog, self.record_runs, self.digest):
            try:
                step(issues, by_id)
            except Exception as e:  # keep going; record it
                self.log("step_error", step=step.__name__, error=str(e)[:300])
                self.notes.append(f"clerk step {step.__name__} failed: {str(e)[:120]}")
        self.save()

    # ---- 0: keep the deployed studio-company in step with main --------------------------------
    def deploy_sync(self, issues, by_id):
        if not self.deploy_repo:
            return
        res = deploy.sync(self.deploy_repo, skip_sha=self.state.get("deploy_failed_sha"))
        st = res["status"]
        self.log("deploy", status=st, sha=(res.get("sha") or "")[:8])
        if st == "updated":
            self.state.pop("deploy_failed_sha", None)
            changed = res["changed"]
            self.notes.append(f"Deployed studio-company {res['sha'][:8]} ({len(changed)} files changed)")
            if self.infra_project and any(f.startswith("skills/") for f in changed):
                self.act("rescan-skills", self.pc.rescan_skills, self.cid, self.infra_project)
        elif st == "tests_failed":
            if not res.get("repeat"):
                self.state["deploy_failed_sha"] = res["sha"]
                self.needs_board.append(f"NOT deployed: tests fail on studio-company {res['sha'][:8]}. Fix main or revert.")
        elif st in ("dirty", "diverged", "fetch_failed"):
            self.notes.append(f"Deploy skipped ({st}): {res.get('detail', '')}")

    # ---- 1+2+5: GitHub -> Paperclip, merges, red-check loop --------------------------
    def github_sync(self, issues, by_id):
        """Follow the PRs an issue records as work products (agent-bin/studio-record-pr). A branch name is not
        proof of linkage: a PR found only by name is reported to the Director, never acted on."""
        for i in issues:
            if i.get("status") in ("done", "cancelled"):
                continue
            try:
                self.sync_issue(i, issues)
            except Exception as e:  # one unreadable issue must not hide the others
                self.log("issue_error", step="github_sync", task=i["id"], error=str(e)[:300])
                self.notes.append(f"{i.get('identifier') or i['title']}: GitHub check failed: {str(e)[:120]}")

    def sync_issue(self, i, issues):
        products = self.pc.work_products(i["id"]) or []
        linked = [(w, *merge_gate.PR_URL.match(w["url"]).groups()) for w in products
                  if w.get("type") == "pull_request" and w.get("provider") == "github"
                  and merge_gate.PR_URL.match(w.get("url") or "")]
        if not linked:
            self.unlinked(i)
            return
        prs = []
        for w, repo, num in linked:
            pr = self.gh(["pr", "view", num, "--repo", repo,
                          "--json", "number,state,mergedAt,headRefOid,statusCheckRollup,url"])
            if pr:
                self.pr_state(i, pr, w)
                prs.append(pr)
        self.merged_means_done(i, prs, issues)

    # ---- 2b: approved and green -> the merge gate ----------------------------------------
    def merge_approved(self, issues, by_id):
        """Run the deterministic merge gate on each open, green PR of a recently approved task. Paperclip marks a
        task done as soon as its review stage approves, so these are done issues. The gate alone decides; the Clerk
        only asks, once per head. Benjamin, 2026-10-10: the Director, starved by the usage cap, used to be the only
        caller, so approved PRs waited for him to merge by hand."""
        try:
            policy = self.merge_policy()
        except (OSError, ValueError) as e:
            self.log("merge_policy_error", error=str(e)[:200])
            return
        cutoff = self.now() - GATE_LOOKBACK_DAYS * 86400
        for i in issues:
            if i.get("status") != "done" or not merge_gate.project_policy(policy, i.get("projectId"))[0]:
                continue
            updated = merge_gate._when(i.get("updatedAt"))
            if updated is None or updated.timestamp() < cutoff:
                continue
            if "executionPolicy" not in i:  # the issue list leaves it out; without it no task ever reached the gate
                i = self.pc.get_issue(i["id"]) or i
            stages = (i.get("executionPolicy") or {}).get("stages")
            if not stages or not merge_gate.paperclip_review_complete(i):
                continue
            try:
                self.gate_issue(i)
            except Exception as e:  # one unreadable issue must not hide the others
                self.log("issue_error", step="merge_approved", task=i["id"], error=str(e)[:300])

    def gate_issue(self, issue):
        for w in self.pc.work_products(issue["id"]) or []:
            m = merge_gate.PR_URL.match(w.get("url") or "")
            if not (m and w.get("type") == "pull_request" and w.get("provider") == "github"):
                continue
            repo, num = m.groups()
            pr = self.gh(["pr", "view", num, "--repo", repo, "--json", "number,state,headRefOid,statusCheckRollup"])
            checks = (pr or {}).get("statusCheckRollup") or []
            if not pr or pr.get("state") != "OPEN" or not checks or any(
                    (c.get("conclusion") or c.get("state")) in RED or not (c.get("conclusion") or c.get("state"))
                    or (c.get("status") or "") in ("IN_PROGRESS", "QUEUED") for c in checks):
                continue
            key = f"gate:{issue['id']}:{repo}#{num}:{pr.get('headRefOid')}"
            if self.handled(key):
                continue
            if self.dry:
                self.mark(key)
                self.log("dry_run", what="merge-gate", task=issue["id"], pr=int(num))
                continue
            request = {"issue_id": issue["id"], "repo": repo, "pr": int(num), "head_sha": pr.get("headRefOid")}
            allowed, reasons, merged = self.gate(self.pc, request, do_merge=True)
            if any(r.startswith("could not") for r in reasons):
                self.log("merge_gate_retry", task=issue["id"], pr=int(num), reasons=reasons[:3])
                continue  # evidence was unreadable: ask again next tick
            self.mark(key)
            self.log("merge_gate", task=issue["id"], pr=int(num), head=pr.get("headRefOid"), allowed=allowed,
                     merged=merged, reasons=reasons[:5])
            if merged:
                self.notes.append(f"{issue['title']}: PR #{num} merged by the merge gate")
            elif merge_gate.only_protected(reasons):
                self.notes.append(f"{issue['title']}: PR #{num} labelled ready-for-benjamin (touches protected files)")
            else:
                self.needs_director.append(f"PR #{num} ({issue['title']}): the merge gate refused: "
                                           + "; ".join(reasons[:3]))

    def unlinked(self, issue):
        m = GH_LINK.search(issue.get("description") or "")
        if not m:
            return
        repo, num = m.groups()
        for prefix in dict.fromkeys(p for p in (issue.get("identifier"), num) if p):
            for pr in self.gh(["pr", "list", "--repo", repo, "--state", "all", "--search", f"head:agent/{prefix}-",
                               "--json", "number,url"]) or []:
                if not self.seen(f"unlinked:{issue['id']}:{repo}#{pr['number']}"):
                    self.needs_director.append(
                        f"{issue['title']}: PR #{pr['number']} ({pr.get('url', repo)}) matches by branch name only. "
                        f"If it belongs to this issue, record it: studio-record-pr {issue['id']} <PR URL>")

    def pr_state(self, issue, pr, product):
        iid, n = issue["id"], pr["number"]
        checks = pr.get("statusCheckRollup") or []
        red = any((c.get("conclusion") or c.get("state")) in RED for c in checks)
        pending = any(not (c.get("conclusion") or c.get("state")) or (c.get("status") or "") in ("IN_PROGRESS", "QUEUED") for c in checks)
        label = "merged" if pr.get("mergedAt") else pr["state"].lower()
        label += " · checks red" if red else (" · checks running" if pending else " · checks green" if checks else "")
        # A comment wakes the issue's agent (Paperclip wakes the assignee on any comment not its own), so the Clerk
        # comments only when the agent has something to do: red checks to fix, or a PR closed without merging.
        # 2026-10-02: about 16 runs did nothing but read "PR is open, checks green" and end.
        if red or label.startswith("closed"):
            self.once(f"pr:{iid}:{n}:{pr.get('headRefOid')}:{label}", "comment", self.pc.comment, iid,
                      f"[Clerk] PR #{n} is {label}. {pr.get('url', '')}")
        else:
            self.log("pr_state", task=iid, pr=n, state=label)
        status = "merged" if pr.get("mergedAt") else "closed" if pr["state"] == "CLOSED" else None
        if status and product.get("status") != status:
            self.once(f"product:{product['id']}:{status}", "work-product", self.pc.update_work_product,
                      product["id"], status=status)
        if red and not self.handled(f"red:{iid}:{pr.get('headRefOid')}"):
            self.mark(f"red:{iid}:{pr.get('headRefOid')}")
            self.log("check_red", task=iid, pr=n)
            if not self.dry:
                self.state.setdefault("red", {})[iid] = self.state.get("red", {}).get(iid, 0) + 1
            if self.state.get("red", {}).get(iid, 0) >= RED_LIMIT and self.principal:
                if self.once(f"escalate:{iid}", "escalate", self.pc.patch_issue, iid, assigneeAgentId=self.principal,
                             comment=f"[Clerk] {RED_LIMIT} red check runs. Handing to the Principal."):
                    self.notes.append(f"{issue['title']}: 3 red checks, handed to the Principal")
        elif pr["state"] == "OPEN" and not red and not pending and checks:
            # merge_approved asks the merge gate once the review approves, so a green PR wakes nobody.
            # Benjamin hears only of PRs the gate labels ready-for-benjamin (2026-10-02: this line used to
            # ask him to merge every green PR, so he merged them before review).
            if not self.seen(f"review-ready:{iid}:{pr.get('headRefOid')}"):
                self.notes.append(f"{issue['title']}: PR #{n} green, waiting for review")

    def merged_means_done(self, issue, prs, issues):
        """Done only when every recorded PR is closed, at least one merged, and the assignee has already put the
        issue in review. A merge on an issue still in progress goes to the Director instead."""
        if not prs or any(p["state"] == "OPEN" for p in prs) or not any(p.get("mergedAt") for p in prs):
            return
        iid = issue["id"]
        if issue.get("status") != "in_review":
            if not self.seen(f"merged-not-in-review:{iid}"):
                self.needs_director.append(f"{issue['title']}: its PR merged but the issue is {issue.get('status')}; "
                                           "decide whether it is done")
            return
        if self.once(f"merged:{iid}", "done", self.pc.patch_issue, iid, status="done"):
            self.log("merged", task=iid, prs=[p["number"] for p in prs])
            for d in [x for x in issues if iid in (x.get("blockedByIssueIds") or [])]:
                self.once(f"bring-main-in:{d['id']}:{iid}", "bring-main-in", self.pc.comment, d["id"],
                          f"[Clerk] '{issue['title']}' merged. Bring `main` into your branch before continuing.")

    # ---- 3: approved B plan -> copy to GitHub, wake the builder ----------------------
    def plan_gate(self, issues, by_id):
        for i in issues:
            if i.get("status") in ("done", "cancelled"):
                continue
            plan = self.pc.get_document(i["id"], "plan")
            if not plan:
                continue
            revision = plan.get("latestRevisionId") if isinstance(plan, dict) else None
            reqs = [x for x in self.pc.interactions(i["id"]) if x.get("kind") == "request_confirmation"
                    and ((x.get("payload") or {}).get("target") or {}).get("type") == "issue_document"
                    and ((x.get("payload") or {}).get("target") or {}).get("key") == "plan"]
            approved = [x for x in reqs if x.get("status") == "accepted"
                        and x.get("effectiveResolverPolicy") == "human_only"
                        and x.get("resolvedByUserId") and not x.get("resolvedByAgentId")
                        and ((x.get("payload") or {}).get("target") or {}).get("revisionId") == revision]
            if not revision or not approved:
                if any(x.get("status") == "pending" for x in reqs):
                    self.needs_board.append(f"Plan confirmation waiting: {i['title']}")
                continue
            approval = approved[-1]
            key = f"plan:{i['id']}:{revision}:{approval['id']}"
            m = GH_LINK.search(i.get("description") or "")
            if m:
                body = plan.get("body", "") if isinstance(plan, dict) else str(plan)
                self.once(key + ":github", "plan->github", self.gh_comment, m.group(1), m.group(2),
                          "Approved plan:\n\n" + body)
            if i.get("assigneeAgentId"):
                self.once(key + ":wake", "wake", self.pc.wake_agent, i["assigneeAgentId"], fresh=False)

    def gh_comment(self, repo, num, body):
        subprocess.run(["gh", "issue", "comment", num, "--repo", repo, "--body", body], check=True, timeout=60,
                       env=gh_env(repo))

    # ---- 4: usage caps (enforced by agent-exec; reported here) ---------------------------
    def caps(self, issues, by_id):
        """Report the usage-cap ledger kept by bin/studio-quota. Read-only: agent-exec refuses runs that would
        break a cap, so the Clerk no longer pauses or resumes agents."""
        try:
            with open(QUOTA_LEDGER) as f:
                ledger = json.load(f)
        except FileNotFoundError:
            self.state["usage"] = "no usage-cap ledger yet (no agent run since caps were activated)"
            return
        last = ledger.get("last")
        if not last:
            self.state["usage"] = "usage-cap ledger has no reading yet"
            return
        s = quota.status(ledger, last, quota.load_policy(QUOTA_POLICY, "claude"))
        age = int((self.now() - last["t"]) / 60)
        self.state["usage"] = (f"Claude studio use {s['studio']['five_hour']:g} of {s['caps']['five_hour']} points this "
                               f"5-hour window (resets {s['resets']['five_hour']}), {s['studio']['week']:g} of "
                               f"{s['caps']['week']} this week; account {s['account']['five_hour']:g}% / "
                               f"{s['account']['week']:g}%; {s['active_runs']} runs active; reading {age} min old")
        self.log("caps", usage=self.state["usage"])

    BUILDING = re.compile(r"^(Builder-\d+|Codex-Builder|Principal|Codex-Principal)$")

    def ensure_review(self, issues, by_id, policy=None):
        """Give each code task in an autonomously merged project a Paperclip review stage when it has none:
        the Principal reviews, or Codex-Principal when the Principal wrote it. 2026-10-02: the 6d tasks had no
        reviewer, so Paperclip let the Builder park its work in review only behind an hourly self-check, and
        the merge gate never saw an approval, so every PR fell to Benjamin. The packet's own review policy,
        when it sets one, is never replaced. While Claude's week has no room, Codex-Principal reviews everything,
        so reviews do not wait days for the weekly reset (Benjamin, 2026-10-04: "move all active tasks to codex")."""
        try:
            policy = policy or merge_gate.load_policy()
        except (OSError, ValueError):
            return
        projects = {pid for pid, p in (policy.get("projects") or {}).items() if isinstance(p, dict) and p.get("enabled")}
        agents = {a["id"]: a.get("name", "") for a in self.pc.list_agents(self.cid)}
        by_name = {n: i for i, n in agents.items()}
        claude_out = self.claude_week_out(by_name.get("Principal"))
        for i in issues:
            who = agents.get(i.get("assigneeAgentId"), "")
            if i.get("projectId") not in projects or i.get("status") not in ("todo", "in_progress") \
                    or i.get("executionPolicy") or not self.BUILDING.match(who):
                continue
            codex = who == "Principal" or claude_out
            reviewer = by_name.get("Codex-Principal" if codex else "Principal")
            if not reviewer or self.handled(f"review-stage:{i['id']}"):
                continue
            # Paperclip's issue list always shows executionPolicy as null; only the issue itself has it
            # (2026-10-02: AGE-6's two-stage review was replaced because the list said it had none).
            if self.pc.get_issue(i["id"]).get("executionPolicy"):
                self.mark(f"review-stage:{i['id']}")
                continue
            stage = {"type": "review", "participants": [{"type": "agent", "agentId": reviewer}], "approvalsNeeded": 1}
            if self.once(f"review-stage:{i['id']}", f"review stage on {i.get('identifier')}", self.pc.patch_issue,
                         i["id"], executionPolicy={"mode": "normal", "stages": [stage]}):
                self.log("review_stage", task=i.get("identifier"), reviewer=agents[reviewer])

    def claude_week_out(self, agent_id):
        """True when the usage-cap ledger shows no room left this week for a run of this agent (its estimate)."""
        try:
            with open(QUOTA_LEDGER) as f:
                ledger = json.load(f)
            policy = quota.load_policy(QUOTA_POLICY, "claude")
            return bool(ledger.get("last")) and \
                quota.week_room(ledger, ledger["last"], policy) < quota.estimate(ledger, agent_id, policy)["week"]
        except (OSError, ValueError, KeyError):
            return False

    def resume_capped(self, issues, by_id):
        """Wake an agent whose latest run was refused by a usage cap, once per refusal, 20 minutes after it.
        Paperclip retries a refused run a few times and then leaves the agent in error; nothing woke it after
        the window reset, so the Studio stayed stopped all night (2026-10-02). The wake goes through admission
        again: if there is still no room it is refused once more, and that new refusal is woken 20 minutes later.
        A refusal costs one usage reading, no model use. Paused agents are left alone."""
        agents = {a["id"]: a for a in self.pc.list_agents(self.cid)}
        latest = {}
        for r in self.pc.runs(self.cid, limit=200):
            if self.dead_retry(r):  # 2026-10-12 (AGE-77): a retry that never started hid the refusal under it
                continue
            if r.get("createdAt", "") > latest.get(r["agentId"], {}).get("createdAt", ""):
                latest[r["agentId"]] = r
        for agent_id, r in latest.items():
            a = agents.get(agent_id, {})
            if r.get("status") != "failed" or not CAP_REFUSED.search(r.get("error") or "") \
                    or a.get("status") not in ("error", "idle"):
                continue
            ended = _epoch(r.get("finishedAt") or r.get("createdAt"))
            if ended is None or self.now() - ended < RESUME_AFTER:
                continue
            issue = (r.get("contextSnapshot") or {}).get("issueId")
            if self.once(f"resume-capped:{r['id']}", f"wake {a.get('name', agent_id)} after a cap refusal",
                         self.pc.wake_agent, agent_id, True, "Usage cap refused your last run; trying again", issue):
                self.log("resume_capped", agent=a.get("name", agent_id), run=r["id"], issue=issue)

    def dead_retry(self, r):
        """A Paperclip scheduled retry that was due more than RESUME_AFTER ago and never started."""
        due = _epoch(r.get("scheduledRetryAt")) if r.get("status") == "scheduled_retry" else None
        return due is not None and self.now() - due > RESUME_AFTER

    def restart_reviews(self, issues, by_id):
        """Give a review that never started a reviewer run. Paperclip wakes the reviewer once when a task enters
        review; if a usage cap refuses that run, the review waits for ever, and after one retry Paperclip blocks
        the task (2026-10-12: #86, #93 and #94 waited a day while Codex sat unused). After REVIEW_STALL with no
        reviewer run, the stage goes to the other principal when the reviewer's provider is capped and the other
        is not already a reviewer on the task or its author; otherwise the same reviewer is woken again."""
        agents = {a["id"]: a for a in self.pc.list_agents(self.cid)}
        by_name = {a.get("name"): a["id"] for a in agents.values()}
        principal, codex = by_name.get("Principal"), by_name.get("Codex-Principal")
        other = {principal: codex, codex: principal} if principal and codex else {}
        runs = [r for r in self.pc.runs(self.cid, limit=200) if not self.dead_retry(r)]
        latest = {}
        for r in runs:
            if r.get("createdAt", "") > latest.get(r["agentId"], {}).get("createdAt", ""):
                latest[r["agentId"]] = r
        now = self.now()
        # 2026-10-13: a refusal whose window has since reset no longer means capped; counting it kept AGE-81's
        # review on the capped Principal while Codex had its whole window free
        capped = {a for a, r in latest.items() if r.get("status") == "failed" and CAP_REFUSED.search(r.get("error") or "")
                  and (_cap_reset(r.get("error") or "", now) or float("inf")) > now}
        for i in issues:
            if i.get("status") not in ("in_review", "blocked"):
                continue
            full = self.pc.get_issue(i["id"])  # the issue list leaves out the review state
            state, policy = full.get("executionState") or {}, full.get("executionPolicy") or {}
            who = (state.get("currentParticipant") or {}).get("agentId")
            if state.get("status") != "pending" or state.get("currentStageType") != "review" or not who \
                    or agents.get(who, {}).get("status") == "paused":
                continue
            if i["status"] == "blocked":
                note = sorted(self.pc.comments(i["id"]), key=lambda c: c.get("createdAt", ""))[-1:]
                if not note or STRANDED_REVIEW not in (note[0].get("body") or ""):
                    continue  # blocked by someone, not by Paperclip giving up on the reviewer
            prs = [w for w in self.pc.work_products(i["id"]) or [] if w.get("type") == "pull_request"]
            if prs and all(w.get("status") in ("merged", "closed") for w in prs):
                continue  # nothing left to review: its PR is merged or closed
            mine = [r for r in runs if r.get("agentId") == who and (r.get("contextSnapshot") or {}).get("issueId") == i["id"]]
            if any(r.get("status") in ("queued", "running", "scheduled_retry") for r in mine):
                continue
            last = max(mine, key=lambda r: r.get("createdAt", ""), default=None)
            since = _epoch((last or {}).get("finishedAt") or (last or {}).get("createdAt") or full.get("updatedAt"))
            if since is None or now - since < REVIEW_STALL:
                continue
            key = f"restart-review:{i['id']}:{int(since)}"
            if self.handled(key):
                continue
            stages = policy.get("stages") or []
            idx = next((n for n, s in enumerate(stages) if any(p.get("agentId") == who for p in s.get("participants") or [])), None)
            if idx is None:
                continue
            reviewers = {p.get("agentId") for s in stages for p in s.get("participants") or []}
            alt = other.get(who)
            reviewer = alt if (who in capped and alt and alt not in capped and alt not in reviewers
                               and alt != i.get("assigneeAgentId") and agents.get(alt, {}).get("status") != "paused") else who
            def with_reviewer(agent):
                p = json.loads(json.dumps(policy))
                p["stages"][idx]["participants"] = [{"type": "agent", "agentId": agent}]
                return p
            name = agents.get(reviewer, {}).get("name", reviewer)
            if reviewer != who:
                self.act(f"review of {i.get('identifier')} to {name}", self.pc.patch_issue, i["id"],
                         executionPolicy=with_reviewer(reviewer))
            elif i["status"] == "blocked" and alt:  # a participant change is what restores a stage Paperclip gave up on
                self.act(f"restore review stage on {i.get('identifier')}", self.pc.patch_issue, i["id"],
                         executionPolicy=with_reviewer(alt))
                self.act(f"restore review stage on {i.get('identifier')}", self.pc.patch_issue, i["id"],
                         executionPolicy=with_reviewer(who))
            self.act("comment", self.pc.comment, i["id"],
                     f"[Clerk] This review never got a reviewer run, so {name} is asked to review it now.")
            self.act(f"wake {name}", self.pc.wake_agent, reviewer, True, f"Review {i.get('identifier')}", i["id"])
            self.mark(key)
            self.log("restart_review", task=i.get("identifier"), reviewer=name, was=agents.get(who, {}).get("name"))

    def stuck_to_director(self, issues, by_id):
        """Put a blocked task on the Director's digest when it has sat untouched for STUCK_AFTER with nothing open
        blocking it. Paperclip blocks a task when its retries or its own repair run out and then waits for
        someone; refurb part 2 (AGE-63) sat so from 2026-10-11 while its PR waited for a review nobody asked for.
        Left out: tasks the other steps restart (a cap refusal, a stranded review), tasks waiting on a card only
        Benjamin can answer, the Director's own tasks, people's tasks and paused agents' tasks. The digest wakes
        the Director only when this list changes."""
        agents = {a["id"]: a for a in self.pc.list_agents(self.cid)}
        latest = {}
        for r in self.pc.runs(self.cid, limit=200):
            iid = (r.get("contextSnapshot") or {}).get("issueId")
            if iid and not self.dead_retry(r) and r.get("createdAt", "") > latest.get(iid, {}).get("createdAt", ""):
                latest[iid] = r
        now = self.now()
        for i in issues:
            who = i.get("assigneeAgentId")
            if i.get("status") != "blocked" or not who or who == self.director \
                    or agents.get(who, {}).get("name") == "Director" or agents.get(who, {}).get("status") == "paused":
                continue
            since = _epoch(i.get("updatedAt"))
            if since is None or now - since < STUCK_AFTER:
                continue
            if any((b.get("status") or by_id.get(b.get("id"), {}).get("status")) not in ("done", "cancelled")
                   for b in i.get("blockedBy") or []):
                continue
            r = latest.get(i["id"]) or {}
            if r.get("status") in ("queued", "running", "scheduled_retry") or \
                    (r.get("status") == "failed" and CAP_REFUSED.search(r.get("error") or "")):
                continue  # running, or unblock_capped restarts it after the window resets
            state = self.pc.get_issue(i["id"]).get("executionState") or {}
            if state.get("status") == "pending" and (state.get("currentParticipant") or {}).get("agentId"):
                continue  # restart_reviews looks after an agent's review stage
            if any(phone.human_card(c) for c in self.pc.interactions(i["id"]) or []):
                continue  # waiting on Benjamin, who has been told
            note = sorted(self.pc.comments(i["id"]), key=lambda c: c.get("createdAt", ""))[-1:]
            why = (note[0].get("body") or "").strip().split("\n")[0][:160] if note else "no comment"
            day = time.strftime("%d %b %H:%M", time.localtime(since))
            self.needs_director.append(
                f"{i.get('identifier', i['id'])} ({i.get('title', '')}), {agents.get(who, {}).get('name', who)}: "
                f"blocked and untouched since {day}, with nothing open blocking it. Last note: \"{why}\". "
                f"Unblock it, reassign it or cancel it.")
            self.log("stuck_to_director", task=i.get("identifier", i["id"]))

    def unblock_capped(self, issues, by_id):
        """Move an issue back to todo when Paperclip blocked it only because usage caps refused its runs, once the
        window named in the refusal has reset. Paperclip blocks such an issue after a few refused retries, and
        nothing unblocked it, so after every reset someone had to (Benjamin, 2026-10-11). Only when the issue's
        latest run is a cap refusal, its latest comment is Paperclip's own retry-budget note (so a block by a
        person or an agent after it is left alone), no blocker is still open and its assignee is not paused.
        If there is still no room, the run is refused again and the new refusal is handled after its reset."""
        agents = {a["id"]: a for a in self.pc.list_agents(self.cid)}
        latest = {}
        for r in self.pc.runs(self.cid, limit=200):
            iid = (r.get("contextSnapshot") or {}).get("issueId")
            if iid and r.get("createdAt", "") > latest.get(iid, {}).get("createdAt", ""):
                latest[iid] = r
        for i in issues:
            r = latest.get(i["id"])
            if i.get("status") != "blocked" or not r or r.get("status") != "failed" \
                    or not CAP_REFUSED.search(r.get("error") or ""):
                continue
            if agents.get(i.get("assigneeAgentId"), {}).get("status") == "paused":
                continue
            if any((b.get("status") or by_id.get(b.get("id"), {}).get("status")) not in ("done", "cancelled")
                   for b in i.get("blockedBy") or []):
                continue
            reset = _cap_reset(r.get("error") or "", self.now())
            if reset is None:  # an unreadable reset time: wait a whole window from the refusal
                ended = _epoch(r.get("finishedAt") or r.get("createdAt"))
                reset = ended + 5 * 3600 if ended is not None else None
            if reset is None or self.now() < reset + UNBLOCK_GRACE or self.handled(f"unblock-capped:{r['id']}"):
                continue
            last = sorted(self.pc.comments(i["id"]), key=lambda c: c.get("createdAt", ""))[-1:]
            if not last or STRANDED not in (last[0].get("body") or ""):
                continue
            self.once(f"unblock-capped:{r['id']}", f"unblock {i.get('identifier', i['id'])} after a cap reset",
                      self.pc.patch_issue, i["id"], status="todo",
                      comment="[Clerk] Unblocking: this was blocked only because usage caps refused its runs, "
                              "and that window has now reset.")
            self.log("unblock_capped", task=i["id"], run=r["id"])
            self.notes.append(f"{i.get('title', i['id'])}: unblocked after a usage-cap reset")

    # ---- 4c: the only notices that reach Benjamin's phone (lib/phone.py) ----------------------------
    def tell_benjamin(self, issues, by_id):
        """Phone him once per PR head that waits for his merge, and once per human-only card he must answer.
        Benjamin, 2026-10-12: nothing else, in plain words, saying what waits on each merge."""
        try:
            policy = self.merge_policy()
        except (OSError, ValueError) as e:
            self.log("merge_policy_error", error=str(e)[:200])
            policy = {}
        repos = sorted({p.get("repo") for p in (policy.get("projects") or {}).values() if p.get("repo")})
        open_prs = {}
        for repo in repos:
            prs = self.gh(["pr", "list", "--repo", repo, "--state", "open", "--limit", "50", "--json",
                           "number,title,headRefOid,isDraft,statusCheckRollup,labels,reviews,comments,url"]) or []
            for pr in prs:
                open_prs[(repo, pr["number"])] = pr
                if phone.ready_for_merge(pr):
                    self.merge_ready(repo, pr, issues)
        live = [i for i in issues if i.get("status") not in ("done", "cancelled")]
        for i in live:
            for card in self.pc.interactions(i["id"]) or []:
                if not phone.human_card(card) or phone.merge_card(card):
                    continue
                named = phone.prs_named(card)
                if named and repos and not any((r, n) in open_prs for r in repos for n in named):
                    continue  # it is about a PR that is no longer open
                key = f"phone-card:{card['id']}"
                if self.handled(key):
                    continue
                title, text = phone.card_notice(card.get("title") or "", i.get("title") or "")
                self.ring(key, text, title, notify.link(f"/{i['identifier'].split('-')[0]}/issues/{i['identifier']}")
                          if i.get("identifier") else None)

    def merge_ready(self, repo, pr, issues):
        key = f"phone-merge:{repo}#{pr['number']}:{pr.get('headRefOid')}"
        if self.handled(key):
            return
        url = f"https://github.com/{repo}/pull/{pr['number']}"
        linked = []
        for i in issues:
            if i.get("status") == "cancelled":
                continue
            if any(merge_gate.PR_URL.match(w.get("url") or "") and (w.get("url") or "").rstrip("/") == url
                   for w in self.pc.work_products(i["id"]) or [] if w.get("type") == "pull_request"):
                linked.append(i)
        work = [i for i in linked if not re.match(r"\s*review pr #", i.get("title") or "", re.I)]
        for i in work:  # 2026-10-12: #86 was pinged after its first of two review stages approved
            full = self.pc.get_issue(i["id"])
            if (full.get("executionPolicy") or {}).get("stages") and not merge_gate.paperclip_review_complete(full):
                return
        what = phone.plain(work[0]["title"]) if work else phone.plain(pr.get("title") or "")
        ids = {i["id"] for i in linked}
        blocked = [phone.plain(i["title"]) for i in issues if i.get("status") not in ("done", "cancelled")
                   and i["id"] not in ids and ids & set(i.get("blockedByIssueIds") or [])]
        title, text = phone.merge_notice(pr["number"], what, list(dict.fromkeys(blocked)))
        self.ring(key, text, title, url)

    def ring(self, key, text, title, click=None):
        self.needs_board.append(f"{title}: {text.splitlines()[0]}")
        if self.dry:
            self.mark(key)
            self.log("dry_run", what="phone", title=title)
            return
        notify.send(self.data, text, self.now(), phone=True, title=title, click=click)
        self.mark(key)
        self.log("phone", key=key, title=title)

    def watchdog(self, issues, by_id):
        """Stuck work: retry once, then tell Benjamin in one line (lib/watchdog.py, lib/notify.py)."""
        seen = []
        for i in issues:
            key = f"blocked:{i['id']}:{i.get('updatedAt')}"
            if i.get("status") == "blocked" and not self.handled(key):
                latest = sorted(self.pc.comments(i["id"]), key=lambda c: c.get("createdAt", ""))[-1:]
                i = {**i, "_latest_comment": (latest[0].get("body") or "").strip().split("\n")[0] if latest else ""}
            seen.append(i)
        now = self.now()
        for kind, key, *args in watchdog.plan(now, self.pc.list_agents(self.cid), self.pc.runs(self.cid, limit=200),
                                              seen, self.state.setdefault("watch", {}), notify.quiet(now)):
            if self.handled(key):
                continue
            if kind == "wake":
                agent, issue, reason = args
                self.act(f"watchdog wake {agent}", self.pc.wake_agent, agent, True, reason, issue)
            elif kind == "cancel":
                self.act(f"watchdog cancel run {args[0]}", self.pc.cancel_run, args[0])
            elif kind == "notify":
                self.needs_board.append(args[0])
                if not self.dry:
                    notify.send(self.data, args[0], now)
            self.mark(key)
            self.log("watchdog", kind=kind, key=key)
        if not self.dry:
            notify.flush(self.data, now)

    # ---- 5: efficiency records (research 11), append-only ------------------------------------
    def record_runs(self, issues, by_id):
        """Record every finished run once. Records are evidence, not Paperclip state, so dry-run writes them too."""
        names = {a["id"]: a.get("name", "") for a in self.pc.list_agents(self.cid)}
        n = records.collect(self.pc.runs(self.cid, limit=200), names, records.usage_by_run(QUOTA_DIR),
                            os.path.join(self.data, "records", "runs.jsonl"))
        if n:
            self.log("records", new=n)

    def report(self):
        """Write records/report.md from the run records and the issues' current states."""
        path = os.path.join(self.data, "records", "report.md")
        recs = records.load_jsonl(os.path.join(self.data, "records", "runs.jsonl"))
        issues = {i["id"]: i for i in self.pc.list_issues(self.cid)}
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(records.report(recs, issues, now=self.now()))
        return path

    # ---- 6: digest ----------------------------------------------------------------------
    def digest(self, issues, by_id):
        lines = ["# Digest", f"_{time.strftime('%Y-%m-%d %H:%M', time.localtime(self.now()))}_", ""]
        for h, items in (("Needs you (Board)", self.needs_board), ("Needs the Director", self.needs_director),
                         ("Notes", self.notes)):
            lines += [f"## {h}"] + ([f"- {x}" for x in items] or ["- nothing"]) + [""]
        counts = {}
        for i in issues:
            counts[i.get("status", "?")] = counts.get(i.get("status", "?"), 0) + 1
        lines.append("## Work: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        lines.append(f"Usage: {self.state.get('usage', 'n/a')}")
        text = "\n".join(lines)[:DIGEST_MAX_CHARS]
        # TODO(check): the "Director inbox" issue is found by title; the Worker's summaries of agent comments are not wired in yet.
        inbox = next((i for i in issues if i.get("title") == "Director inbox"), None)
        if self.dry or not inbox:
            os.makedirs(self.data, exist_ok=True)
            open(os.path.join(self.data, "digest.md"), "w").write(text)
        else:
            self.pc.put_document(inbox["id"], "digest", text)
        wake = bool(self.needs_director or self.needs_board)
        h = hashlib.sha256((str(self.needs_director) + str(self.needs_board)).encode()).hexdigest()
        if wake and self.director and h != self.state.get("last_wake_hash"):
            if not self.dry:
                self.state["last_wake_hash"] = h
            self.act("wake-director", self.pc.wake_agent, self.director, fresh=True)
        self.log("digest", wake=wake, dry=self.dry)

    # ---- 8: weekly -------------------------------------------------------------------------
    def weekly(self):
        out = os.path.join(self.data, "backup", time.strftime("%Y-%m-%d", time.localtime(self.now())))
        os.makedirs(out, exist_ok=True)
        ok = self.act("export", self.pc.export_company, self.cid, out) if not self.dry else None
        report = {"by_agent": self.pc.costs_by_agent(self.cid), "by_project": self.pc.costs_by_project(self.cid),
                  "export_ok": ok}
        json.dump(report, open(os.path.join(out, "cost-report.json"), "w"), indent=2)
        self.log("weekly", out=out)
        return out


def _epoch(iso):
    """Paperclip's ISO times (2026-10-01T20:13:56.216Z) as epoch seconds; None if absent or unreadable."""
    import datetime
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def _cap_reset(error, now):
    """When the window named in a cap refusal resets, as epoch seconds; None if it cannot be read. Claude's
    readings say "Oct 11, 3:20am (Europe/London)", Codex's "Oct 11 02:58 UTC" (lib/quota.py)."""
    import datetime
    m = CAP_RESET.search(error)
    if not m:
        return None
    text = m[1].strip()
    c = CODEX_RESET.match(text)
    if not c:
        return quota.parse_reset(text, now)
    year = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).year
    try:
        at = datetime.datetime(year, quota.MONTHS[c[1]], int(c[2]), int(c[3]), int(c[4]), tzinfo=datetime.timezone.utc)
    except (KeyError, ValueError):
        return None
    if at.timestamp() < now - 180 * 86400:  # "Jan 2" read in late December is next year
        at = at.replace(year=year + 1)
    return at.timestamp()


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)
