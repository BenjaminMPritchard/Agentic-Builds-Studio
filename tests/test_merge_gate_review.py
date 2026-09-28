"""Independent review through Paperclip's review stage (no second GitHub identity)."""
import copy
import unittest

from lib.merge_gate import evaluate
from tests.test_merge_gate import BASE_EV, BASE_POLICY, BASE_REQ, SHA, R

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


if __name__ == "__main__":
    unittest.main()
