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

from lib import deploy, github_app, merge_gate, notify, quota, records, watchdog

GH_LINK = re.compile(r"GitHub:\s*([\w.-]+/[\w.-]+)#(\d+)")
RED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE"}
RED_LIMIT = 3
CAP_REFUSED = re.compile(r"studio-quota: \w+ cap reached")
RESUME_AFTER = 20 * 60  # seconds after a cap refusal before the agent is woken to try again
DIGEST_MAX_CHARS = 6000  # about 1,500 tokens
RECEIPT_DAYS = 60
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
                 principal_id=None, recorder_id=None, now=time.time, deploy_repo=None, infra_project_id=None):
        self.pc, self.cid, self.data, self.gh, self.dry = pc, company_id, data_dir, gh, dry_run
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
        for step in (self.deploy_sync, self.github_sync, self.plan_gate, self.ensure_review, self.caps, self.resume_capped,
                     self.watchdog, self.record_runs, self.digest):
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
            # The Director runs the merge gate; Benjamin hears only of PRs the gate labels ready-for-benjamin
            # (2026-10-02: this line used to ask him to merge every green PR, so he merged them before review).
            if not self.seen(f"review-ready:{iid}:{pr.get('headRefOid')}"):
                self.notes.append(f"{issue['title']}: PR #{n} green, waiting for review/merge")
                self.needs_director.append(f"PR #{n} ({issue['title']}) is green: once reviewed, run the merge gate")

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
        when it sets one, is never replaced."""
        try:
            policy = policy or merge_gate.load_policy()
        except (OSError, ValueError):
            return
        projects = {pid for pid, p in (policy.get("projects") or {}).items() if isinstance(p, dict) and p.get("enabled")}
        agents = {a["id"]: a.get("name", "") for a in self.pc.list_agents(self.cid)}
        by_name = {n: i for i, n in agents.items()}
        for i in issues:
            who = agents.get(i.get("assigneeAgentId"), "")
            if i.get("projectId") not in projects or i.get("status") not in ("todo", "in_progress") \
                    or i.get("executionPolicy") or not self.BUILDING.match(who):
                continue
            reviewer = by_name.get("Codex-Principal" if who == "Principal" else "Principal")
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

    def resume_capped(self, issues, by_id):
        """Wake an agent whose latest run was refused by a usage cap, once per refusal, 20 minutes after it.
        Paperclip retries a refused run a few times and then leaves the agent in error; nothing woke it after
        the window reset, so the Studio stayed stopped all night (2026-10-02). The wake goes through admission
        again: if there is still no room it is refused once more, and that new refusal is woken 20 minutes later.
        A refusal costs one usage reading, no model use. Paused agents are left alone."""
        agents = {a["id"]: a for a in self.pc.list_agents(self.cid)}
        latest = {}
        for r in self.pc.runs(self.cid, limit=200):
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
