import copy
import json
import os
import tempfile
import unittest
from unittest import mock

from lib import merge_gate
from lib.merge_gate import evaluate, collect, run

SHA = "a" * 40
SHA2 = "b" * 40
R = "Org/Site"

BASE_POLICY = {"version": 1, "company_id": "c", "projects": {"p": {
    "enabled": True, "repo": R, "base_branch": "main", "merge_method": "squash", "authority_classes": ["A", "B"],
    "required_checks": ["check"], "required_approvals": 1, "trusted_reviewers": ["rev"], "protected_paths": [],
    "authorised_by": "Benjamin", "authorised_on": "2026-09-28"}}}

BASE_ISSUE = {"id": "i", "identifier": "AGE-3", "companyId": "c", "projectId": "p", "status": "in_review",
              "description": "- **Authority:** A\n- **Engineering risk:** low\n", "blockedBy": [],
              "executionPolicy": None, "executionState": None,
              "workProducts": [
                  {"type": "pull_request", "provider": "github", "status": "ready_for_review",
                   "url": f"https://github.com/{R}/pull/7",
                   "metadata": {"repo": R, "number": 7, "headRef": "agent/AGE-3-x", "baseRef": "main"}},
                  {"type": "commit", "provider": "github", "status": "active",
                   "metadata": {"repo": R, "sha": SHA, "branch": "agent/AGE-3-x"}}]}

BASE_EV = {"issue": BASE_ISSUE, "plan": None, "interactions": [], "activity": [],
           "pr": {"number": 7, "state": "open", "draft": False, "merged": False, "base_repo": R, "head_repo": R,
                  "base_ref": "main", "head_ref": "agent/AGE-3-x", "head_sha": SHA, "author": "bot", "labels": [],
                  "mergeable": True, "mergeable_state": "clean", "changed_files": 1},
           "files": [{"filename": "src/a.py", "previous_filename": None}],
           "check_runs": [{"name": "check", "head_sha": SHA, "status": "completed", "conclusion": "success"}],
           "statuses": [], "reviews": [{"user": "rev", "state": "APPROVED", "commit_id": SHA}]}

BASE_REQ = {"issue_id": "i", "repo": R.lower(), "pr": 7, "head_sha": SHA}

VALID_B_APPROVAL = {"kind": "request_confirmation", "status": "accepted", "effectiveResolverPolicy": "human_only",
                     "resolvedByUserId": "u1", "resolvedByAgentId": None,
                     "payload": {"target": {"type": "issue_document", "key": "plan", "revisionId": "rev-2"}}}
VALID_B_PLAN = {"body": "**Scope paths:** src/**", "latestRevisionId": "rev-2"}


def policy():
    return copy.deepcopy(BASE_POLICY)


def ev():
    return copy.deepcopy(BASE_EV)


def req():
    return copy.deepcopy(BASE_REQ)


class Base(unittest.TestCase):
    def test_base_fixture_allowed(self):
        self.assertEqual(evaluate(policy(), req(), ev()), [])

    def assertRefused(self, mutate, contains, pol=None, rq=None):
        """`mutate` receives the evidence dict and mutates it in place."""
        e = ev()
        mutate(e)
        reasons = evaluate(pol or policy(), rq or req(), e)
        self.assertTrue(reasons, "expected refusal")
        self.assertTrue(any(contains in r for r in reasons), reasons)


class Cases(Base):
    # 1
    def test_policy_projects_empty(self):
        p = policy(); p["projects"] = {}
        self.assertRefused(lambda e: None, "not authorised for this project", pol=p)

    # 2
    def test_project_enabled_false(self):
        p = policy(); p["projects"]["p"]["enabled"] = False
        self.assertRefused(lambda e: None, "not authorised for this project", pol=p)

    # 3
    def test_policy_version_not_1(self):
        p = policy(); p["version"] = 2
        self.assertRefused(lambda e: None, "merge policy is missing or malformed", pol=p)

    # 4
    def test_policy_field_missing(self):
        p = policy(); del p["projects"]["p"]["required_checks"]
        self.assertRefused(lambda e: None, "required_checks", pol=p)

    # 5
    def test_issue_company_id_differs(self):
        self.assertRefused(lambda e: e["issue"].__setitem__("companyId", "other"),
                            "different Paperclip company")

    # 6
    def test_request_repo_differs_from_policy_repo(self):
        rq = req(); rq["repo"] = "org/other"
        self.assertRefused(lambda e: None, "not the one authorised for this project", rq=rq)

    # 7
    def test_authority_line_missing(self):
        self.assertRefused(lambda e: e["issue"].__setitem__("description", "- **Engineering risk:** low\n"),
                            "must state its Authority")

    # 8
    def test_authority_stated_twice(self):
        self.assertRefused(
            lambda e: e["issue"].__setitem__(
                "description", "- **Authority:** A\n- **Authority:** B\n- **Engineering risk:** low\n"),
            "must state its Authority")

    # 9
    def test_authority_human(self):
        self.assertRefused(
            lambda e: e["issue"].__setitem__(
                "description", "- **Authority:** HUMAN\n- **Engineering risk:** low\n"),
            "cannot merge autonomously")

    # 10
    def test_authority_unfilled_template(self):
        self.assertRefused(
            lambda e: e["issue"].__setitem__(
                "description", "- **Authority:** A | B | HUMAN\n- **Engineering risk:** low\n"),
            "cannot merge autonomously")

    # 11
    def test_class_b_not_in_policy_authority_classes(self):
        p = policy(); p["projects"]["p"]["authority_classes"] = ["A"]

        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
        self.assertRefused(mutate, "does not authorise autonomous merge for class B", pol=p)

    # 12
    def test_packet_says_a_but_plan_exists(self):
        self.assertRefused(lambda e: e.__setitem__("plan", {"body": "x", "latestRevisionId": "rev-1"}),
                            "packet says A")

    # 13
    def test_b_with_no_plan(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = None
        self.assertRefused(mutate, "B work has no plan document")

    # 14
    def test_b_plan_confirmation_accepted_but_resolved_by_agent(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = copy.deepcopy(VALID_B_PLAN)
            approval = copy.deepcopy(VALID_B_APPROVAL)
            approval["resolvedByAgentId"] = "agent-1"
            e["interactions"] = [approval]
        self.assertRefused(mutate, "no accepted human-only confirmation")

    # 15
    def test_b_confirmation_effective_resolver_policy_anyone(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = copy.deepcopy(VALID_B_PLAN)
            approval = copy.deepcopy(VALID_B_APPROVAL)
            approval["effectiveResolverPolicy"] = "anyone"
            e["interactions"] = [approval]
        self.assertRefused(mutate, "no accepted human-only confirmation")

    # 16
    def test_b_confirmation_targets_older_revision(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = copy.deepcopy(VALID_B_PLAN)
            approval = copy.deepcopy(VALID_B_APPROVAL)
            approval["payload"]["target"]["revisionId"] = "rev-1"
            e["interactions"] = [approval]
        self.assertRefused(mutate, "no accepted human-only confirmation")

    # 17
    def test_any_pending_interaction(self):
        self.assertRefused(lambda e: e.__setitem__("interactions", [{"status": "pending"}]),
                            "unresolved confirmation")

    # 18
    def test_issue_status_in_progress(self):
        self.assertRefused(lambda e: e["issue"].__setitem__("status", "in_progress"), "not in_review")

    # 19
    def test_blocked_by_not_done(self):
        self.assertRefused(lambda e: e["issue"].__setitem__("blockedBy", [{"status": "open"}]),
                            "unresolved blockers")

    # 20
    def test_execution_state_pending(self):
        def mutate(e):
            e["issue"]["executionPolicy"] = {"stages": [{"id": "s1"}]}
            e["issue"]["executionState"] = {"status": "pending", "completedStageIds": [], "lastDecisionOutcome": None}
        self.assertRefused(mutate, "review policy is not complete")

    # 21
    def test_no_pr_work_product(self):
        def mutate(e):
            e["issue"]["workProducts"] = [w for w in e["issue"]["workProducts"] if w["type"] != "pull_request"]
        self.assertRefused(mutate, "exactly this pull request as its only open PR work product")

    # 22
    def test_two_open_pr_work_products(self):
        def mutate(e):
            extra = copy.deepcopy(e["issue"]["workProducts"][0])
            extra["url"] = f"https://github.com/{R}/pull/8"
            extra["metadata"]["number"] = 8
            e["issue"]["workProducts"].append(extra)
        self.assertRefused(mutate, "exactly this pull request as its only open PR work product")

    # 23
    def test_pr_url_metadata_disagree(self):
        def mutate(e):
            e["issue"]["workProducts"][0]["metadata"]["number"] = 99
        self.assertRefused(mutate, "exactly this pull request as its only open PR work product")

    # 24
    def test_work_product_headref_differs_from_pr(self):
        self.assertRefused(lambda e: e["issue"]["workProducts"][0]["metadata"].__setitem__("headRef", "agent/AGE-3-y"),
                            "branch differs from the branch recorded")

    # 25
    def test_no_commit_work_product_with_expected_sha(self):
        self.assertRefused(lambda e: e["issue"]["workProducts"][1]["metadata"].__setitem__("sha", SHA2),
                            "does not record the expected head SHA")

    # 26
    def test_branch_not_agent_identifier_pattern(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("head_ref", "feature/x"), "is not agent/AGE-3-")

    # 27
    def test_head_repo_is_a_fork(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("head_repo", "someone/fork"), "fork or wrong base")

    # 28
    def test_base_ref_not_policy_base_branch(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("base_ref", "develop"), "pull request targets develop")

    # 29
    def test_pr_draft(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("draft", True), "not open and ready")

    # 30
    def test_pr_closed(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("state", "closed"), "not open and ready")

    # 31
    def test_head_sha_stale(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("head_sha", SHA2), "head moved")

    # 32
    def test_mergeable_none(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("mergeable", None), "cleanly mergeable")

    # 33
    def test_mergeable_state_blocked(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("mergeable_state", "blocked"), "cleanly mergeable")

    # 34
    def test_label_needs_human(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("labels", ["needs-human"]), "pull request is labelled")

    # 35
    def test_changed_file_constitution(self):
        self.assertRefused(
            lambda e: e.__setitem__("files", [{"filename": "CONSTITUTION.md", "previous_filename": None}]),
            "protected path CONSTITUTION.md")

    def test_changed_file_merge_policy(self):
        # A PR must never authorise its own merge by editing the policy.
        self.assertRefused(
            lambda e: e.__setitem__("files", [{"filename": "policy/autonomous-merge.json", "previous_filename": None}]),
            "protected path policy/autonomous-merge.json")

    # 36
    def test_changed_file_github_workflow(self):
        self.assertRefused(
            lambda e: e.__setitem__("files", [{"filename": ".github/workflows/x.yml", "previous_filename": None}]),
            "protected path .github/workflows/x.yml")

    # 37
    def test_renamed_file_previous_filename_protected(self):
        self.assertRefused(
            lambda e: e.__setitem__("files", [{"filename": "src/a.py", "previous_filename": "CLAUDE.md"}]),
            "protected path CLAUDE.md")

    # 38
    def test_project_protected_paths_match(self):
        p = policy(); p["projects"]["p"]["protected_paths"] = ["secrets/**"]

        def mutate(e):
            e["files"] = [{"filename": "secrets/x.txt", "previous_filename": None}]
        self.assertRefused(mutate, "protected path secrets/x.txt", pol=p)

    # 39
    def test_mergeable_paths_set_and_file_outside(self):
        p = policy(); p["projects"]["p"]["mergeable_paths"] = ["src/**"]

        def mutate(e):
            e["files"] = [{"filename": "other/b.py", "previous_filename": None}]
        self.assertRefused(mutate, "outside the project's autonomously mergeable paths", pol=p)

    # 40
    def test_len_files_ne_changed_files(self):
        self.assertRefused(lambda e: e["pr"].__setitem__("changed_files", 2), "complete list of changed files")

    # 41
    def test_files_none(self):
        self.assertRefused(lambda e: e.__setitem__("files", None), "complete list of changed files")

    # 42
    def test_required_check_missing(self):
        p = policy(); p["projects"]["p"]["required_checks"] = ["check", "other"]
        self.assertRefused(lambda e: None, "required check other has not passed", pol=p)

    # 43
    def test_required_check_conclusion_failure(self):
        self.assertRefused(
            lambda e: e.__setitem__(
                "check_runs", [{"name": "check", "head_sha": SHA, "status": "completed", "conclusion": "failure"}]),
            "check check is failure")

    # 44
    def test_non_required_check_in_progress(self):
        def mutate(e):
            e["check_runs"].append({"name": "extra", "head_sha": SHA, "status": "in_progress", "conclusion": None})
        self.assertRefused(mutate, "check extra is in_progress")

    # 45
    def test_check_run_for_another_head_sha(self):
        self.assertRefused(
            lambda e: e.__setitem__(
                "check_runs", [{"name": "check", "head_sha": SHA2, "status": "completed", "conclusion": "success"}]),
            "not for the expected head")

    # 46
    def test_commit_status_pending(self):
        self.assertRefused(lambda e: e.__setitem__("statuses", [{"context": "ci", "state": "pending"}]),
                            "status ci is pending")

    # 47
    def test_changes_requested(self):
        self.assertRefused(
            lambda e: e.__setitem__("reviews", [{"user": "someone", "state": "CHANGES_REQUESTED", "commit_id": SHA}]),
            "changes were requested")

    # 48
    def test_approval_on_older_commit_id(self):
        self.assertRefused(
            lambda e: e.__setitem__("reviews", [{"user": "rev", "state": "APPROVED", "commit_id": SHA2}]),
            "needs 1 independent approval")

    # 49
    def test_approval_from_untrusted_login(self):
        self.assertRefused(
            lambda e: e.__setitem__("reviews", [{"user": "nottrusted", "state": "APPROVED", "commit_id": SHA}]),
            "needs 1 independent approval")

    # 50
    def test_approval_by_pr_author(self):
        def mutate(e):
            e["pr"]["author"] = "rev"
            e["reviews"] = [{"user": "rev", "state": "APPROVED", "commit_id": SHA}]
        self.assertRefused(mutate, "needs 1 independent approval")

    # 51
    def test_risk_high_zero_required_approvals_no_reviews(self):
        p = policy(); p["projects"]["p"]["required_approvals"] = 0

        def mutate(e):
            e["issue"]["description"] = "- **Authority:** A\n- **Engineering risk:** high\n"
            e["reviews"] = []
        self.assertRefused(mutate, "needs 1 independent approval", pol=p)

    # 52 positive
    def test_class_a_low_risk_zero_required_approvals_allowed(self):
        p = policy(); p["projects"]["p"]["required_approvals"] = 0
        e = ev()
        e["issue"]["description"] = "- **Authority:** A\n- **Engineering risk:** low\n"
        e["reviews"] = []
        self.assertEqual(evaluate(p, req(), e), [])

    # 53 positive
    def test_b_valid_human_only_approval_in_scope_allowed(self):
        e = ev()
        e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
        e["plan"] = copy.deepcopy(VALID_B_PLAN)
        e["interactions"] = [copy.deepcopy(VALID_B_APPROVAL)]
        self.assertEqual(evaluate(policy(), req(), e), [])

    # 54
    def test_b_plan_lacks_scope_paths(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = {"body": "no scope line here", "latestRevisionId": "rev-2"}
            e["interactions"] = [copy.deepcopy(VALID_B_APPROVAL)]
        self.assertRefused(mutate, "must declare its Scope paths once")

    # 55
    def test_b_file_outside_scope_paths(self):
        def mutate(e):
            e["issue"]["description"] = "- **Authority:** B\n- **Engineering risk:** low\n"
            e["plan"] = {"body": "**Scope paths:** other/**", "latestRevisionId": "rev-2"}
            e["interactions"] = [copy.deepcopy(VALID_B_APPROVAL)]
        self.assertRefused(mutate, "B2: needs human approval")

    # 56
    def test_head_sha_not_40_hex(self):
        rq = req(); rq["head_sha"] = "abc"
        self.assertRefused(lambda e: None, "full 40-character commit id", rq=rq)

    # 57 positive
    def test_approved_then_commented_still_counts(self):
        e = ev()
        e["reviews"] = [{"user": "rev", "state": "APPROVED", "commit_id": SHA},
                         {"user": "rev", "state": "COMMENTED", "commit_id": SHA}]
        self.assertEqual(evaluate(policy(), req(), e), [])


# ---- collect() / run() without network -------------------------------------------------------

class FakePC:
    def __init__(self, issue, plan=None, interactions=None):
        self._issue, self._plan, self._interactions = issue, plan, (interactions if interactions is not None else [])

    def get_issue(self, issue_id):
        return self._issue if self._issue.get("id") == issue_id else None

    def get_document(self, issue_id, key):
        return self._plan

    def issue_activity(self, issue_id):
        return []

    def interactions(self, issue_id):
        return self._interactions


def gh_pr_json():
    return {
        "number": 7, "state": "open", "draft": False, "merged": False,
        "base": {"ref": "main", "repo": {"full_name": R}},
        "head": {"ref": "agent/AGE-3-x", "sha": SHA, "repo": {"full_name": R}},
        "user": {"login": "bot"}, "labels": [],
        "mergeable": True, "mergeable_state": "clean", "changed_files": 1,
    }


def make_fake_gh(pr=None, files=None, check_runs=None, statuses=None, reviews=None, fail=False):
    repo, n, sha = R.lower(), 7, SHA
    pr = pr if pr is not None else gh_pr_json()
    files = files if files is not None else [{"filename": "src/a.py", "previous_filename": None}]
    check_runs = check_runs if check_runs is not None else [
        {"name": "check", "head_sha": sha, "status": "completed", "conclusion": "success"}]
    statuses = statuses if statuses is not None else []
    reviews = reviews if reviews is not None else [{"user": {"login": "rev"}, "state": "APPROVED", "commit_id": sha}]

    routes = {
        f"repos/{repo}/pulls/{n}": pr,
        f"repos/{repo}/pulls/{n}/files?per_page=100": files,
        f"repos/{repo}/commits/{sha}/check-runs?filter=latest&per_page=100": check_runs,
        f"repos/{repo}/commits/{sha}/status": {"statuses": statuses},
        f"repos/{repo}/pulls/{n}/reviews?per_page=100": reviews,
    }

    def gh(path, paginate=False):
        if fail:
            raise RuntimeError("gh boom")
        if path not in routes:
            raise RuntimeError(f"unexpected gh path {path}")
        return routes[path]
    return gh


class CollectRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def request(self):
        return {"issue_id": "i", "repo": R.lower(), "pr": 7, "head_sha": SHA}

    def logpath(self):
        return os.path.join(self.data_dir, "log", "merge-gate.jsonl")

    def loglines(self):
        try:
            with open(self.logpath()) as f:
                return f.read().splitlines()
        except FileNotFoundError:
            return []

    def test_collect_builds_expected_evidence_shape(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        e = collect(pc, self.request(), gh=gh)
        self.assertEqual(e["pr"]["head_sha"], SHA)
        self.assertEqual(e["reviews"], [{"user": "rev", "state": "APPROVED", "commit_id": SHA}])
        self.assertEqual(e["files"], [{"filename": "src/a.py", "previous_filename": None}])
        self.assertEqual(evaluate(policy(), self.request(), e), [])

    def test_run_check_only_allowed_never_merges(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        called = []
        allowed, reasons, merged = run(pc, self.request(), do_merge=False, policy=policy(), gh=gh,
                                        merge_cmd=called.append, data_dir=self.data_dir)
        self.assertTrue(allowed, reasons)
        self.assertFalse(merged)
        self.assertEqual(called, [])
        self.assertEqual(len(self.loglines()), 1)

    def test_run_merge_allowed_calls_merge_cmd_and_logs_twice(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        allowed, reasons, merged = run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                                        merge_cmd=["true"], data_dir=self.data_dir)
        self.assertTrue(allowed, reasons)
        self.assertTrue(merged)
        self.assertEqual(len(self.loglines()), 2)
        for line in self.loglines():
            json.loads(line)  # each line is valid JSON

    def test_run_refused_does_not_merge(self):
        marker = os.path.join(self.data_dir, "marker")
        issue = copy.deepcopy(BASE_ISSUE)
        issue["companyId"] = "other-company"  # forces refusal
        pc = FakePC(issue)
        gh = make_fake_gh()
        allowed, reasons, merged = run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                                        merge_cmd=["touch", marker], data_dir=self.data_dir)
        self.assertFalse(allowed)
        self.assertFalse(merged)
        self.assertFalse(os.path.exists(marker))

    def test_run_gh_failure_refuses_with_evidence_message(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh(fail=True)
        allowed, reasons, merged = run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                                        merge_cmd=["true"], data_dir=self.data_dir)
        self.assertFalse(allowed)
        self.assertFalse(merged)
        self.assertTrue(any("could not collect evidence" in r for r in reasons), reasons)

    def test_run_merge_cmd_failure(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        allowed, reasons, merged = run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                                        merge_cmd=["false"], data_dir=self.data_dir)
        self.assertTrue(allowed, reasons)
        self.assertFalse(merged)
        self.assertTrue(reasons)

    def test_run_unwritable_data_dir_raises_and_does_not_merge(self):
        marker = os.path.join(self.data_dir, "marker")
        bad_data_dir = os.path.join(self.data_dir, "not_a_dir")
        open(bad_data_dir, "w").close()  # a file, not a directory: os.makedirs(.../log) will fail
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        with self.assertRaises(Exception):
            run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                merge_cmd=["touch", marker], data_dir=bad_data_dir)
        self.assertFalse(os.path.exists(marker))

    def test_default_merge_command_shape(self):
        pc = FakePC(copy.deepcopy(BASE_ISSUE))
        gh = make_fake_gh()
        captured = {}

        real_run = merge_gate.subprocess.run

        def fake_run(cmd, **kw):
            if cmd and cmd[0] == "gh":
                captured["cmd"] = cmd

                class R:
                    returncode = 0
                    stdout = ""
                    stderr = ""
                return R()
            return real_run(cmd, **kw)

        with mock.patch.object(merge_gate.subprocess, "run", side_effect=fake_run):
            allowed, reasons, merged = run(pc, self.request(), do_merge=True, policy=policy(), gh=gh,
                                            data_dir=self.data_dir)
        self.assertTrue(allowed, reasons)
        self.assertTrue(merged)
        cmd = captured["cmd"]
        self.assertIn("--match-head-commit", cmd)
        self.assertIn(SHA, cmd)
        self.assertNotIn("--admin", cmd)


if __name__ == "__main__":
    unittest.main()
