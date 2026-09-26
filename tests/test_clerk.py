import json, os, tempfile, unittest
from tests.fakes import FakePaperclip
from lib.paperclip import Paperclip
from lib.clerk import Clerk
from lib import pacer


class ClerkTests(unittest.TestCase):
    def setUp(self):
        self.fp = FakePaperclip()
        self.tmp = tempfile.TemporaryDirectory()
        self.prs = {}
        self.woken = []
        self.pc = Paperclip(self.fp.url, "k")
        self.pc.wake_agent = lambda a, fresh=True: self.woken.append((a, fresh)) or True
        self.fp.agents = [{"id": "a1", "name": "Builder-1"}, {"id": "dir", "name": "Director"}]

    def tearDown(self):
        self.fp.stop(); self.tmp.cleanup()

    def clerk(self, **kw):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda args: self.prs.get(args[args.index("--repo") + 1], []),
                  director_id="dir", principal_id="prin", **kw)
        c.gh_comment = lambda *a: self.gh_comments.append(a)
        return c

    gh_comments = []

    def statuses(self):
        return {i: v["status"] for i, v in self.fp.issues.items()}

    def test_merge_marks_done_and_unblocks_dependents(self):
        self.fp.add(id="w5", title="6d SEO", status="in_review", description="GitHub: o/r#31", assigneeAgentId="a1")
        self.fp.add(id="w6", title="7b", status="blocked", blockedByIssueIds=["w5"], assigneeAgentId="a1")
        self.prs["o/r"] = [{"number": 40, "state": "MERGED", "mergedAt": "2026-09-25", "headRefOid": "abc",
                            "statusCheckRollup": [{"conclusion": "SUCCESS"}], "url": "u"}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.statuses()["w5"], "done")
        self.assertTrue(any("Bring `main` into" in b for i, b in self.fp.comments if i == "w6"))
        c2 = self.clerk(); c2.tick()  # gate sees w5 done, unblocks w6
        self.assertEqual(self.statuses()["w6"], "todo")
        self.assertIn(("a1", True), self.woken)
        n = len(self.fp.comments); self.clerk().tick()  # idempotent
        self.assertEqual(len(self.fp.comments), n)

    def test_three_red_checks_escalate_to_principal_once(self):
        self.fp.add(id="t", title="Task", status="in_progress", description="GitHub: o/r#5", assigneeAgentId="a1")
        for sha in ("a", "b", "c", "c"):
            self.prs["o/r"] = [{"number": 1, "state": "OPEN", "headRefOid": sha, "statusCheckRollup": [{"conclusion": "FAILURE"}]}]
            self.clerk().tick()
        esc = [p for p in self.fp.patches if p[1].get("assigneeAgentId") == "prin"]
        self.assertEqual(len(esc), 1)

    def test_green_open_pr_goes_to_board_digest(self):
        self.fp.add(id="t", title="Task", status="in_review", description="GitHub: o/r#5")
        self.fp.add(id="inbox", title="Director inbox", status="todo")
        self.prs["o/r"] = [{"number": 9, "state": "OPEN", "headRefOid": "x", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}]
        self.clerk().tick()
        self.assertIn("Merge PR #9", self.fp.docs[("inbox", "digest")])
        self.assertLessEqual(len(self.fp.docs[("inbox", "digest")]), 6000)
        self.assertIn(("dir", True), self.woken)
        self.woken.clear(); self.prs["o/r"][0]["headRefOid"] = "x"
        self.clerk().tick()  # same situation: do not wake the Director again
        self.assertEqual(self.woken, [])

    def test_dry_run_writes_no_paperclip_state_and_wakes_nobody(self):
        self.fp.add(id="t", title="Task", status="in_review", description="GitHub: o/r#5")
        self.fp.add(id="w", title="W", status="blocked", blockedByIssueIds=["t"])
        self.prs["o/r"] = [{"number": 9, "state": "MERGED", "mergedAt": "x", "headRefOid": "x", "statusCheckRollup": []}]
        self.clerk(dry_run=True).tick()
        self.assertEqual((self.fp.patches, self.fp.comments, self.woken), ([], [], []))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "digest.md")))

    def test_accepted_plan_is_copied_to_github_and_wakes_builder(self):
        self.fp.add(id="t", title="Task", status="in_progress", description="GitHub: o/r#5", assigneeAgentId="a1")
        self.fp.docs[("t", "plan")] = "Step 1..."
        self.fp.interactions_["t"] = [{"id": "i1", "kind": "request_confirmation", "status": "accepted"}]
        c = self.clerk(); c.tick()
        self.assertEqual(self.gh_comments[-1][:2], ("o/r", "5"))
        self.assertIn(("a1", False), self.woken)

    def test_branch_search_uses_the_paperclip_identifier(self):
        seen = []
        self.fp.add(id="t", title="T", status="in_progress", identifier="AGE-7", description="GitHub: o/r#5")
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: seen.append(a[a.index("--search") + 1]) or [])
        c.tick()
        self.assertEqual(seen, ["head:agent/AGE-7-", "head:agent/5-"])

    def test_pending_plan_is_flagged_not_actioned(self):
        self.fp.add(id="t", title="Task", status="in_progress", assigneeAgentId="a1")
        self.fp.docs[("t", "plan")] = "x"
        self.fp.interactions_["t"] = [{"id": "i1", "kind": "request_confirmation", "status": "pending"}]
        c = self.clerk(); c.tick()
        self.assertNotIn(("a1", False), self.woken)
        self.assertNotIn(("a1", True), self.woken)
        self.assertIn("Plan confirmation waiting: Task", c.needs_board)

    def test_one_failing_step_does_not_stop_the_tick(self):
        self.fp.add(id="t", title="T", status="in_progress", description="GitHub: o/r#5")
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: 1 / 0)
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

    def quota(self, session, week):
        self.fp.quota = [{"provider": "anthropic", "ok": True, "windows": [
            {"label": "Current session", "usedPercent": session, "resetsAt": "2026-09-26T05:10:00+00:00"},
            {"label": "Current week (all models)", "usedPercent": week, "resetsAt": "2026-09-28T08:00:00+00:00"}]},
            {"provider": "openai", "ok": False, "windows": []}]

    def agents3(self):
        self.fp.agents = [{"id": "a1", "name": "Builder-1", "adapterType": "claude_local", "status": "idle"},
                          {"id": "a2", "name": "Principal", "adapterType": "claude_local", "status": "paused"},  # human-paused
                          {"id": "w", "name": "Worker", "adapterType": "process", "status": "idle"}]

    def test_usage_over_limit_pauses_claude_agents_only(self):
        self.agents3(); self.quota(session=90, week=50)
        c = self.clerk(); c.tick()
        self.assertEqual(self.fp.paused_calls, [("a1", "pause")])   # not the process agent, not the already-paused one
        self.assertEqual(c.state["paused_by_clerk"], ["a1"])
        self.assertIn("session allowance 90%", c.state["heavy_reason"])
        self.assertTrue(any("Usage allowance nearly used" in x for x in c.needs_board))

    def test_weekly_limit_ignored_by_default(self):
        self.agents3(); self.quota(session=10, week=99)
        self.clerk().tick()
        self.assertEqual(self.fp.paused_calls, [])

    def test_resumes_only_what_we_paused_when_usage_drops(self):
        self.agents3(); self.quota(session=95, week=50); self.clerk().tick()
        self.fp.paused_calls.clear(); self.quota(session=5, week=50)
        c = self.clerk(); c.tick()
        self.assertEqual(self.fp.paused_calls, [("a1", "resume")])  # Principal stays paused: a human did that
        self.assertEqual(c.state["paused_by_clerk"], [])
        self.assertIn("session 5%", c.state["usage"])

    def test_under_limits_or_unknown_usage_pauses_nothing(self):
        self.agents3(); self.quota(session=45, week=88); self.clerk().tick()
        self.fp.quota = []; self.clerk().tick()   # quota endpoint gives nothing usable
        self.assertEqual(self.fp.paused_calls, [])

    def test_pacer_dry_run_reports_but_pauses_nobody(self):
        self.agents3(); self.quota(session=99, week=99)
        c = self.clerk(dry_run=True); c.tick()
        self.assertEqual(self.fp.paused_calls, [])
        self.assertEqual(c.state["paused_by_clerk"], [])
        self.assertIn("paused", c.notes[0])

    def test_pacer(self):
        agents = {"a1": "Builder-1", "a2": "Builder-2", "p": "Principal"}
        runs = [{"agentId": "a1", "status": "running"}, {"agentId": "a2", "status": "running"}]
        st, heavy = pacer.update({}, runs, agents, now=1000)
        self.assertFalse(pacer.heavy_allowed(st, heavy, 1000)[0])
        st, heavy = pacer.update({}, [{"id": "r1", "agentId": "a1", "status": "failed", "error": "Claude usage limit reached"}], agents, now=1000)
        self.assertFalse(pacer.heavy_allowed(st, heavy, 1001)[0])
        self.assertTrue(pacer.heavy_allowed(st, 0, 1000 + 3601)[0])

    def test_weekly_export_and_cost_report(self):
        self.pc.export_company = lambda cid, out: True
        out = self.clerk().weekly()
        self.assertTrue(os.path.exists(os.path.join(out, "cost-report.json")))


if __name__ == "__main__":
    unittest.main()
