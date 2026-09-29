"""bin/qwen-run's Paperclip path: check out the task, run the job, and finish it or hand it back to its creator."""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

from tests.fakes import FakeOllama, FakePaperclip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD = json.dumps({"category": "lint", "evidence": "F401 `os` imported but unused"})
BAD = json.dumps({"category": "lint", "evidence": "invented"})


class Handback(unittest.TestCase):
    def setUp(self):
        self.fp = FakePaperclip()
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "enabled.json"), "w") as f:
            json.dump({"enabled": ["classify-failure"]}, f)
        self.job = {"job": "classify-failure", "input": {"log": "F401 `os` imported but unused"},
                    "requester": "someone-else"}

    def tearDown(self):
        self.fp.stop()
        self.tmp.cleanup()

    def run_worker(self, answers, task="t", run=None, **issue):
        self.fp.add(**{"id": "t", "title": "Classify", "status": "todo", "assigneeAgentId": "worker", **issue})
        o = FakeOllama(answers)
        env = {"PAPERCLIP_API_URL": self.fp.url, "PAPERCLIP_API_KEY": "k", "PAPERCLIP_AGENT_ID": "worker",
               "OLLAMA_URL": o.url, "STUDIO_DATA": self.tmp.name, "STUDIO_QWEN_DIR": self.tmp.name}
        if task:
            env["PAPERCLIP_TASK_ID"] = task
        if run:
            env["PAPERCLIP_RUN_ID"] = run
        try:
            with mock.patch.dict(os.environ, env):
                if not task:
                    os.environ.pop("PAPERCLIP_TASK_ID", None)
                if not run:
                    os.environ.pop("PAPERCLIP_RUN_ID", None)
                loader = importlib.machinery.SourceFileLoader("qwen_run", os.path.join(ROOT, "bin", "qwen-run"))
                spec = importlib.util.spec_from_loader(loader.name, loader)
                mod = importlib.util.module_from_spec(spec)
                loader.exec_module(mod)
                return mod.paperclip_task()
        finally:
            o.stop()

    def last_patch(self):
        return self.fp.patches[-1][1]

    def test_a_checked_result_finishes_the_task(self):
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.assertEqual(self.run_worker([GOOD], createdByAgentId="director"), 0)
        self.assertEqual(self.fp.checkouts, ["t"])
        self.assertEqual(json.loads(self.fp.docs[("t", "result")])["status"], "ok")
        self.assertEqual(self.last_patch()["status"], "done")

    def test_a_job_whose_strings_came_back_with_real_line_breaks_still_runs(self):
        # As Paperclip returned AGE-12's job document: the \n escapes had become line breaks.
        self.fp.docs[("t", "job")] = '{"job": "classify-failure", "input": {"log": "F401 `os` imported but unused\nsecond line"}}'
        self.run_worker([GOOD], createdByAgentId="director")
        self.assertEqual(self.last_patch()["status"], "done")

    def test_a_failed_job_goes_back_to_the_agent_that_created_the_task(self):
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.run_worker([BAD], createdByAgentId="director")
        p = self.last_patch()
        self.assertEqual((p["status"], p["assigneeAgentId"]), ("todo", "director"))  # not the document's "requester"
        self.assertIn("could not produce a checked result", p["comment"])
        self.assertEqual(json.loads(self.fp.docs[("t", "result")])["status"], "needs_human")

    def test_a_task_a_person_created_goes_back_to_that_person(self):
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.run_worker([BAD], createdByUserId="benjamin")
        p = self.last_patch()
        self.assertEqual((p["status"], p["assigneeAgentId"], p["assigneeUserId"]), ("todo", None, "benjamin"))

    def test_no_creator_blocks_the_task_with_the_reason(self):
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.run_worker([BAD])
        p = self.last_patch()
        self.assertEqual(p["status"], "blocked")
        self.assertIn("No creator is recorded", p["comment"])

    def test_missing_or_broken_job_document_is_handed_back(self):
        self.assertEqual(self.run_worker([GOOD], createdByAgentId="director"), 1)
        self.assertIn("no `job` document", self.last_patch()["comment"])
        self.fp.docs[("t", "job")] = "{not json"
        self.fp.checkouts.clear()
        self.assertEqual(self.run_worker([GOOD], createdByAgentId="director"), 1)
        self.assertIn("not valid JSON", self.last_patch()["comment"])

    def test_a_disabled_job_is_handed_back_without_calling_the_model(self):
        self.job["job"] = "mechanical-edit"
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.run_worker([GOOD], createdByAgentId="director")
        self.assertIn("is not enabled", self.last_patch()["comment"])

    def test_a_wake_without_a_task_does_nothing(self):
        self.assertEqual(self.run_worker([GOOD], task=None), 0)
        self.assertEqual((self.fp.checkouts, self.fp.patches), ([], []))

    def test_the_task_is_found_from_the_run_when_paperclip_does_not_pass_it(self):
        # Paperclip's process adapter sets PAPERCLIP_RUN_ID but not PAPERCLIP_TASK_ID, and has already checked
        # the task out for this run (a second checkout would be refused).
        self.fp.run_records["run-1"] = {"id": "run-1", "contextSnapshot": {
            "issueId": "t", "wakeReason": "issue_assigned", "paperclipHarnessCheckedOut": True}}
        self.fp.checkouts.append("t")
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.assertEqual(self.run_worker([GOOD], task=None, run="run-1", createdByAgentId="director"), 0)
        self.assertEqual(self.last_patch()["status"], "done")

    def test_a_run_without_an_issue_does_nothing(self):
        self.fp.run_records["run-2"] = {"id": "run-2", "contextSnapshot": {"wakeReason": "timer"}}
        self.assertEqual(self.run_worker([GOOD], task=None, run="run-2"), 0)
        self.assertEqual(self.fp.patches, [])

    def test_a_task_someone_else_has_is_left_alone(self):
        self.fp.checkouts.append("t")  # the fake answers 409 for a second checkout
        self.fp.docs[("t", "job")] = json.dumps(self.job)
        self.assertEqual(self.run_worker([GOOD], createdByAgentId="director"), 0)
        self.assertEqual(self.fp.patches, [])


if __name__ == "__main__":
    unittest.main()
