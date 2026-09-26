"""The Clerk: scripts only, no LLM. One `tick` runs each step below; every step is idempotent
and isolated (an error in one is logged and does not stop the rest).

Assumed issue fields (TODO(check) against the live API): id, title, status, assigneeAgentId,
blockedByIssueIds, description (with a line `GitHub: owner/repo#N`), projectId.
Statuses used: backlog/todo/in_progress/in_review/blocked/done.
"""
import hashlib
import json
import os
import re
import subprocess
import time

from lib import deploy, pacer

GH_LINK = re.compile(r"GitHub:\s*([\w.-]+/[\w.-]+)#(\d+)")
RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"}
RED_LIMIT = 3
DIGEST_MAX_CHARS = 6000  # about 1,500 tokens


def gh_json(args):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError(r.stderr.strip()[:200])
    return json.loads(r.stdout or "null")


class Clerk:
    def __init__(self, pc, company_id, data_dir, gh=gh_json, dry_run=False, director_id=None,
                 principal_id=None, recorder_id=None, now=time.time, deploy_repo=None, infra_project_id=None):
        self.pc, self.cid, self.data, self.gh, self.dry = pc, company_id, data_dir, gh, dry_run
        self.director, self.principal, self.recorder, self.now = director_id, principal_id, recorder_id, now
        self.deploy_repo, self.infra_project = deploy_repo, infra_project_id
        self.state_path = os.path.join(data_dir, "clerk-state.json")
        self.state = pacer.load(self.state_path)
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

    def seen(self, key):
        """True if key was already handled; otherwise marks it (persisted by save())."""
        done = self.state.setdefault("done", {})
        if key in done:
            return True
        done[key] = int(self.now())
        return False

    def save(self):
        pacer.save(self.state_path, self.state)

    # ---- the tick -----------------------------------------------------------------
    def tick(self):
        issues = self.pc.list_issues(self.cid)
        by_id = {i["id"]: i for i in issues}
        for step in (self.deploy_sync, self.github_sync, self.gates, self.plan_gate, self.pace, self.digest):
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
        for i in issues:
            m = GH_LINK.search(i.get("description") or "")
            if not m or i.get("status") in ("done", "cancelled"):
                continue
            repo, num = m.groups()
            # Paperclip names branches agent/<issue identifier>-<slug> (e.g. agent/AGE-3-pallet-cleanup).
            prefix = i.get("identifier") or num
            prs = self.gh(["pr", "list", "--repo", repo, "--state", "all", "--search", f"head:agent/{prefix}-",
                           "--json", "number,state,mergedAt,headRefOid,statusCheckRollup,url"])
            for pr in prs or []:
                self.pr_state(i, pr)

    def pr_state(self, issue, pr):
        iid, n = issue["id"], pr["number"]
        checks = pr.get("statusCheckRollup") or []
        red = any((c.get("conclusion") or c.get("state")) in RED for c in checks)
        pending = any(not (c.get("conclusion") or c.get("state")) or (c.get("status") or "") in ("IN_PROGRESS", "QUEUED") for c in checks)
        label = "merged" if pr.get("mergedAt") else pr["state"].lower()
        label += " · checks red" if red else (" · checks running" if pending else " · checks green" if checks else "")
        if not self.seen(f"pr:{iid}:{n}:{pr.get('headRefOid')}:{label}"):
            self.act("comment", self.pc.comment, iid, f"[Clerk] PR #{n} is {label}. {pr.get('url', '')}")
        if red and not self.seen(f"red:{iid}:{pr.get('headRefOid')}"):
            self.state.setdefault("red", {})[iid] = self.state.get("red", {}).get(iid, 0) + 1
            self.log("check_red", task=iid, pr=n)
            if self.state["red"][iid] >= RED_LIMIT and not self.seen(f"escalate:{iid}") and self.principal:
                self.act("escalate", self.pc.patch_issue, iid, assigneeAgentId=self.principal,
                         comment=f"[Clerk] {RED_LIMIT} red check runs. Handing to the Principal.")
                self.notes.append(f"{issue['title']}: 3 red checks, handed to the Principal")
        if pr.get("mergedAt") and not self.seen(f"merged:{iid}"):
            self.act("done", self.pc.patch_issue, iid, status="done")
            self.log("merged", task=iid, pr=n)
            for d in [x for x in self._all if iid in (x.get("blockedByIssueIds") or [])]:
                self.act("bring-main-in", self.pc.comment, d["id"],
                         f"[Clerk] '{issue['title']}' merged. Bring `main` into your branch before continuing.")
        elif pr["state"] == "OPEN" and not red and not pending and checks:
            if not self.seen(f"review-ready:{iid}:{pr.get('headRefOid')}"):
                self.notes.append(f"{issue['title']}: PR #{n} green, waiting for review/merge")
                self.needs_board.append(f"Merge PR #{n} ({issue['title']}) once reviewed")

    @property
    def _all(self):
        return self.pc.list_issues(self.cid)

    # ---- 3: dependency gate ---------------------------------------------------------
    def gates(self, issues, by_id):
        for i in issues:
            deps = i.get("blockedByIssueIds") or []
            if i.get("status") == "blocked" and deps and all(by_id.get(d, {}).get("status") == "done" for d in deps):
                if not self.seen(f"unblock:{i['id']}"):
                    self.act("unblock", self.pc.patch_issue, i["id"], status="todo")
                    if i.get("assigneeAgentId"):
                        self.act("wake", self.pc.wake_agent, i["assigneeAgentId"], fresh=True)
                    self.log("unblocked", task=i["id"])

    # ---- 3b: accepted plan -> copy to GitHub, wake the builder -------------------------
    def plan_gate(self, issues, by_id):
        for i in issues:
            if i.get("status") in ("done", "cancelled"):
                continue
            plan = self.pc.get_document(i["id"], "plan")
            if not plan:
                continue
            reqs = [x for x in self.pc.interactions(i["id"]) if x.get("kind", x.get("type")) == "request_confirmation"]
            if not (reqs and reqs[-1].get("status") == "accepted"):
                if reqs and reqs[-1].get("status") == "pending":
                    self.needs_board.append(f"Plan confirmation waiting: {i['title']}")
                continue
            if self.seen(f"plan:{i['id']}:{reqs[-1].get('id', len(reqs))}"):
                continue
            m = GH_LINK.search(i.get("description") or "")
            if m:
                body = plan.get("body", "") if isinstance(plan, dict) else str(plan)
                self.act("plan->github", self.gh_comment, m.group(1), m.group(2), "Approved plan:\n\n" + body)
            if i.get("assigneeAgentId"):
                self.act("wake", self.pc.wake_agent, i["assigneeAgentId"], fresh=False)

    def gh_comment(self, repo, num, body):
        subprocess.run(["gh", "issue", "comment", num, "--repo", repo, "--body", body], check=True, timeout=60)

    # ---- 4: pacer ----------------------------------------------------------------------
    def pace(self, issues, by_id):
        """Pause every Claude agent while the real 5-hour or weekly allowance is nearly used; resume the
        ones we paused (never ones a human paused) once it is not. A recent usage-limit failure also holds."""
        agents = self.pc.list_agents(self.cid)
        names = {a["id"]: a.get("name", "") for a in agents}
        st, heavy = pacer.update(self.state, self.pc.runs(self.cid), names, self.now())
        self.state = st
        failure_ok, failure_why = pacer.heavy_allowed(st, heavy, self.now())
        try:
            win = pacer.parse_windows(self.pc.quota_windows(self.cid))
        except Exception as e:
            win = {}
            self.log("quota_error", error=str(e)[:200])
        decision = pacer.decide(win)
        reasons = decision["reasons"] + ([] if failure_ok or not st.get("hold_until", 0) > self.now() else [failure_why])
        hold = bool(reasons)
        self.state["usage"] = pacer.describe(win)
        self.state["heavy_allowed"] = not hold
        self.state["heavy_reason"] = "; ".join(reasons) if hold else (failure_why if not failure_ok else "ok")
        ours = set(self.state.get("paused_by_clerk", []))
        claude = [a for a in agents if a.get("adapterType") == "claude_local"]
        if hold:
            for a in claude:
                if a.get("status") != "paused":
                    self.act("pause", self.pc.pause_agent, a["id"])
                    if not self.dry:
                        ours.add(a["id"])
            self.notes.append("Pacer: Claude agents paused. " + self.state["heavy_reason"])
            self.needs_board.append("Usage allowance nearly used; agents paused until it resets: " + self.state["heavy_reason"])
        else:
            still = {a["id"]: a for a in agents}
            for aid in list(ours):
                if still.get(aid, {}).get("status") == "paused":
                    self.act("resume", self.pc.resume_agent, aid)
                ours.discard(aid) if not self.dry else None
            if heavy >= pacer.MAX_HEAVY:
                self.notes.append(f"Pacer: {heavy} heavy runs active (max {pacer.MAX_HEAVY}); not enforced, only reported")
        self.state["paused_by_clerk"] = sorted(ours)
        self.log("pacer", hold=hold, usage=self.state["usage"], dry=self.dry)

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
        lines.append(f"Usage: {self.state.get('usage', 'n/a')}. Pacer: {self.state.get('heavy_reason', 'n/a')}")
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
