"""agent-bin/studio-task: task actions for agents whose tools lack Paperclip's issue actions."""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

from tests.fakes import FakePaperclip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    loader = importlib.machinery.SourceFileLoader("studio_task", os.path.join(ROOT, "agent-bin", "studio-task"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class StudioTask(unittest.TestCase):
    def setUp(self):
        self.fp = FakePaperclip()
        self.fp.add(id="t", title="T", status="in_progress", assigneeAgentId="cx", createdByUserId="ben")
        self.env = mock.patch.dict(os.environ, {"PAPERCLIP_API_URL": self.fp.url, "PAPERCLIP_API_KEY": "run-key"})
        self.env.start()
        self.mod = load()

    def tearDown(self):
        self.env.stop()
        self.fp.stop()

    def test_comment_status_and_document(self):
        self.assertEqual(self.mod.main(["x", "comment", "t", "hello"]), 0)
        self.assertEqual(self.fp.comments, [("t", "hello")])
        self.assertEqual(self.mod.main(["x", "status", "t", "blocked"]), 0)
        self.assertEqual(self.fp.issues["t"]["status"], "blocked")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
            f.write("# Evidence\n")
        self.assertEqual(self.mod.main(["x", "doc", "t", "evidence", f.name]), 0)
        self.assertEqual(self.fp.docs[("t", "evidence")], "# Evidence\n")
        os.remove(f.name)

    def test_handback_goes_to_the_recorded_creator(self):
        self.assertEqual(self.mod.main(["x", "handback", "t", "done, see comment"]), 0)
        patch = self.fp.patches[-1][1]
        self.assertEqual((patch["status"], patch["assigneeUserId"], patch["comment"]), ("in_review", "ben", "done, see comment"))

    def test_bad_use_is_refused(self):
        for argv in (["x"], ["x", "status", "t", "shipped"], ["x", "delete", "t"], ["x", "comment", "t"]):
            self.assertEqual(self.mod.main(argv), 2, argv)
        os.environ.pop("PAPERCLIP_API_KEY")
        self.assertEqual(self.mod.main(["x", "comment", "t", "hi"]), 3)


if __name__ == "__main__":
    unittest.main()
