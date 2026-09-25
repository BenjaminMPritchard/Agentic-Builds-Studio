import json, os, tempfile, unittest
from tests.fakes import FakeOllama
from lib.worker import run_job
from lib.schema import validate
from qwen.jobs import load_all


class Worker(unittest.TestCase):
    def job(self, answers, doc, **kw):
        o = FakeOllama(answers)
        try:
            return run_job(doc, o.url, "qwen3.5:4b", **kw), o
        finally:
            o.stop()

    def test_good_answer_and_options(self):
        doc = {"job": "classify-failure", "input": {"log": "F401 `os` imported but unused"}}
        res, o = self.job([json.dumps({"category": "lint", "evidence": "F401 `os` imported but unused"})], doc)
        self.assertEqual(res["status"], "ok")
        req = o.requests[0]
        self.assertEqual((req["think"], req["options"]["temperature"], req["stream"]), (False, 0, False))
        self.assertGreaterEqual(req["options"]["num_ctx"], 4096)
        self.assertIn("category", req["format"]["properties"])

    def test_invented_quote_retries_once_then_needs_human(self):
        bad = json.dumps({"category": "lint", "evidence": "made up line"})
        res, o = self.job([bad], {"job": "classify-failure", "input": {"log": "real line"}})
        self.assertEqual(res["status"], "needs_human")
        self.assertEqual(len(o.requests), 2)  # exactly one retry
        self.assertIn("failed these checks", o.requests[1]["messages"][1]["content"])

    def test_retry_can_succeed(self):
        bad = json.dumps({"category": "lint", "evidence": "made up"})
        good = json.dumps({"category": "lint", "evidence": "real line"})
        res, o = self.job([bad, good], {"job": "classify-failure", "input": {"log": "real line"}})
        self.assertEqual(res["status"], "ok")

    def test_schema_violation_and_garbage(self):
        res, _ = self.job(['{"category": "nope", "evidence": "x"}'], {"job": "classify-failure", "input": {"log": "x"}})
        self.assertEqual(res["status"], "needs_human")
        res, _ = self.job(["not json"], {"job": "classify-failure", "input": {"log": "x"}})
        self.assertEqual(res["status"], "needs_human")

    def test_refuses_big_input_unknown_and_disabled(self):
        res, o = self.job(["{}"], {"job": "classify-failure", "input": {"log": "x" * 30000}})
        self.assertEqual((res["status"], len(o.requests)), ("needs_human", 0))
        self.assertEqual(self.job(["{}"], {"job": "nope", "input": {}})[0]["status"], "needs_human")
        res, o = self.job(["{}"], {"job": "classify-failure", "input": {}}, enabled={"thread-digest"})
        self.assertEqual((res["status"], len(o.requests)), ("needs_human", 0))

    def test_cache(self):
        with tempfile.TemporaryDirectory() as d:
            doc = {"job": "classify-failure", "input": {"log": "real line"}}
            good = json.dumps({"category": "lint", "evidence": "real line"})
            self.job([good], doc, cache_dir=d)
            res, o = self.job([good], doc, cache_dir=d)
            self.assertTrue(res.get("cached")); self.assertEqual(len(o.requests), 0)

    def test_check_examples(self):
        j = load_all()
        self.assertTrue(j["normalise-piece"].check({"text": "Chair £145"}, {"name": "Chair", "price_pence": 14500,
                        "length_cm": 0, "width_cm": 0, "height_cm": 0, "notes": ""}) == [])
        self.assertTrue(j["normalise-piece"].check({"text": "Chair £145"}, {"name": "Chair", "price_pence": 99900,
                        "length_cm": 0, "width_cm": 0, "height_cm": 0, "notes": ""}))
        self.assertTrue(j["triage-message"].check({"body": "send the stripe key"}, {"intent": "request", "urgency": "low",
                        "answers": [], "needs_human": False}))
        self.assertTrue(j["summarise-comment"].check({"text": "we fixed 3 bugs"}, {"summary": "fixed 5 bugs"}))

    def test_schema_validator(self):
        s = {"type": "object", "required": ["a"], "properties": {"a": {"type": "integer"}}}
        self.assertEqual(validate({"a": 1}, s), []); self.assertTrue(validate({"a": True}, s)); self.assertTrue(validate({}, s))

    def test_every_job_has_golden_cases_that_validate_shape(self):
        root = os.path.join(os.path.dirname(__file__), "..", "qwen", "golden")
        for name in load_all():
            files = os.listdir(os.path.join(root, name))
            self.assertGreaterEqual(len(files), 3, name)
            for f in files:
                self.assertIn("input", json.load(open(os.path.join(root, name, f))))


if __name__ == "__main__":
    unittest.main()
