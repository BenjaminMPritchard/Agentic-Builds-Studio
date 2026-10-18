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

    def test_green_open_pr_wakes_nobody(self):
        self.fp.add(id="t", title="Task", status="in_review")
        self.fp.add(id="inbox", title="Director inbox", status="todo")
        self.link("t", "o/r", 9)
        self.prs["o/r"] = [{"number": 9, "state": "OPEN", "headRefOid": "x", "statusCheckRollup": [{"conclusion": "SUCCESS"}]}]
        self.clerk().tick()
        digest = self.fp.docs[("inbox", "digest")]
        self.assertIn("Task: PR #9 green, waiting for review", digest)
        self.assertIn("## Needs you (Board)\n- nothing", digest)  # Benjamin merges only ready-for-benjamin PRs
        self.assertEqual(self.fp.comments, [])  # nothing for the agent to do, so no comment to wake it
        self.assertNotIn(("dir", True), self.woken)  # the Clerk asks the merge gate once the review approves
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

    # ---- the Clerk asks the merge gate about approved, green PRs (Benjamin, 2026-10-10) ----
    GATE_POLICY = {"version": 1, "projects": {"mothers": {
        "enabled": True, "repo": "o/r", "base_branch": "main", "merge_method": "merge", "authority_classes": ["A", "B"],
        "required_checks": ["check"], "required_approvals": 1, "trusted_reviewers": [], "protected_paths": [],
        "mergeable_paths": [], "authorised_by": "Benjamin", "authorised_on": "2026-09-30"}}}

    def approved(self, **kw):
        issue = dict(id="t", title="Task", status="done", projectId="mothers", updatedAt="2026-10-10T20:00:00Z",
                     executionPolicy={"stages": [{"id": "s1", "type": "review"}]},
                     executionState={"status": "completed", "lastDecisionOutcome": "approved",
                                     "completedStageIds": ["s1"]})
        issue.update(kw)
        self.fp.add(**issue)
        self.link(issue["id"], "o/r", 9)

    def gate_clerk(self, result=(True, [], True), **kw):
        calls = []
        policy = lambda: self.GATE_POLICY
        def gate(pc, request, do_merge=False):
            calls.append((request, do_merge))
            return result
        c = self.clerk(gate=gate, merge_policy=policy, now=lambda: 1791676800, **kw)  # 2026-10-11
        return c, calls

    def green(self, sha="h1", checks=({"conclusion": "SUCCESS"},)):
        self.prs["o/r"] = [{"number": 9, "state": "OPEN", "headRefOid": sha, "statusCheckRollup": list(checks)}]

    def test_an_approved_green_pr_goes_to_the_merge_gate_once_per_head(self):
        self.approved(); self.green()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [({"issue_id": "t", "repo": "o/r", "pr": 9, "head_sha": "h1"}, True)])
        self.assertIn("Task: PR #9 merged by the merge gate", c.notes)
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [])  # same head: not asked again
        self.green(sha="h2")
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(len(calls), 1)  # a new head is a new question

    def test_the_review_policy_is_read_from_the_issue_when_the_list_leaves_it_out(self):
        # 2026-10-12: Paperclip's issue list omits executionPolicy, so the gate was never asked for any task.
        self.approved(); self.green()
        full = self.pc.list_issues
        self.pc.list_issues = lambda cid: [{k: v for k, v in i.items() if k not in ("executionPolicy", "executionState")}
                                           for i in full(cid)]
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(len(calls), 1)

    def test_the_gate_is_not_asked_without_an_approved_review(self):
        self.approved(executionState={"status": "pending", "completedStageIds": []}); self.green()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [])

    def test_the_gate_is_not_asked_for_a_task_without_a_review_stage(self):
        self.approved(executionPolicy=None); self.green()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [])

    def test_the_gate_is_not_asked_for_a_project_the_policy_does_not_authorise(self):
        self.approved(projectId="studio"); self.green()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [])

    def test_the_gate_is_not_asked_while_checks_are_red_or_running(self):
        self.approved()
        for checks in ([{"conclusion": "FAILURE"}], [{"status": "IN_PROGRESS"}], []):
            self.green(checks=checks)
            c, calls = self.gate_clerk(); c.tick()
            self.assertEqual(calls, [], checks)

    def test_old_approvals_are_left_alone(self):
        self.approved(updatedAt="2026-09-01T00:00:00Z"); self.green()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(calls, [])

    def test_a_protected_path_refusal_is_noted_and_other_refusals_go_to_the_director(self):
        self.approved(); self.green()
        c, _ = self.gate_clerk(result=(False, ["pull request touches protected path backend/core/models.py"], False))
        c.tick()
        self.assertIn("Task: PR #9 labelled ready-for-benjamin (touches protected files)", c.notes)
        self.green(sha="h2")
        c, _ = self.gate_clerk(result=(False, ["changes were requested"], False)); c.tick()
        self.assertIn("PR #9 (Task): the merge gate refused: changes were requested", c.needs_director)

    def test_unreadable_evidence_is_asked_again_next_tick(self):
        self.approved(); self.green()
        c, calls = self.gate_clerk(result=(False, ["could not collect evidence: OSError: x"], False)); c.tick()
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(len(calls), 1)

    def test_a_dry_run_never_asks_the_gate(self):
        self.approved(); self.green()
        c, calls = self.gate_clerk(dry_run=True); c.tick()
        self.assertEqual(calls, [])
        c, calls = self.gate_clerk(); c.tick()
        self.assertEqual(len(calls), 1)  # the dry run used up nothing



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

    def test_codex_principal_reviews_everything_while_claudes_week_is_used_up(self):
        # 2026-10-04: the account reached 99% of its week; reviews by the Principal would wait for the reset.
        ledger = os.path.join(self.tmp.name, "claude.json")
        with open(ledger, "w") as f:
            json.dump({"last": {"t": 0, "five_hour": {"pct": 0, "key": "x"}, "week": {"pct": 99.4, "key": "Mon"}},
                       "studio": {"five_hour": {}, "week": {"Mon": 39}}, "active": {}, "samples": {}}, f)
        clerk_mod.QUOTA_LEDGER = ledger
        self.fp.add(id="t1", identifier="AGE-24", title="6d-3", status="in_progress", projectId="mothers", assigneeAgentId="b1")
        self.run_()
        self.assertEqual(self.fp.patches[0][1]["executionPolicy"]["stages"][0]["participants"][0]["agentId"], "cp")

    def test_a_review_policy_missing_only_from_the_issue_list_is_kept(self):
        self.fp.add(id="t1", identifier="AGE-6", title="7a", status="in_progress", projectId="mothers", assigneeAgentId="pr",
                    executionPolicy={"mode": "normal", "stages": [{"type": "review"}, {"type": "review"}]})
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [])
        c.ensure_review([{**self.fp.issues["t1"], "executionPolicy": None}], {}, policy=self.policy)  # as the list shows it
        self.assertEqual(self.fp.patches, [])

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


class UnblockCapped(unittest.TestCase):
    """2026-10-11: Paperclip blocks an issue whose runs a usage cap refused, and nothing unblocked it after the
    window reset, so every reset needed a person."""

    tearDown = ClerkTests.tearDown
    NOTE = "Paperclip retried this issue's run after it ended without finishing, but the bounded retry budget is spent"

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "b", "name": "Codex-Builder", "status": "error"},
                          {"id": "p", "name": "Principal", "status": "paused"}]
        self.t = 1_791_689_600  # 2026-10-11T03:33:20Z

    def refusal(self, rid, issue, resets="Oct 11 02:58 UTC", provider="codex", minutes_ago=60):
        import datetime
        iso = datetime.datetime.fromtimestamp(self.t - minutes_ago * 60, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
        return {"id": rid, "agentId": "b", "status": "failed", "createdAt": iso, "finishedAt": iso,
                "error": f"studio-quota: {provider} cap reached; not starting: studio 5-hour: used 34 + reserved 0 "
                         f"+ this run 14 + margin 1 = 49 > 28 (resets {resets})",
                "contextSnapshot": {"issueId": issue}}

    def blocked(self, iid, assignee="b", **kw):
        self.fp.add(id=iid, identifier=iid.upper(), title=iid, status="blocked", assigneeAgentId=assignee, **kw)
        self.fp.comments.append((iid, self.NOTE))

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.t)
        c.unblock_capped(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()

    def test_a_cap_blocked_issue_is_unblocked_once_after_the_reset(self):
        self.blocked("w1")
        self.fp.runs_ = [self.refusal("r1", "w1")]
        self.tick(); self.tick()
        unblocks = [p for p in self.fp.patches if p[1].get("status") == "todo"]
        self.assertEqual([p[0] for p in unblocks], ["w1"])
        self.assertIn("usage caps refused", unblocks[0][1]["comment"])

    def test_not_before_the_reset(self):
        self.blocked("w1")
        self.fp.runs_ = [self.refusal("r1", "w1", resets="Oct 11 04:10 UTC")]
        self.tick()
        self.assertEqual(self.fp.patches, [])

    def test_claude_reset_text_is_read(self):
        self.blocked("w1")
        self.fp.runs_ = [self.refusal("r1", "w1", resets="Oct 11, 3:20am (Europe/London)", provider="claude")]
        self.tick()  # 03:20 BST is 02:20 UTC, an hour before now
        self.assertEqual(len(self.fp.patches), 1)

    def test_left_alone_when_not_only_a_cap_block(self):
        self.blocked("paused", assignee="p")  # a paused assignee is a human pause
        self.blocked("open_blocker", blockedBy=[{"id": "x", "status": "in_progress"}])
        self.blocked("later_comment")
        self.fp.comments.append(("later_comment", "Blocked: waiting for Benjamin's decision"))
        self.blocked("ran_later")
        later = {**self.refusal("r9", "ran_later", minutes_ago=1), "status": "succeeded", "error": None}
        self.fp.add(id="not_blocked", title="t", status="todo", assigneeAgentId="b")
        self.fp.runs_ = [self.refusal("r1", "paused"), self.refusal("r2", "open_blocker"),
                         self.refusal("r3", "later_comment"), self.refusal("r4", "ran_later", minutes_ago=90), later,
                         self.refusal("r5", "not_blocked")]
        self.tick()
        self.assertEqual(self.fp.patches, [])

    def test_an_unreadable_reset_waits_a_whole_window(self):
        self.blocked("w1")
        self.fp.runs_ = [self.refusal("r1", "w1", resets="unknown", minutes_ago=60)]
        self.tick()
        self.assertEqual(self.fp.patches, [])
        self.fp.runs_ = [self.refusal("r1", "w1", resets="unknown", minutes_ago=303)]
        self.tick()
        self.assertEqual(len(self.fp.patches), 1)


class StuckToDirector(unittest.TestCase):
    """2026-10-13: refurb part 2 (AGE-63) sat blocked from 2026-10-11 after Paperclip's own repair ran out, with
    nothing open blocking it, and nobody was asked to decide."""

    tearDown = ClerkTests.tearDown
    T = 1_791_890_000  # 2026-10-13T09:13:20Z

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "b", "name": "Codex-Builder", "status": "idle"},
                          {"id": "p", "name": "Principal", "status": "paused"},
                          {"id": "dir", "name": "Director", "status": "idle"}]

    def iso(self, hours_ago):
        import datetime
        return datetime.datetime.fromtimestamp(self.T - hours_ago * 3600, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")

    def blocked(self, iid, assignee="b", hours_ago=30, note="Paperclip exhausted the bounded original-owner repair", **kw):
        self.fp.add(id=iid, identifier=iid.upper(), title=iid, status="blocked", assigneeAgentId=assignee,
                    updatedAt=self.iso(hours_ago), **kw)
        self.fp.comments.append((iid, note))

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T, director_id="dir")
        issues = list(self.fp.issues.values())
        c.stuck_to_director(issues, dict(self.fp.issues))
        return c.needs_director

    def test_a_long_stuck_task_goes_to_the_director(self):
        self.blocked("w1")
        need = self.tick()
        self.assertEqual(len(need), 1)
        self.assertIn("W1 (w1), Codex-Builder", need[0])
        self.assertIn("Paperclip exhausted", need[0])
        self.assertEqual(self.fp.patches, [])  # the Clerk decides nothing itself

    def test_the_same_list_twice_reads_the_same_so_the_director_is_woken_once(self):
        self.blocked("w1")
        self.assertEqual(self.tick(), self.tick())

    def test_left_alone(self):
        self.blocked("recent", hours_ago=2)
        self.blocked("directors", assignee="dir")
        self.blocked("paused", assignee="p")
        self.blocked("persons", assignee=None)
        self.blocked("open_blocker", blockedBy=[{"id": "x", "status": "in_progress"}])
        self.blocked("capped")
        self.blocked("review", executionState={"status": "pending", "currentParticipant": {"agentId": "p"}})
        self.blocked("card")
        self.fp.interactions_["card"] = [{"id": "c1", "status": "pending", "resolverPolicy": "human_only"}]
        self.fp.runs_ = [{"id": "r1", "agentId": "b", "status": "failed", "createdAt": self.iso(1),
                          "error": "studio-quota: codex cap reached; not starting", "contextSnapshot": {"issueId": "capped"}}]
        self.assertEqual(self.tick(), [])


if __name__ == "__main__":
    unittest.main()


class RestartReviews(unittest.TestCase):
    """2026-10-12: Paperclip woke each reviewer once; the usage cap refused the run and #86, #93 and #94 waited a
    day for a review while Codex had its whole week unused."""

    tearDown = ClerkTests.tearDown
    T = 1_791_840_000  # 2026-10-12T19:20:00Z

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "prin", "name": "Principal", "status": "idle"},
                          {"id": "cx", "name": "Codex-Principal", "status": "idle"},
                          {"id": "b", "name": "Builder-1", "status": "idle"}]
        self.woken = []
        self.pc.wake_agent = lambda a, fresh=True, reason="", issue=None: self.woken.append((a, issue)) or True

    def iso(self, minutes_ago):
        import datetime
        return datetime.datetime.fromtimestamp(self.T - minutes_ago * 60, datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")

    def review(self, iid, status="in_review", reviewer="prin", stages=None):
        stages = stages or [{"id": "s1", "type": "review", "participants": [{"type": "agent", "agentId": reviewer}]}]
        self.fp.add(id=iid, identifier=iid.upper(), title=iid, status=status, assigneeAgentId="b",
                    updatedAt=self.iso(120), executionPolicy={"mode": "normal", "stages": stages},
                    executionState={"status": "pending", "currentStageType": "review",
                                    "currentParticipant": {"type": "agent", "agentId": reviewer}})

    def a_run(self, rid, agent, issue, minutes_ago, status="failed", capped=True):
        return {"id": rid, "agentId": agent, "status": status, "createdAt": self.iso(minutes_ago),
                "finishedAt": self.iso(minutes_ago), "contextSnapshot": {"issueId": issue},
                "error": "studio-quota: claude cap reached; not starting: studio 5-hour" if capped else None}

    def tick(self, t=None):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: t or self.T)
        c.restart_reviews(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()

    def reviewers(self, iid):
        return [p["agentId"] for s in self.fp.issues[iid]["executionPolicy"]["stages"] for p in s["participants"]]

    def test_a_capped_reviewer_hands_the_review_to_the_other_principal_once(self):
        self.review("r1")
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60)]
        self.tick(); self.tick()
        self.assertEqual(self.reviewers("r1"), ["cx"])
        self.assertEqual(self.woken, [("cx", "r1")])

    def test_the_other_principal_counts_as_free_once_its_refusal_window_has_reset(self):
        self.review("r1")  # 2026-10-13: AGE-81's review stayed on the capped Principal while Codex was free
        old = {**self.a_run("x2", "cx", "other", 50),
               "error": "studio-quota: codex cap reached; not starting: studio 5-hour: used 32 (resets Oct 12 19:00 UTC)"}
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60), old]
        self.tick()
        self.assertEqual(self.reviewers("r1"), ["cx"])

    def test_an_uncapped_reviewer_is_woken_again(self):
        self.review("r1")
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        self.tick()
        self.assertEqual(self.reviewers("r1"), ["prin"])
        self.assertEqual(self.woken, [("prin", "r1")])

    def test_the_other_principal_is_not_used_when_it_already_reviews_this_task(self):
        self.review("r1", stages=[{"id": "s1", "type": "review", "participants": [{"type": "agent", "agentId": "cx"}]},
                                  {"id": "s2", "type": "review", "participants": [{"type": "agent", "agentId": "prin"}]}])
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60)]
        self.tick()
        self.assertEqual(self.reviewers("r1"), ["cx", "prin"])
        self.assertEqual(self.woken, [("prin", "r1")])

    def test_a_stage_paperclip_gave_up_on_is_restored(self):
        self.review("r1", status="blocked")
        self.fp.comments.append(("r1", "Paperclip retried the pending execution-review participant once, but ..."))
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        self.tick()
        self.assertEqual([p[1]["executionPolicy"]["stages"][0]["participants"][0]["agentId"]
                          for p in self.fp.patches if "executionPolicy" in p[1]], ["cx", "prin"])
        self.assertEqual(self.woken, [("prin", "r1")])

    def test_a_stage_paperclip_gave_up_on_is_restored_after_someone_comments(self):
        # 2026-10-16: the Director commented on AGE-64 after Paperclip blocked its review, and the review sat all morning
        self.review("r1", status="blocked")
        self.fp.comments.append(("r1", "Director: the fix task is done; Codex-Principal re-checks B3."))
        self.fp.activity_["r1"] = [
            {"action": "issue.comment_added", "createdAt": self.iso(70), "actorType": "agent", "details": {}},
            {"action": "issue.updated", "createdAt": self.iso(80), "actorType": "system",
             "details": {"source": "recovery.reconcile_execution_review_participant", "status": "blocked"}}]
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        self.tick()
        self.assertEqual(self.woken, [("prin", "r1")])

    def test_a_review_an_agent_blocked_is_left_alone(self):
        self.review("r1", status="blocked")
        self.fp.comments.append(("r1", "Blocked: waiting for packet 5"))
        self.fp.activity_["r1"] = [
            {"action": "issue.updated", "createdAt": self.iso(70), "actorType": "agent",
             "details": {"source": "comment", "changes": {"status": {"from": "in_review", "to": "blocked"}}}},
            {"action": "issue.updated", "createdAt": self.iso(80), "actorType": "system",
             "details": {"source": "recovery.reconcile_execution_review_participant", "status": "blocked"}}]
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        self.tick()
        self.assertEqual(self.woken, [])

    def test_left_alone(self):
        self.review("live"); self.review("recent"); self.review("person_blocked", status="blocked")
        self.fp.comments.append(("person_blocked", "Blocked: waiting for Benjamin"))
        self.review("merged")
        self.fp.products["merged"] = [{"type": "pull_request", "status": "merged"}]
        self.fp.runs_ = [self.a_run("x0", "prin", "merged", 90),
                         self.a_run("x1", "prin", "live", 5, status="running", capped=False),
                         self.a_run("x2", "prin", "recent", 10), self.a_run("x3", "prin", "person_blocked", 90)]
        self.tick()
        self.assertEqual((self.woken, self.fp.patches), ([], []))


    def test_a_review_paperclip_will_not_start_goes_to_the_director_once(self):
        # 2026-10-16: AGE-64 was held for reconciliation; every wake was skipped and the Clerk commented every 30 min
        self.review("r1", status="blocked")
        self.fp.comments.append(("r1", "Paperclip retried the pending execution-review participant once, but ..."))
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        def held(a, fresh=True, reason="", issue=None):
            self.woken.append((a, issue))
            self.pc.last_skip = "execution_reconciliation_required"
            return False
        self.pc.wake_agent = held
        for t in (self.T, self.T + 3600):
            c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: t)
            c.restart_reviews(list(self.fp.issues.values()), dict(self.fp.issues))
            c.save()
            self.fp.issues["r1"]["updatedAt"] = self.iso(-60)  # the restore patch moves it on
            if t == self.T:
                self.assertEqual(len(c.needs_director), 1)
                self.assertIn("Replace it", c.needs_director[0])
        self.assertEqual(self.woken, [("prin", "r1")])
        self.assertEqual([b for i, b in self.fp.comments if i == "r1" and b.startswith("[Clerk]")], [])


    def test_a_wake_skipped_for_another_reason_is_not_a_hold(self):
        # 2026-10-17: AGE-92's wake was skipped (another wake was pending) and the Director was told to replace it
        self.review("r1", status="blocked")
        self.fp.comments.append(("r1", "Paperclip retried the pending execution-review participant once, but ..."))
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="cancelled", capped=False)]
        def skipped(a, fresh=True, reason="", issue=None):
            self.pc.last_skip = "wakeup_skipped"
            return False
        self.pc.wake_agent = skipped
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T)
        c.restart_reviews(list(self.fp.issues.values()), dict(self.fp.issues))
        self.assertEqual(c.needs_director, [])

    def test_a_reviewer_the_ledger_shows_out_of_room_counts_as_capped(self):
        # 2026-10-17: the Principal's latest run succeeded and left Claude at 21 of 22; its reviews stayed with it
        os.makedirs(clerk_mod.QUOTA_DIR, exist_ok=True)
        ledger = {"last": {"t": self.T, "five_hour": {"pct": 30.0, "key": "K", "at": self.T + 3600},
                           "week": {"pct": 50.0, "key": "W", "at": self.T + 86400}},
                  "studio": {"five_hour": {"K": 21.0}, "week": {"W": 40.0}}, "active": {}, "samples": {}}
        with open(os.path.join(clerk_mod.QUOTA_DIR, "claude.json"), "w") as f:
            json.dump(ledger, f)
        self.review("r1")
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 60, status="succeeded", capped=False)]
        self.tick()
        self.assertEqual(self.reviewers("r1"), ["cx"])

    def test_a_capped_reviewer_hands_over_without_waiting_for_the_stall(self):
        # 2026-10-17: each 20-minute cap refusal restarted the 30-minute stall, so AGE-92 never moved
        self.review("r1")
        self.fp.runs_ = [self.a_run("x1", "prin", "r1", 2)]
        self.tick()
        self.assertEqual(self.reviewers("r1"), ["cx"])

    def test_a_ledger_from_before_the_reset_is_not_out_of_room(self):
        os.makedirs(clerk_mod.QUOTA_DIR, exist_ok=True)
        ledger = {"last": {"t": self.T - 7200, "five_hour": {"pct": 30.0, "key": "K", "at": self.T - 60},
                           "week": {"pct": 50.0, "key": "W", "at": self.T + 86400}},
                  "studio": {"five_hour": {"K": 21.0}, "week": {"W": 40.0}}, "active": {}, "samples": {}}
        with open(os.path.join(clerk_mod.QUOTA_DIR, "claude.json"), "w") as f:
            json.dump(ledger, f)
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T)
        self.assertFalse(c.window_out("claude", "prin"))

class SkippedWakes(unittest.TestCase):
    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.pc = Paperclip(self.fp.url, "k")

    def test_a_wake_paperclip_skips_is_not_a_wake(self):
        self.assertTrue(self.pc.wake_agent("a1", issue_id="t"))
        self.fp.wake_reply = {"status": "skipped", "reason": "execution_reconciliation_required"}
        self.assertFalse(self.pc.wake_agent("a1", issue_id="t"))
        self.assertEqual(self.pc.last_skip, "execution_reconciliation_required")


class ResumeAfterMerge(unittest.TestCase):
    """2026-10-17: refurb part 4 (AGE-65) waited, blocked, for #102 to merge, and stayed blocked after it did."""
    tearDown = ClerkTests.tearDown
    POLICY = {"version": 1, "projects": {"mothers": {
        "enabled": True, "repo": "o/r", "base_branch": "main", "merge_method": "merge", "authority_classes": ["A", "B"],
        "required_checks": ["check"], "required_approvals": 1, "trusted_reviewers": [], "protected_paths": [],
        "mergeable_paths": [], "authorised_by": "Benjamin", "authorised_on": "2026-09-30"}}}

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "cb", "name": "Codex-Builder", "status": "idle"}, {"id": "dir", "name": "Director"}]
        self.woken = []
        self.pc.wake_agent = lambda a, fresh=True, reason="", issue=None: self.woken.append((a, issue)) or True
        self.state = {102: "MERGED", 7: "OPEN"}

    def gh(self, args):
        return {"number": int(args[2]), "state": self.state.get(int(args[2]), "OPEN")}

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=self.gh, merge_policy=lambda: self.POLICY, director_id="dir")
        c.resume_after_merge(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()

    def waiting(self, iid, note, **kw):
        self.fp.add(**{"id": iid, "identifier": iid.upper(), "title": iid, "status": "blocked",
                       "assigneeAgentId": "cb", "projectId": "mothers", **kw})
        self.fp.comments.append((iid, note))

    def statuses(self, iid):
        return [p[1].get("status") for p in self.fp.patches if p[0] == iid]

    def test_a_task_waiting_for_a_merged_pr_resumes_once(self):
        self.waiting("w", "Director: PR #102 (packet 3) waits for Benjamin's merge; resume when #102 merges.")
        self.tick(); self.tick()
        self.assertEqual(self.statuses("w"), ["todo"])
        self.assertEqual(self.woken, [("cb", "w")])

    def test_left_alone(self):
        self.waiting("open", "Waiting for PR #7 to merge.")
        self.waiting("some_open", "Waiting for #102 and #7 to merge.")
        self.waiting("no_merge_word", "PR #102 needs a rebase first.")
        self.waiting("no_pr", "Waiting for AGE-64 to merge.")
        self.waiting("director", "Waiting for #102 to merge.", assigneeAgentId="dir")
        self.waiting("other_project", "Waiting for #102 to merge.", projectId="studio")
        self.waiting("blocker_open", "Waiting for #102 to merge.", blockedBy=[{"id": "x", "status": "todo"}])
        self.tick()
        self.assertEqual((self.fp.patches, self.woken), ([], []))


class ResumeThroughDeadRetries(unittest.TestCase):
    tearDown = ClerkTests.tearDown
    T = RestartReviews.T
    iso, a_run = RestartReviews.iso, RestartReviews.a_run

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "prin", "name": "Principal", "status": "error"}]
        self.woken = []
        self.pc.wake_agent = lambda a, fresh=True, reason="", issue=None: self.woken.append((a, issue)) or True

    def retry(self, due_minutes_ago):
        return {"id": "s1", "agentId": "prin", "status": "scheduled_retry", "createdAt": self.iso(25),
                "scheduledRetryAt": self.iso(due_minutes_ago), "contextSnapshot": {"issueId": "t"}}

    def test_a_stale_scheduled_retry_does_not_hide_the_refusal_under_it(self):
        # AGE-77: the latest run was a retry due at 02:53 that never started, on top of cap refusals.
        self.fp.runs_ = [self.a_run("f1", "prin", "t", 30), self.retry(due_minutes_ago=24)]
        Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T).resume_capped([], {})
        self.assertEqual(self.woken, [("prin", "t")])

    def test_a_retry_not_yet_due_still_counts(self):
        self.fp.runs_ = [self.a_run("f1", "prin", "t", 30), self.retry(due_minutes_ago=-5)]
        Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T).resume_capped([], {})
        self.assertEqual(self.woken, [])


class ReviewsStayWithAgents(unittest.TestCase):
    """2026-10-13: after three change-request rounds Paperclip handed AGE-60's review to Benjamin, and only a
    browser-console request could move it. Benjamin, 2026-10-14: reviews never wait on him."""

    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "b", "name": "Codex-Builder"}, {"id": "cp", "name": "Codex-Principal"},
                          {"id": "dir", "name": "Director"}]
        self.review = {"mode": "normal", "stages": [{"id": "s1", "type": "review",
                                                     "participants": [{"type": "agent", "agentId": "cp"}]}]}

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], director_id="dir")
        c.reviews_stay_with_agents(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()
        return c.needs_director

    def test_every_review_policy_gets_the_high_round_limit_once_and_keeps_its_stages(self):
        self.fp.add(id="t1", identifier="AGE-75", title="x", status="in_review", executionPolicy=self.review)
        self.tick(); self.tick()
        self.assertEqual(len(self.fp.patches), 1)
        sent = self.fp.patches[0][1]["executionPolicy"]
        self.assertEqual(sent["maxReviewRounds"], clerk_mod.REVIEW_ROUNDS_MAX)
        self.assertEqual(sent["stages"], self.review["stages"])  # same stage ids, so the review state carries on

    def test_a_review_that_bounced_twice_goes_to_the_director(self):
        self.fp.add(id="t1", identifier="AGE-52", title="countdown", status="in_progress",
                    executionPolicy={**self.review, "maxReviewRounds": clerk_mod.REVIEW_ROUNDS_MAX},
                    executionState={"status": "changes_requested", "currentStageType": "review", "changesRequestedCount": 2,
                                    "returnAssignee": {"type": "agent", "agentId": "b"}})
        need = self.tick()
        self.assertEqual(len(need), 1)
        self.assertIn("AGE-52 (countdown): the review has bounced 2 times between Codex-Builder and Codex-Principal", need[0])
        self.assertEqual(self.fp.patches, [])

    def test_a_review_already_handed_to_a_person_is_freed_and_goes_to_the_director(self):
        # AGE-75 sat with the Clerk's own user from 2026-10-14 11:46: the higher limit ends Paperclip's hold.
        self.fp.add(id="held", identifier="AGE-75", title="x", status="in_review", executionPolicy=self.review,
                    executionState={"status": "pending", "currentStageType": "review", "changesRequestedCount": 3,
                                    "currentParticipant": {"type": "user", "userId": "clerk"},
                                    "returnAssignee": {"type": "agent", "agentId": "b"}})
        need = self.tick()
        self.assertEqual(self.fp.patches[0][1]["executionPolicy"]["maxReviewRounds"], clerk_mod.REVIEW_ROUNDS_MAX)
        self.assertIn("AGE-75 (x): the review has bounced 3 times", need[0])

    def test_left_alone(self):
        self.fp.add(id="plan", title="x", status="in_review",
                    executionPolicy={"mode": "normal", "stages": [{"id": "a", "type": "approval", "participants": []}]})
        self.fp.add(id="done", title="x", status="done", executionPolicy=self.review)
        self.fp.add(id="once", title="x", status="in_progress",
                    executionPolicy={**self.review, "maxReviewRounds": clerk_mod.REVIEW_ROUNDS_MAX},
                    executionState={"currentStageType": "review", "changesRequestedCount": 1})
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.fp.patches, [])


class DirectorWakesOnInbox(unittest.TestCase):
    """2026-10-15: four Director runs decided all six stuck tasks and Paperclip refused every write
    (cross_issue_influence_run_context_required): the Clerk woke it on no task, and its inbox was parked blocked."""

    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.pc.wake_agent = Paperclip.wake_agent.__get__(self.pc)  # the real call, recorded by the fake
        self.fp.agents = [{"id": "dir", "name": "Director", "status": "idle"}]
        self.fp.add(id="inbox", title="Director inbox", status="blocked", blockedByIssueIds=["x"])

    def test_the_digest_wake_reopens_the_inbox_and_runs_on_it(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], director_id="dir")
        c.needs_director = ["AGE-63: stuck"]
        c.digest(list(self.fp.issues.values()), dict(self.fp.issues))
        self.assertEqual(self.fp.wakes[0][0], "dir")
        self.assertEqual(self.fp.wakes[0][1]["payload"], {"issueId": "inbox"})
        self.assertEqual((self.fp.issues["inbox"]["status"], self.fp.issues["inbox"]["blockedByIssueIds"]), ("todo", []))

    def test_a_capped_director_is_woken_on_its_inbox(self):
        t = 1_759_400_000
        import datetime
        iso = datetime.datetime.fromtimestamp(t - 1800, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        self.fp.runs_ = [{"id": "r1", "agentId": "dir", "status": "failed", "createdAt": iso, "finishedAt": iso,
                          "error": "studio-quota: claude cap reached; not starting", "contextSnapshot": {}}]
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: t, director_id="dir")
        c.resume_capped(list(self.fp.issues.values()), {})
        self.assertEqual(self.fp.wakes[0][1]["payload"], {"issueId": "inbox"})


class DirectorInboxNotWatched(unittest.TestCase):
    """2026-10-15: the watchdog put the Director's own comment on its parked inbox on the digest as a new
    "blocked" line every time, and that woke the Director again (22 wakes in 4 hours)."""

    tearDown = ClerkTests.tearDown

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "dir", "name": "Director", "status": "idle"}]

    def test_a_blocked_inbox_is_not_reported(self):
        self.fp.add(id="inbox", identifier="AGE-3", title="Director inbox", status="blocked", assigneeAgentId="dir",
                    updatedAt="2026-10-15T12:16:00.000Z")
        self.fp.comments.append(("inbox", "Director, digest of 13:05: no change."))
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], director_id="dir")
        c.watchdog(list(self.fp.issues.values()), dict(self.fp.issues))
        self.assertEqual(c.needs_board, [])


class SpareCodex(unittest.TestCase):
    """2026-10-18: Codex stood at 67 of 100 with six days to its weekly reset and would have stopped every Codex task."""
    tearDown = ClerkTests.tearDown
    T = 1_800_000_000

    def setUp(self):
        ClerkTests.setUp(self)
        self.fp.agents = [{"id": "cb", "name": "Codex-Builder", "status": "idle"},
                          {"id": "b1", "name": "Builder-1", "status": "idle"},
                          {"id": "b2", "name": "Builder-2", "status": "idle"}]

    def ledger(self, account_week, studio_week, days):
        os.makedirs(clerk_mod.QUOTA_DIR, exist_ok=True)
        ledger = {"last": {"t": self.T, "five_hour": {"pct": 10.0, "key": "K", "at": self.T + 3600},
                           "week": {"pct": account_week, "key": "W", "at": self.T + days * 86400}},
                  "studio": {"five_hour": {"K": 5.0}, "week": {"W": studio_week}}, "active": {}, "samples": {}}
        with open(os.path.join(clerk_mod.QUOTA_DIR, "codex.json"), "w") as f:
            json.dump(ledger, f)

    def tick(self):
        c = Clerk(self.pc, "co", self.tmp.name, gh=lambda a: [], now=lambda: self.T)
        c.spare_codex(list(self.fp.issues.values()), dict(self.fp.issues))
        c.save()
        return c

    def moves(self):
        return [(p[0], p[1]["assigneeAgentId"]) for p in self.fp.patches if "assigneeAgentId" in p[1]]

    def test_waiting_codex_tasks_move_to_the_least_busy_claude_builder_once(self):
        self.ledger(67.0, 52.0, 5.9)  # 32.5 left over 5.9 days: 5.5 a day, under 10
        self.fp.add(id="busy", identifier="AGE-1", title="b1 work", status="todo", assigneeAgentId="b1")
        self.fp.add(id="t", identifier="AGE-91", title="t", status="blocked", assigneeAgentId="cb")
        self.fp.add(id="u", identifier="AGE-94", title="u", status="todo", assigneeAgentId="cb")
        self.fp.add(id="run", identifier="AGE-90", title="r", status="in_progress", assigneeAgentId="cb")
        self.fp.add(id="held", identifier="AGE-9", title="h", status="todo", assigneeAgentId="cb", checkoutRunId="x")
        c = self.tick()
        self.tick()
        self.assertEqual(self.moves(), [("t", "b2"), ("u", "b1")])
        self.assertIn("moves from Codex-Builder to Builder-2", next(p[1]["comment"] for p in self.fp.patches if p[0] == "t"))
        self.assertEqual(len(c.needs_director), 2)

    def test_left_alone_while_the_week_lasts_or_without_a_current_reading(self):
        self.fp.add(id="t", identifier="AGE-91", title="t", status="todo", assigneeAgentId="cb")
        self.ledger(40.0, 30.0, 5.0)  # 59.5 over 5 days: 11.9 a day
        self.tick()
        self.ledger(90.0, 80.0, -0.1)  # a reading from before the reset says nothing
        self.tick()
        self.assertEqual(self.moves(), [])
