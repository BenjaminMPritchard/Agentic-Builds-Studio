"""bin/studio-status: the scheduled phone status (Benjamin, 2026-11-04: a script, not an agent)."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1793800000.0


def load():
    loader = importlib.machinery.SourceFileLoader("studio_status", os.path.join(ROOT, "bin", "studio-status"))
    spec = importlib.util.spec_from_loader("studio_status", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class Status(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def snap(self, **kw):
        status = {"t": int(NOW - 300), "waiting": [], "blocked": [], "agents": [], "errors": [],
                  "counts": {"in_progress": 2, "todo": 3, "done": 40},
                  "usage": "Claude studio use 4 of 20 points this 5-hour window (resets 1pm), 9 of 35 this week; "
                           "account 30% / 40%; 0 runs active; reading 5 min old",
                  "codex_week": {"left": 62.5, "days": 3.2}, **kw}
        with open(os.path.join(self.tmp.name, "clerk-state.json"), "w") as f:
            json.dump({"status": status, "done": {}}, f)

    def report(self, up=True):
        return self.mod.report(NOW, data=self.tmp.name, up=up)

    def test_all_good(self):
        self.snap()
        title, text = self.report()
        self.assertEqual(title, "Studio: all good")
        self.assertTrue(text.startswith("Nothing needs you and nothing is stuck."))
        self.assertIn("Work: 2 in progress, 3 to do.", text)
        self.snap(queued=4)
        self.assertIn("Work: 2 in progress, 3 to do, 4 waiting for earlier tasks.", self.report()[1])
        self.assertIn("Claude: studio used 4 of 20 points this 5-hour window (resets 1pm), 9 of 35 this week.", text)
        self.assertIn("Codex: 62.5 points left this week, 3.2 days to reset.", text)

    def test_what_is_stuck_is_named(self):
        self.snap(blocked=[{"id": "AGE-108", "title": "Viewing lifecycle", "since": "2026-11-04T09:00:00Z",
                            "agent": "Builder-2"}],
                  agents=[{"name": "Codex-Builder", "status": "error", "why": None}])
        title, text = self.report()
        self.assertEqual(title, "Studio is stuck")
        self.assertIn("- Viewing lifecycle (blocked 4 h, Builder-2)", text)
        self.assertNotIn("AGE-", text)
        self.assertIn("- Codex-Builder is error", text)

    def test_what_needs_benjamin_comes_first(self):
        self.snap(waiting=[f"merge PR #{n}: thing {n}" for n in range(7)],
                  blocked=[{"id": "AGE-1", "title": "x", "since": None, "agent": None}])
        title, text = self.report()
        self.assertEqual(title, "Studio needs you")
        self.assertTrue(text.startswith("Needs you:\n- merge PR #0: thing 0"))
        self.assertIn("- and 2 more", text)
        self.assertLess(text.index("Needs you:"), text.index("Stuck:"))

    def test_a_silent_clerk_or_paperclip_down_is_reported(self):
        self.snap(t=int(NOW - 3 * 3600))
        self.assertEqual(self.report(), ("Studio is stuck", "The Clerk has not reported for 3 h, so nothing is "
                                         "retried or gated. Check the Clerk agent in Paperclip."))
        os.remove(os.path.join(self.tmp.name, "clerk-state.json"))
        self.assertEqual(self.report()[0], "Studio status missing")
        self.assertEqual(self.report(up=False)[0], "Studio is down")


if __name__ == "__main__":
    unittest.main()
