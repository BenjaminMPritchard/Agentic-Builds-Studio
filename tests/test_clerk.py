import json, os, tempfile, unittest
from tests.fakes import FakePaperclip
from lib.paperclip import Paperclip
from lib.clerk import Clerk
from lib import clerk as clerk_mod


class ClerkTests(unittest.TestCase):
    def setUp(self):
        self.fp = FakePaperclip()
        self.tmp = tempfile.TemporaryDirectory()
        self.prs = {}
        self.woken = []
        self.pc = Paperclip(self.fp.url, "k")
        self.pc.wake_agent = lambda a, fresh=True: self.woken.append((a, fresh)) or True
        self.fp.agents = [{"id": "a1", "name": "Builder-1"}, {"id": "dir", "name": "Director"}]
        # never read the host's real usage-cap ledger
        self._ledger, self._qdir = clerk_mod.QUOTA_LEDGER, clerk_mod.QUOTA_DIR
        clerk_mod.QUOTA_LEDGER = os.path.join(self.tmp.name, "no-ledger.json")
        clerk_mod.QUOTA_DIR = os.path.join(self.tmp.name, "quota")

    def tearDown(self):
        clerk_mod.QUOTA_LEDGER, clerk_mod.QUOTA_DIR = self._ledger, self._qdir
        self.fp.stop(); self.tmp.cleanup()

    def gh(self, args):
        repo = args[args.index("--repo") + 1]
        if args[:2] == ["pr", "view"]:
            return next((p for p in self.prs.get(repo, []) if p["number"] == int(args[2])), None)
        self.searches.append(args[args.index("--search") + 1])
        return self.prs.get(repo, [])

    searches = []

    def clerk(self, **kw):
        c = Clerk(self.pc, "co", self.tmp.name, gh=self.gh, director_id="dir", principal_id="prin", **kw)
        c.gh_comment = lambda *a: self.gh_comments.append(a)
        return c

    gh_comments = []

    def statuses(self):
        return {i: v["status"] for i, v in self.fp.issues.items()}

    def link(self, issue, repo, n):
        self.fp.products.setdefault(issue, []).append(
            {"id": f"wp-{issue}-{n}", "type": "pull_request", "provider": "github", "status": "ready_for_review",
             "url": f"https://github.com/{repo}/pull/{n}", "metadata": {"repo": repo, "number": n, "headRef": "b"}})

    def test_paperclip_owns_dependency_transitions(self):
        self.fp.add(id="w5", title="6d SEO", status="in_review", description="GitHub: o/r#31", assigneeAgentId="a1")
        self.fp.add(id="w6", title="7b", status="blocked", blockedByIssueIds=["w5"], assigneeAgentId="a1")
        self.link("w5", "o/r", 40)
        self.prs["o/r"] = [{"number": 40, "state": "MERGED", "mergedAt": "2026-09-25", "headRefOid": "abc",
                            "statusCheckRollup": [{"conclusion": "SUCCESS"}], "url": "u"}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.statuses()["w5"], "done")
        self.assertEqual(self.fp.products["w5"][0]["status"], "merged")
        self.assertTrue(any("Bring `main` into" in b for i, b in self.fp.comments if i == "w6"))
        c2 = self.clerk(); c2.tick()
        self.assertEqual(self.statuses()["w6"], "blocked")
        self.assertNotIn(("a1", True), self.woken)
        n = len(self.fp.comments); self.clerk().tick()  # idempotent
        self.assertEqual(len(self.fp.comments), n)

    def test_a_merge_on_an_issue_still_in_progress_goes_to_the_director(self):
        self.fp.add(id="t", title="Task", status="in_progress")
        self.link("t", "o/r", 7)
        self.prs["o/r"] = [{"number": 7, "state": "MERGED", "mergedAt": "x", "headRefOid": "a", "statusCheckRollup": []}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.statuses()["t"], "in_progress")
        self.assertTrue(any("decide whether it is done" in x for x in c.needs_director))

    def test_done_waits_for_every_recorded_pr(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.link("t", "o/r", 7); self.link("t", "o/r", 8)
        self.prs["o/r"] = [{"number": 7, "state": "MERGED", "mergedAt": "x", "headRefOid": "a", "statusCheckRollup": []},
                           {"number": 8, "state": "OPEN", "headRefOid": "b", "statusCheckRollup": []}]
        self.clerk().tick()
        self.assertEqual(self.statuses()["t"], "in_review")
        self.prs["o/r"][1].update(state="CLOSED")
        self.clerk().tick()
        self.assertEqual(self.statuses()["t"], "done")

    def test_studio_issues_without_a_github_line_are_followed_through_work_products(self):
        self.fp.add(id="t", title="Back-fill", status="in_review", identifier="AGE-9")
        self.link("t", "BenjaminMPritchard/Agentic-Builds-Studio", 33)
        self.prs["BenjaminMPritchard/Agentic-Builds-Studio"] = [
            {"number": 33, "state": "MERGED", "mergedAt": "x", "headRefOid": "a52db60", "statusCheckRollup": []}]
        self.clerk().tick()
        self.assertEqual(self.statuses()["t"], "done")

    def test_a_pr_found_only_by_branch_name_is_reported_not_actioned(self):
        self.searches.clear()
        self.fp.add(id="t", title="T", status="in_review", identifier="AGE-7", description="GitHub: o/r#5")
        self.prs["o/r"] = [{"number": 9, "state": "MERGED", "mergedAt": "x", "headRefOid": "x", "url": "u9"}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.searches, ["head:agent/AGE-7-", "head:agent/5-"])
        self.assertEqual((self.statuses()["t"], self.fp.comments), ("in_review", []))
        self.assertTrue(any("studio-record-pr t <PR URL>" in x for x in c.needs_director))
        c = self.clerk(); c.tick()
        self.assertEqual(c.needs_director, [])  # reported once

    def test_three_red_checks_escalate_to_principal_once(self):
        self.fp.add(id="t", title="Task", status="in_progress", assigneeAgentId="a1")
        self.link("t", "o/r", 1)
        for sha in ("a", "b", "c", "c"):
            self.prs["o/r"] = [{"number": 1, "state": "OPEN", "headRefOid": sha, "statusCheckRollup": [{"conclusion": "FAILURE"}]}]
            self.clerk().tick()
        esc = [p for p in self.fp.patches if p[1].get("assigneeAgentId") == "prin"]
        self.assertEqual(len(esc), 1)

    def test_green_open_pr_goes_to_the_director_not_the_board(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.fp.add(id="inbox", title="Director inbox", status="todo")
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "OPEN", "headRefOid": "x", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}]
        self.clerk(dry_run=True).tick()  # a dry-run tick must not use up the wake
        self.assertEqual(self.woken, [])
        self.clerk().tick()
        digest = self.fp.docs[("inbox", "digest")]
        self.assertIn("PR #9 (Task) is green: once reviewed, run the merge gate", digest)
        self.assertIn("## Needs you (Board)\n- nothing", digest)  # Benjamin merges only ready-for-benjamin PRs
        self.assertEqual(self.fp.comments, [])  # nothing for the agent to do, so no comment to wake it
        self.assertLessEqual(len(self.fp.docs[("inbox", "digest")]), 6000)
        self.assertIn(("dir", True), self.woken)
        self.woken.clear(); self.prs["o/r"][0]["headRefOid"] = "x"
        self.clerk().tick()  # same situation: do not wake the Director again
        self.assertEqual(self.woken, [])

    def test_red_checks_are_commented_so_the_agent_wakes_to_fix_them(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "OPEN", "headRefOid": "x", "statusCheckRollup": [{"conclusion": "FAILURE"}]}]
        self.clerk().tick()
        self.assertTrue(any(i == "t" and "checks red" in b for i, b in self.fp.comments))

    def test_dry_run_writes_nothing_and_keeps_no_receipts(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.fp.add(id="w", title="W", status="blocked", blockedByIssueIds=["t"])
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "MERGED", "mergedAt": "x", "headRefOid": "x", "statusCheckRollup": []}]
        for _ in range(2):
            self.clerk(dry_run=True).tick()
        self.assertEqual((self.fp.patches, self.fp.comments, self.woken), ([], [], []))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "digest.md")))
        self.clerk().tick()  # dry-run ends: what it saw is acted on now
        self.assertEqual(self.statuses()["t"], "done")
        self.assertTrue(any(i == "w" for i, _ in self.fp.comments))

    def test_one_unreadable_issue_does_not_hide_the_others(self):
        self.fp.add(id="bad", title="Old org", status="backlog", identifier="AGE-6", description="GitHub: gone/r#14")
        self.fp.add(id="t", title="Task", status="in_review")
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "MERGED", "mergedAt": "x", "headRefOid": "x", "statusCheckRollup": []}]
        gh = self.gh
        c = Clerk(self.pc, "co", self.tmp.name, director_id="dir", principal_id="prin",
                  gh=lambda a: (_ for _ in ()).throw(RuntimeError("HTTP 404")) if "gone/r" in a else gh(a))
        c.tick()
        self.assertEqual(self.statuses()["t"], "done")
        self.assertTrue(any(n.startswith("AGE-6: GitHub check failed: HTTP 404") for n in c.notes), c.notes)

    def test_a_failed_write_is_retried_next_tick(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "MERGED", "mergedAt": "x", "headRefOid": "x", "statusCheckRollup": []}]
        real = self.pc.patch_issue
        self.pc.patch_issue = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("paperclip down"))
        self.clerk().tick()
        self.assertEqual(self.statuses()["t"], "in_review")
        self.pc.patch_issue = real
        self.clerk().tick()
        self.assertEqual(self.statuses()["t"], "done")

    def test_accepted_plan_is_copied_to_github_and_wakes_builder(self):
        self.fp.add(id="t", title="Task", status="in_progress", description="GitHub: o/r#5", assigneeAgentId="a1")
        self.fp.docs[("t", "plan")] = "Step 1..."
        self.fp.interactions_["t"] = [{"id": "i1", "kind": "request_confirmation", "status": "accepted",
            "effectiveResolverPolicy": "human_only", "resolvedByUserId": "owner", "resolvedByAgentId": None,
            "payload": {"target": {"type": "issue_document", "key": "plan", "revisionId": "revision-1"}}}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.gh_comments[-1][:2], ("o/r", "5"))
        self.assertIn(("a1", False), self.woken)

    def test_pending_plan_is_flagged_not_actioned(self):
        self.fp.add(id="t", title="Task", status="in_progress", assigneeAgentId="a1")
        self.fp.docs[("t", "plan")] = "x"
        self.fp.interactions_["t"] = [{"id": "i1", "kind": "request_confirmation", "status": "pending",
            "payload": {"target": {"type": "issue_document", "key": "plan", "revisionId": "revision-1"}}}]
        c = self.clerk(); c.tick()
        self.assertNotIn(("a1", False), self.woken)
        self.assertNotIn(("a1", True), self.woken)
        self.assertIn("Plan confirmation waiting: Task", c.needs_board)

    def test_plan_gate_rejects_agent_or_stale_approval(self):
        self.fp.add(id="t", title="Task", status="in_progress", assigneeAgentId="a1")
        self.fp.docs[("t", "plan")] = "new plan"
        approval = {"id": "i1", "kind": "request_confirmation", "status": "accepted",
            "effectiveResolverPolicy": "human_only", "resolvedByUserId": "owner", "resolvedByAgentId": None,
            "payload": {"target": {"type": "issue_document", "key": "plan", "revisionId": "old"}}}
        self.fp.interactions_["t"] = [approval]
        self.clerk().tick()
        self.assertNotIn(("a1", False), self.woken)
        approval["payload"]["target"]["revisionId"] = "revision-1"
        approval["resolvedByUserId"] = None
        approval["resolvedByAgentId"] = "agent"
        self.clerk().tick()
        self.assertNotIn(("a1", False), self.woken)

    def test_issue_list_paginates_bare_arrays(self):
        for n in range(205):
            self.fp.add(id=f"t{n}", title="Task", status="todo")
        self.assertEqual(len(self.pc.list_issues("co")), 205)

    def test_one_failing_step_does_not_stop_the_tick(self):
        self.fp.add(id="t", title="T", status="in_progress", description="GitHub: o/r#5")
        self.pc.get_document = lambda *a: 1 / 0  # the plan step fails as a whole
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [])
        c.tick()
        log = open(os.path.join(self.tmp.name, "log", "studio.jsonl")).read()
        self.assertIn("step_error", log); self.assertIn('"event": "digest"', log)

    def test_client_matches_live_api_shapes(self):
        self.fp.add(id="t", title="T", status="todo")
        self.pc.put_document("t", "digest", "hello")          # 400 from the fake unless format=markdown
        self.assertEqual(self.pc.get_document("t", "digest")["body"], "hello")
        self.pc.checkout("t", agent_id="a1")                   # 400 unless agentId+expectedStatuses
        from lib.paperclip import Paperclip
        real = Paperclip(self.fp.url, "k")
        self.assertTrue(real.wake_agent("a1", fresh=True))
        self.assertEqual(self.fp.wakes[-1][1]["forceFreshSession"], True)

    def test_usage_caps_are_reported_and_no_agent_is_paused(self):
        self.fp.agents = [{"id": "a1", "name": "Builder-1", "adapterType": "claude_local", "status": "idle"}]
        ledger = os.path.join(self.tmp.name, "claude.json")
        with open(ledger, "w") as f:
            json.dump({"last": {"t": 0, "five_hour": {"pct": 40, "key": "1pm"}, "week": {"pct": 22, "key": "Mon"}},
                       "studio": {"five_hour": {"1pm": 4.5}, "week": {"Mon": 1.5}}, "active": {}, "samples": {}}, f)
        old = clerk_mod.QUOTA_LEDGER
        try:
            clerk_mod.QUOTA_LEDGER = ledger
            c = self.clerk(now=lambda: 600); c.tick()
            self.assertIn("Claude studio use 4.5 of 22 points this 5-hour window (resets 1pm), 1.5 of 80 this week",
                          c.state["usage"])
            self.assertIn("reading 10 min old", c.state["usage"])
            clerk_mod.QUOTA_LEDGER = os.path.join(self.tmp.name, "missing.json")
            c = self.clerk(); c.tick()
            self.assertIn("no usage-cap ledger yet", c.state["usage"])
        finally:
            clerk_mod.QUOTA_LEDGER = old
        self.assertEqual(self.fp.paused_calls, [])

    def test_finished_runs_are_recorded_once_and_reported(self):
        self.fp.agents = [{"id": "a1", "name": "Scout"}]
        self.fp.add(id="t", title="Triage", status="done")
        self.fp.runs_ = [
            {"id": "r1", "agentId": "a1", "status": "succeeded", "createdAt": "2026-09-30T03:20:50Z",
             "startedAt": "2026-09-30T03:20:55Z", "finishedAt": "2026-09-30T03:23:25Z",
             "contextSnapshot": {"issueId": "t", "wakeReason": "issue_assigned"},
             "usageJson": {"model": "claude-haiku-4-5-20251001", "billingType": "subscription_included",
                           "inputTokens": 57416, "outputTokens": 11682, "costUsd": 0.28}},
            {"id": "r2", "agentId": "a1", "status": "running", "createdAt": "2026-09-30T03:30:00Z"}]
        os.makedirs(os.path.join(self.tmp.name, "quota"))
        with open(os.path.join(self.tmp.name, "quota", "claude-runs.jsonl"), "w") as f:
            f.write(json.dumps({"run": "r1", "agent": "a1", "used": {"five_hour": 2.0, "week": 0.5},
                                "attribution": "bounded", "ended": "released", "windows": {}}) + "\n")
        for _ in range(2):
            self.clerk(dry_run=True).tick()  # records are evidence, written in dry-run too; once per run
        recs = [json.loads(l) for l in open(os.path.join(self.tmp.name, "records", "runs.jsonl"))]
        self.assertEqual([r["run"] for r in recs], ["r1"])  # the running one waits until it finishes
        self.assertEqual(recs[0]["studio_usage"]["five_hour"], 2.0)
        self.assertEqual(recs[0]["tokens"], {"inputTokens": 57416, "outputTokens": 11682})
        text = open(self.clerk().report()).read()
        self.assertIn("| Scout | claude-haiku-4-5-20251001 | 1 | 1 / 0 / 0 | 2.5 / 2.5 | 2 / 0.5 (n=1) | – | 11682 | 1 / 0 / 0 |", text)

    def test_weekly_export_and_cost_report(self):
        self.pc.export_company = lambda cid, out: True
        out = self.clerk().weekly()
        self.assertTrue(os.path.exists(os.path.join(out, "cost-report.json")))


class ClerkGitHubIdentity(unittest.TestCase):
    """The Clerk's gh calls use the agents' App token for the repository's owner, not a personal token."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = os.path.join(self.tmp.name, "agents-app.json")
        clerk_mod._tokens.clear()
        self.minted, self.t = [], 1000.0

    def tearDown(self):
        self.tmp.cleanup(); clerk_mod._tokens.clear()

    def env(self, repo):
        def mint(owner, app_id, key_path):
            self.minted.append((owner, app_id, key_path))
            return f"ghs_{owner}_{len(self.minted)}"
        old = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
        os.environ.update(GH_TOKEN="personal", GITHUB_TOKEN="personal")
        try:
            return clerk_mod.gh_env(repo, config=self.config, mint=mint, now=lambda: self.t)
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    def configure(self):
        with open(self.config, "w") as f:
            json.dump({"app_id": 5110225, "key_path": "/etc/studio/agents-app.pem"}, f)

    def test_without_app_config_the_environment_is_inherited(self):
        self.assertIsNone(self.env("o/r"))
        self.assertEqual(self.minted, [])

    def test_app_token_for_the_repo_owner_replaces_personal_tokens(self):
        self.configure()
        env = self.env("Agentic-Builds-Studio-Client-Pages/site")
        self.assertEqual(env["GH_TOKEN"], "ghs_Agentic-Builds-Studio-Client-Pages_1")
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertEqual(self.minted, [("Agentic-Builds-Studio-Client-Pages", 5110225, "/etc/studio/agents-app.pem")])

    def test_tokens_are_reused_per_owner_until_near_expiry(self):
        self.configure()
        self.env("a/one"); self.env("a/two"); self.env("b/three")
        self.assertEqual([m[0] for m in self.minted], ["a", "b"])
        self.t += 49 * 60
        self.env("a/one")
        self.assertEqual(len(self.minted), 2)
        self.t += 2 * 60
        self.assertEqual(self.env("a/one")["GH_TOKEN"], "ghs_a_3")

    def test_both_gh_calls_use_the_repo_environment(self):
        from unittest import mock
        calls = []
        def run(cmd, **kw):
            calls.append((cmd, kw.get("env")))
            return mock.Mock(returncode=0, stdout="[]", stderr="")
        with mock.patch.object(clerk_mod, "gh_env", lambda repo: {"GH_TOKEN": "app-" + repo}), \
             mock.patch.object(clerk_mod.subprocess, "run", run):
            clerk_mod.gh_json(["pr", "list", "--repo", "o/r"])
            Clerk.gh_comment(None, "o/s", "5", "body")
        self.assertEqual([c[1] for c in calls], [{"GH_TOKEN": "app-o/r"}, {"GH_TOKEN": "app-o/s"}])

    def test_no_token_means_the_call_fails(self):
        self.configure()
        def mint(*a):
            raise clerk_mod.github_app.GitHubAppError("HTTP 404")
        with self.assertRaises(clerk_mod.github_app.GitHubAppError):
            clerk_mod.gh_env("o/r", config=self.config, mint=mint)


class EnsureReview(unittest.TestCase):
    """2026-10-02: tasks with no reviewer could not reach the merge gate, so every PR fell to Benjamin."""
    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "b1", "name": "Builder-1"}, {"id": "pr", "name": "Principal"},
                          {"id": "cp", "name": "Codex-Principal"}, {"id": "dir", "name": "Director"}]
        self.policy = {"projects": {"mothers": {"enabled": True}, "off": {"enabled": False}}}

    def run_(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [])
        c.ensure_review(list(self.fp.issues.values()), {}, policy=self.policy)
        c.save()

    def test_a_builders_task_gets_the_principal_as_reviewer_once(self):
        self.fp.add(id="t1", identifier="AGE-24", title="6d-3", status="in_progress", projectId="mothers", assigneeAgentId="b1")
        self.fp.add(id="t2", identifier="AGE-30", title="7b", status="todo", projectId="mothers", assigneeAgentId="pr")
        self.run_(); self.run_()
        stages = {i: b["executionPolicy"]["stages"][0]["participants"][0]["agentId"] for i, b in self.fp.patches}
        self.assertEqual(stages, {"t1": "pr", "t2": "cp"})  # the Principal's own work goes to Codex-Principal
        self.assertEqual(len(self.fp.patches), 2)

    def test_left_alone_when_reviewed_already_not_code_not_authorised_or_not_active(self):
        self.fp.add(id="a", title="x", status="in_progress", projectId="mothers", assigneeAgentId="b1",
                    executionPolicy={"mode": "normal", "stages": []})
        self.fp.add(id="b", title="x", status="in_progress", projectId="mothers", assigneeAgentId="dir")
        self.fp.add(id="c", title="x", status="in_progress", projectId="off", assigneeAgentId="b1")
        self.fp.add(id="d", title="x", status="backlog", projectId="mothers", assigneeAgentId="b1")
        self.run_()
        self.assertEqual(self.fp.patches, [])

class ResumeCapped(unittest.TestCase):
    """2026-10-02: agents refused by a usage cap were left in error by Paperclip and nothing woke them after the
    window reset, so the Studio stayed stopped all night."""

    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.pc.wake_agent = Paperclip.wake_agent.__get__(self.pc)  # the real call, recorded by the fake
        self.fp.agents = [{"id": "a1", "name": "Builder-1", "status": "error"},
                          {"id": "p1", "name": "Principal", "status": "paused"}]
        self.t = 1_759_400_000  # 2025-10-02T10:13:20Z

    def refused(self, agent, minutes_ago, rid):
        import datetime
        at = datetime.datetime.fromtimestamp(self.t - minutes_ago * 60, datetime.timezone.utc)
        iso = at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        return {"id": rid, "agentId": agent, "status": "failed", "createdAt": iso, "finishedAt": iso,
                "error": "Claude exited with code 5: studio-quota: claude cap reached; not starting: ...",
                "contextSnapshot": {"issueId": "w1"}}

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.t)
        c.resume_capped([], {})
        c.save()

    def test_an_agent_refused_by_a_cap_is_woken_on_its_issue_once(self):
        self.fp.runs_ = [self.refused("a1", 30, "r1")]
        self.tick(); self.tick()
        self.assertEqual(len(self.fp.wakes), 1)
        agent, body = self.fp.wakes[0]
        self.assertEqual((agent, body["source"], body["payload"]), ("a1", "assignment", {"issueId": "w1"}))

    def test_not_too_soon_not_paused_and_not_after_a_later_run(self):
        self.fp.runs_ = [self.refused("a1", 5, "r1"), self.refused("p1", 60, "r2")]
        self.tick()
        self.assertEqual(self.fp.wakes, [])  # 5 minutes is too soon; a paused agent is left alone
        later = {**self.refused("a1", 1, "r3"), "status": "succeeded", "error": None}
        self.fp.runs_ = [self.refused("a1", 30, "r1"), later]
        self.tick()
        self.assertEqual(self.fp.wakes, [])  # its latest run is not a refusal


if __name__ == "__main__":
    unittest.main()
