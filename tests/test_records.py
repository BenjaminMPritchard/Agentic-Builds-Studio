"""lib/records.py: append-only run records and the per-agent report (research 11)."""
import json
import os
import shutil
import tempfile
import unittest

from lib import records


def run(i, agent="a1", status="succeeded", mins=10, model="claude-sonnet-5", issue="t"):
    return {"id": i, "agentId": agent, "status": status, "createdAt": f"2026-09-30T01:{i[-1]}0:00Z",
            "startedAt": "2026-09-30T02:00:00Z", "finishedAt": f"2026-09-30T02:{mins:02d}:00Z",
            "contextSnapshot": {"issueId": issue}, "usageJson": {"model": model, "outputTokens": 1000}}


class Records(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "records", "runs.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_append_only_and_once_per_run(self):
        names = {"a1": "Builder-1"}
        self.assertEqual(records.collect([run("r1"), run("r2", status="running")], names, {}, self.path), 1)
        first = open(self.path).read()
        self.assertEqual(records.collect([run("r1"), run("r2")], names, {}, self.path), 1)
        self.assertTrue(open(self.path).read().startswith(first))  # earlier lines are never rewritten
        self.assertEqual([r["run"] for r in records.load_jsonl(self.path)], ["r1", "r2"])

    def test_claude_and_codex_usage_stay_in_separate_columns(self):
        usage = {"r1": ("claude", {"used": {"five_hour": 3.0, "week": 0.5}}),
                 "r2": ("codex", {"used": {"five_hour": 4.0, "week": 1.0}})}
        records.collect([run("r1"), run("r2", model="gpt-6-sol", mins=30)], {"a1": "X"}, usage, self.path)
        text = records.report(records.load_jsonl(self.path), {"t": {"status": "in_review"}})
        self.assertIn("| 3 / 0.5 (n=1) | 4 / 1 (n=1) |", text)
        self.assertIn("20 / 30", text)  # median and p90 minutes over the two runs
        self.assertIn("never added", text)

    def test_a_torn_last_line_is_skipped_not_repaired(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write(json.dumps(records.record(run("r1"), {}, {})) + "\n" + '{"run": "r2", "ag')
        self.assertEqual([r["run"] for r in records.load_jsonl(self.path)], ["r1"])
        records.collect([run("r3")], {}, {}, self.path)  # appending after a torn line keeps the new record
        self.assertEqual([r["run"] for r in records.load_jsonl(self.path)], ["r1", "r3"])

    def test_no_records_reports_honestly(self):
        text = records.report([])
        self.assertIn("0 finished runs", text)
        self.assertIn("Not measured yet", text)


if __name__ == "__main__":
    unittest.main()
