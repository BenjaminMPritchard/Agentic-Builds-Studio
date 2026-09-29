"""agent-bin/studio-record-pr writes the PR and head-commit work products the merge gate and Clerk read."""
import importlib.machinery
import importlib.util
import os
import unittest

from lib import merge_gate
from lib.paperclip import Paperclip
from tests.fakes import FakePaperclip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://github.com/BenjaminMPritchard/Agentic-Builds-Studio/pull/33"


def load():
    loader = importlib.machinery.SourceFileLoader("studio_record_pr", os.path.join(ROOT, "agent-bin", "studio-record-pr"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class RecordPr(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.fp = FakePaperclip()
        self.pc = Paperclip(self.fp.url, "k")
        self.fp.add(id="t", title="AGE-9", status="in_review")
        self.pr = {"number": 33, "state": "OPEN", "headRefName": "agent/AGE-9-mothers-backfill",
                   "headRefOid": "a52db609acee34e2f409290f33a05b48e2fcd85a", "isDraft": False}

    def tearDown(self):
        self.fp.stop()

    def record(self):
        return self.mod.record(self.pc, "t", URL, self.pr)

    def issue(self):
        return {"workProducts": self.fp.products.get("t", [])}

    def test_the_merge_gate_accepts_what_is_recorded(self):
        self.assertEqual(self.record(), ["recorded PR #33", "recorded head a52db60"])
        repo = "benjaminmpritchard/agentic-builds-studio"
        self.assertEqual(merge_gate.linked_prs(self.issue()), [(repo, 33, "agent/AGE-9-mothers-backfill")])
        self.assertTrue(merge_gate.recorded_commit(self.issue(), repo, self.pr["headRefOid"], self.pr["headRefName"]))

    def test_running_it_again_changes_nothing(self):
        self.record()
        self.assertEqual(self.record(), [])
        self.assertEqual(len(self.fp.products["t"]), 2)

    def test_a_new_head_is_recorded_and_the_old_one_archived(self):
        self.record()
        self.pr["headRefOid"] = "b" * 40
        self.assertEqual(self.record(), ["recorded head bbbbbbb", "archived old head a52db60"])
        live = [w for w in self.fp.products["t"] if w["type"] == "commit" and w["status"] != "archived"]
        self.assertEqual([w["metadata"]["sha"] for w in live], ["b" * 40])

    def test_merged_state_is_carried_over(self):
        self.record()
        self.pr["state"] = "MERGED"
        self.assertEqual(self.record(), ["updated PR #33 (merged)"])
        self.assertEqual(merge_gate.linked_prs(self.issue()), [])  # a merged PR is no longer a live link

    def test_github_must_agree_with_the_url(self):
        self.pr["number"] = 34
        with self.assertRaises(SystemExit):
            self.record()
        self.assertEqual(self.fp.products, {})

    def test_bad_arguments(self):
        for argv in (["x"], ["x", "t"], ["x", "t", "https://github.com/o/r/issues/3"], ["x", "t", URL, "extra"]):
            self.assertEqual(self.mod.main(argv), 2, argv)


if __name__ == "__main__":
    unittest.main()
