"""Independent review through Paperclip's review stage (no second GitHub identity)."""
import copy
import os
import tempfile
import unittest
from unittest import mock

from lib import merge_gate
from lib.github_app import GitHubAppError
from lib.merge_gate import evaluate, run
from tests.test_merge_gate import BASE_EV, BASE_ISSUE, BASE_POLICY, BASE_REQ, SHA, R, FakePC, make_fake_gh, policy

AUTHOR, REVIEWER, OTHER = "builder", "principal", "director"
T_HEAD, T_BEFORE, T_AFTER, T_LATER = ("2026-09-28T10:00:00.000Z", "2026-09-28T09:00:00.000Z",
                                     "2026-09-28T11:00:00.000Z", "2026-09-28T12:00:00.000Z")


def decision(actor, outcome, when, decision_id, actor_type="agent"):
    return {"action": "issue.updated", "actorType": actor_type, "actorId": actor, "createdAt": when,
            "details": {"executionState": {"lastDecisionId": decision_id, "lastDecisionOutcome": outcome,
                                           "status": "completed" if outcome == "approved" else "changes_requested"}}}


def review_ev(activity):
    """Medium risk (needs one approval), no GitHub reviews, a completed Paperclip review stage."""
    ev = copy.deepcopy(BASE_EV)
    ev["reviews"] = []
    issue = ev["issue"]
    issue["description"] = "- **Authority:** A\n- **Engineering risk:** medium\n"
    issue["executionPolicy"] = {"mode": "normal", "stages": [{"id": "s1", "type": "review", "approvalsNeeded": 1,
                                                              "participants": [{"type": "agent", "agentId": REVIEWER}]}]}
    issue["executionState"] = {"status": "completed", "lastDecisionOutcome": "approved", "completedStageIds": ["s1"],
                               "returnAssignee": {"type": "agent", "agentId": AUTHOR}}
    for w in issue["workProducts"]:
        if w["type"] == "commit":
            w["createdAt"] = T_HEAD
    ev["activity"] = activity
    return ev


class PaperclipReview(unittest.TestCase):
    def check(self, activity, allowed, why=None):
        reasons = evaluate(BASE_POLICY, BASE_REQ, review_ev(activity))
        if allowed:
            self.assertEqual(reasons, [])
        else:
            self.assertTrue(any(why in r for r in reasons), reasons)

    def test_approval_by_another_agent_after_the_head_counts(self):
        self.check([decision(REVIEWER, "approved", T_AFTER, "d1")], True)

    def test_approval_by_a_human_counts(self):
        self.check([decision("user-1", "approved", T_AFTER, "d1", actor_type="user")], True)

    def test_approval_before_the_head_was_recorded_does_not_count(self):
        self.check([decision(REVIEWER, "approved", T_BEFORE, "d1")], False, "needs 1 independent approval")

    def test_self_approval_by_the_author_does_not_count(self):
        self.check([decision(AUTHOR, "approved", T_AFTER, "d1")], False, "needs 1 independent approval")

    def test_changes_requested_after_the_head_refuses_even_if_later_approved_elsewhere(self):
        self.check([decision(REVIEWER, "changes_requested", T_AFTER, "d1"), decision(OTHER, "approved", T_LATER, "d2")],
                   False, "requested changes after the head")

    def test_changes_requested_before_the_head_then_approval_after_is_fine(self):
        self.check([decision(REVIEWER, "changes_requested", T_BEFORE, "d1"), decision(REVIEWER, "approved", T_AFTER, "d2")],
                   True)

    def test_repeated_snapshot_of_the_same_decision_is_not_a_new_decision(self):
        # The approving decision d1 happened before the head; a later update merely repeats it.
        self.check([decision(REVIEWER, "approved", T_BEFORE, "d1"), decision(OTHER, "approved", T_AFTER, "d1")],
                   False, "needs 1 independent approval")

    def test_unknown_author_counts_no_approvals(self):
        ev = review_ev([decision(REVIEWER, "approved", T_AFTER, "d1")])
        ev["issue"]["executionState"]["returnAssignee"] = None
        self.assertTrue(any("needs 1 independent approval" in r for r in evaluate(BASE_POLICY, BASE_REQ, ev)))

    def test_head_never_recorded_with_a_time_counts_no_approvals(self):
        ev = review_ev([decision(REVIEWER, "approved", T_AFTER, "d1")])
        for w in ev["issue"]["workProducts"]:
            w.pop("createdAt", None)
        self.assertTrue(any("needs 1 independent approval" in r for r in evaluate(BASE_POLICY, BASE_REQ, ev)))

    def test_unreadable_activity_refuses(self):
        self.check(None, False, "could not read the issue's activity")

    def test_two_needed_counts_distinct_reviewers(self):
        policy = copy.deepcopy(BASE_POLICY)
        policy["projects"]["p"]["required_approvals"] = 2
        acts = [decision(REVIEWER, "approved", T_AFTER, "d1"), decision(REVIEWER, "approved", T_LATER, "d2")]
        self.assertTrue(any("needs 2" in r for r in evaluate(policy, BASE_REQ, review_ev(acts))))
        acts[1]["actorId"] = OTHER
        self.assertEqual(evaluate(policy, BASE_REQ, review_ev(acts)), [])


class MergeApp(unittest.TestCase):
    """When the policy names the merge App, the gate uses only that App's token."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.request = {"issue_id": "i", "repo": R.lower(), "pr": 7, "head_sha": SHA}

    def tearDown(self):
        self.tmp.cleanup()

    def app_policy(self):
        p = policy()
        p["github_app"] = {"app_id": 5109343, "key_path": "/etc/studio/merge-gate-app.pem"}
        return p

    def test_merge_runs_with_the_app_token_only(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"], seen["env"] = cmd, kw.get("env") or {}
            return mock.Mock(returncode=0, stdout="", stderr="")
        with mock.patch.object(merge_gate.github_app, "installation_token", return_value="tok-123") as tok, \
                mock.patch.dict(os.environ, {"GITHUB_TOKEN": "agent-token", "GH_TOKEN": "agent-token"}), \
                mock.patch.object(merge_gate.subprocess, "run", side_effect=fake_run):
            allowed, reasons, merged = run(FakePC(copy.deepcopy(BASE_ISSUE)), self.request, do_merge=True,
                                           policy=self.app_policy(), gh=make_fake_gh(), data_dir=self.tmp.name)
        self.assertTrue(merged, reasons)
        tok.assert_called_once_with(R.lower(), 5109343, "/etc/studio/merge-gate-app.pem")
        self.assertEqual(seen["env"].get("GH_TOKEN"), "tok-123")
        self.assertNotIn("GITHUB_TOKEN", seen["env"])

    def test_no_app_token_refuses_and_never_merges(self):
        with mock.patch.object(merge_gate.github_app, "installation_token", side_effect=GitHubAppError("key missing")), \
                mock.patch.object(merge_gate.subprocess, "run") as sub:
            allowed, reasons, merged = run(FakePC(copy.deepcopy(BASE_ISSUE)), self.request, do_merge=True,
                                           policy=self.app_policy(), gh=make_fake_gh(), data_dir=self.tmp.name)
        self.assertFalse(allowed)
        self.assertFalse(merged)
        sub.assert_not_called()
        self.assertTrue(any("GitHubAppError" in r for r in reasons), reasons)

    def test_malformed_app_policy_refuses(self):
        p = self.app_policy()
        p["github_app"]["app_id"] = "5109343"
        with mock.patch.object(merge_gate.github_app, "installation_token") as tok:
            allowed, reasons, _ = run(FakePC(copy.deepcopy(BASE_ISSUE)), self.request, policy=p, gh=make_fake_gh(),
                                      data_dir=self.tmp.name)
        self.assertFalse(allowed)
        tok.assert_not_called()

    def test_no_app_in_policy_keeps_the_ambient_credential(self):
        with mock.patch.object(merge_gate.github_app, "installation_token") as tok:
            allowed, reasons, _ = run(FakePC(copy.deepcopy(BASE_ISSUE)), self.request, policy=policy(),
                                      gh=make_fake_gh(), data_dir=self.tmp.name)
        self.assertTrue(allowed, reasons)
        tok.assert_not_called()


if __name__ == "__main__":
    unittest.main()
