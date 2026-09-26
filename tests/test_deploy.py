import os, subprocess, tempfile, unittest
from lib import deploy
from lib.clerk import Clerk
from lib.paperclip import Paperclip
from tests.fakes import FakePaperclip


def g(cwd, *a):
    subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


class Deploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.origin, self.work, self.live = (os.path.join(t, n) for n in ("origin.git", "work", "live"))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.work], check=True, capture_output=True)
        self.commit("tests/__init__.py", "")
        self.commit("tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test(self): self.assertTrue(True)\n")
        g(self.work, "push", "-q", "origin", "main")
        subprocess.run(["git", "clone", "-q", self.origin, self.live], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, path, text, push=False):
        full = os.path.join(self.work, path); os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "w").write(text); g(self.work, "add", "-A"); g(self.work, "commit", "-qm", f"edit {path}")
        if push: g(self.work, "push", "-q", "origin", "main")

    def head(self, repo):
        return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_current_then_updates_when_tests_pass(self):
        self.assertEqual(deploy.sync(self.live)["status"], "current")
        self.commit("skills/x/SKILL.md", "hi", push=True)
        r = deploy.sync(self.live)
        self.assertEqual((r["status"], r["changed"]), ("updated", ["skills/x/SKILL.md"]))
        self.assertEqual(self.head(self.live), self.head(self.work))
        self.assertFalse(os.path.exists(os.path.join(self.live, ".git", "worktrees")) and os.listdir(os.path.join(self.live, ".git", "worktrees")))

    def test_failing_tests_block_the_deploy_and_are_not_retried(self):
        before = self.head(self.live)
        self.commit("tests/test_bad.py", "import unittest\nclass B(unittest.TestCase):\n    def test(self): self.fail('boom')\n", push=True)
        r = deploy.sync(self.live)
        self.assertEqual(r["status"], "tests_failed"); self.assertIn("boom", r["detail"])
        self.assertEqual(self.head(self.live), before)                       # live copy did not move
        self.assertTrue(deploy.sync(self.live, skip_sha=r["sha"])["repeat"])  # known-bad commit: not re-tested every tick
        self.commit("tests/test_bad.py", "", push=True)                       # a fix arrives
        self.assertEqual(deploy.sync(self.live, skip_sha=r["sha"])["status"], "updated")

    def test_never_overwrites_local_edits_or_diverged_history(self):
        open(os.path.join(self.live, "local.txt"), "w").write("x"); g(self.live, "add", "-A")
        self.commit("a.txt", "a", push=True)
        self.assertEqual(deploy.sync(self.live)["status"], "dirty")
        g(self.live, "commit", "-qm", "local commit")
        self.assertEqual(deploy.sync(self.live)["status"], "diverged")

    def test_fetch_failure_is_reported_not_raised(self):
        g(self.live, "remote", "set-url", "origin", os.path.join(self.tmp.name, "nope.git"))
        self.assertEqual(deploy.sync(self.live)["status"], "fetch_failed")

    def test_clerk_step_updates_notes_and_rescans_skills(self):
        fp = FakePaperclip(); calls = []
        try:
            pc = Paperclip(fp.url, "k"); pc.rescan_skills = lambda c, p: calls.append((c, p))
            self.commit("skills/x/SKILL.md", "hi", push=True)
            c = Clerk(pc, "co", os.path.join(self.tmp.name, "data"), gh=lambda a: [], deploy_repo=self.live, infra_project_id="proj")
            c.tick()
            self.assertEqual(calls, [("co", "proj")])
            self.assertTrue(any("Deployed studio-company" in n for n in c.notes))
            self.commit("tests/test_bad.py", "import unittest\nclass B(unittest.TestCase):\n    def test(self): self.fail('x')\n", push=True)
            c2 = Clerk(pc, "co", os.path.join(self.tmp.name, "data"), gh=lambda a: [], deploy_repo=self.live); c2.tick()
            self.assertTrue(any("NOT deployed" in b for b in c2.needs_board))
            c3 = Clerk(pc, "co", os.path.join(self.tmp.name, "data"), gh=lambda a: [], deploy_repo=self.live); c3.tick()
            self.assertFalse(any("NOT deployed" in b for b in c3.needs_board))   # reported once, then quiet
        finally:
            fp.stop()


if __name__ == "__main__":
    unittest.main()
