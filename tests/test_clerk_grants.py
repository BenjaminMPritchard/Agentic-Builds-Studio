import json
import subprocess
import unittest

from lib import clerk_grants


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TrimSqlTest(unittest.TestCase):
    def test_deletes_only_the_clerks_other_grants(self):
        sql = clerk_grants.trim_sql()
        self.assertIn(f"principal_id = '{clerk_grants.CLERK_USER}'", sql)
        self.assertIn(f"company_id = '{clerk_grants.COMPANY}'", sql)
        self.assertIn("principal_type = 'user'", sql)
        self.assertIn("permission_key NOT IN ('tasks:assign')", sql)
        self.assertTrue(sql.startswith("DELETE FROM principal_permission_grants WHERE"))

    def test_refuses_values_that_could_change_the_sql(self):
        for kw in ({"user": "x' OR '1'='1"}, {"company": "c; DROP TABLE x"}, {"keep": ()},
                   {"keep": ("tasks:assign') OR ('1",)}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                clerk_grants.trim_sql(**kw)


class TrimTest(unittest.TestCase):
    def test_returns_the_removed_keys(self):
        seen = {}

        def run(cmd, **kw):
            seen["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "tools:admin\nagents:create\n", "")
        self.assertEqual(clerk_grants.trim(run=run), ["agents:create", "tools:admin"])
        self.assertIn("ON_ERROR_STOP=1", seen["cmd"])
        self.assertEqual(seen["cmd"][-1], clerk_grants.trim_sql())

    def test_nothing_to_remove(self):
        self.assertEqual(clerk_grants.trim(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", "")), [])

    def test_psql_failure_raises(self):
        with self.assertRaisesRegex(RuntimeError, "psql exited 2"):
            clerk_grants.trim(run=lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "connection refused"))


class WaitHealthyTest(unittest.TestCase):
    def test_waits_through_errors_until_ok(self):
        answers = [OSError("refused"), FakeResponse(b'{"status":"starting"}'), FakeResponse(b'{"status":"ok"}')]

        def opener(url, timeout):
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        self.assertTrue(clerk_grants.wait_healthy(timeout=60, opener=opener, sleep=lambda s: None))
        self.assertEqual(answers, [])

    def test_gives_up_at_the_timeout(self):
        def opener(url, timeout):
            return FakeResponse(json.dumps({"status": "starting"}).encode())
        self.assertFalse(clerk_grants.wait_healthy(timeout=0, opener=opener, sleep=lambda s: None))


if __name__ == "__main__":
    unittest.main()
