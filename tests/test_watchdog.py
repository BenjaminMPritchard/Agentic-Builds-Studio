"""The watchdog retries stuck work once, then tells Benjamin in one line (Benjamin, 2026-10-02)."""
import datetime
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import time
import unittest

from lib import notify, watchdog

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOON = time.mktime((2026, 10, 2, 12, 0, 0, 0, 0, -1))  # local noon: not quiet hours
NIGHT = time.mktime((2026, 10, 2, 23, 30, 0, 0, 0, -1))


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


AGENTS = [{"id": "b1", "name": "Builder-1", "status": "error"}, {"id": "pr", "name": "Principal", "status": "idle"}]
ISSUES = [{"id": "i1", "identifier": "AGE-23", "title": "Structured data", "status": "in_review",
           "assigneeAgentId": "b1", "updatedAt": iso(NOON - 60)}]


def failed(rid, minutes_ago, error="Claude exited with code 1: API Error 529 overloaded", agent="b1"):
    t = NOON - minutes_ago * 60
    return {"id": rid, "agentId": agent, "status": "failed", "createdAt": iso(t - 60), "finishedAt": iso(t),
            "errorCode": "adapter_failed", "error": error, "contextSnapshot": {"issueId": "i1"}}


class Plan(unittest.TestCase):
    def kinds(self, actions):
        return [(a[0], a[1]) for a in actions]

    def test_a_failed_run_is_retried_once_then_reported(self):
        watch = {}
        acts = watchdog.plan(NOON, AGENTS, [failed("r1", 15)], ISSUES, watch)
        self.assertEqual(acts, [("wake", "retry:r1", "b1", "i1", acts[0][4])])
        self.assertIn("trying once more", acts[0][4])
        self.assertEqual(watchdog.plan(NOON, AGENTS, [failed("r1", 15)], ISSUES, watch), [])  # still waiting
        acts = watchdog.plan(NOON, AGENTS, [failed("r1", 15), failed("r2", 2, error="Claude exited with code 1: API Error 529 overloaded")], ISSUES, watch)
        self.assertEqual(acts[0][0], "notify")
        self.assertIn("Builder-1 failed twice on AGE-23", acts[0][2])
        self.assertIn("API Error", acts[0][2])

    def test_a_different_failure_after_the_retry_gets_its_own_retry(self):
        watch = {}
        watchdog.plan(NOON, AGENTS, [failed("r1", 15)], ISSUES, watch)
        acts = watchdog.plan(NOON, AGENTS, [failed("r2", 12, error="something else")], ISSUES, watch)
        self.assertEqual(self.kinds(acts), [("wake", "retry:r2")])

    def test_not_retried_too_soon_at_night_or_for_cap_refusals(self):
        self.assertEqual(watchdog.plan(NOON, AGENTS, [failed("r1", 2)], ISSUES, {}), [])
        self.assertEqual(watchdog.plan(NOON, AGENTS, [failed("r1", 15)], ISSUES, {}, quiet=True), [])
        cap = failed("r1", 30, error="studio-quota: claude cap reached; not starting")
        self.assertEqual(watchdog.plan(NOON, AGENTS, [cap], ISSUES, {}), [])  # the Clerk's resume_capped has those

    def test_a_success_clears_the_failure(self):
        watch = {}
        watchdog.plan(NOON, AGENTS, [failed("r1", 15)], ISSUES, watch)
        ok = {**failed("r2", 5), "status": "succeeded", "error": None}
        watchdog.plan(NOON, AGENTS, [failed("r1", 15), ok], ISSUES, watch)
        self.assertEqual(watch["fails"], {})

    def test_a_silent_run_is_reported_then_cancelled_and_retried(self):
        run = {"id": "r9", "agentId": "b1", "status": "running", "createdAt": iso(NOON - 3600 * 2),
               "lastOutputAt": iso(NOON - 35 * 60), "contextSnapshot": {"issueId": "i1"}}
        acts = watchdog.plan(NOON, AGENTS, [run], ISSUES, {})
        self.assertEqual(self.kinds(acts), [("notify", "silent:r9")])
        self.assertIn("written nothing for 35 min on AGE-23", acts[0][2])
        run["lastOutputAt"] = iso(NOON - 61 * 60)
        acts = watchdog.plan(NOON, AGENTS, [run], ISSUES, {})
        self.assertEqual(self.kinds(acts), [("cancel", "cancel:r9"), ("notify", "cancelled:r9"), ("wake", "after-cancel:r9")])

    def test_idle_work_is_woken_twice_a_day_then_reported(self):
        agents = [{"id": "b1", "name": "Builder-1", "status": "idle"}]
        issues = [{**ISSUES[0], "status": "in_progress", "updatedAt": iso(NOON - 3 * 3600)}]
        runs = [{**failed("r1", 200), "status": "succeeded", "error": None}]
        watch = {}
        first = watchdog.plan(NOON, agents, runs, issues, watch)
        second = watchdog.plan(NOON, agents, runs, issues, watch)
        third = watchdog.plan(NOON, agents, runs, issues, watch)
        self.assertEqual([a[0] for a in first + second], ["wake", "wake"])
        self.assertEqual(third[0][0], "notify")
        self.assertIn("AGE-23 \"Structured data\" (Builder-1) has had no progress for 3 h", third[0][2])

    def test_work_waiting_for_review_or_a_human_is_not_idle(self):
        agents = [{"id": "b1", "name": "Builder-1", "status": "idle"}]
        issues = [{**ISSUES[0], "status": "in_review", "updatedAt": iso(NOON - 9 * 3600)}]
        self.assertEqual(watchdog.plan(NOON, agents, [], issues, {}), [])

    def test_a_blocked_issue_is_reported_with_its_latest_comment(self):
        issues = [{**ISSUES[0], "status": "blocked", "_latest_comment": "GitHub refused the push: no workflows permission"}]
        acts = watchdog.plan(NOON, AGENTS, [], issues, {})
        self.assertEqual(acts[0][0], "notify")
        self.assertIn("AGE-23 \"Structured data\" is blocked. Latest: GitHub refused the push", acts[0][2])


class Notify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = os.path.join(self.tmp.name, "notify.json")
        json.dump({"ntfy_url": "https://example.invalid/t"}, open(self.cfg, "w"))
        self.pushed = []

    def tearDown(self):
        self.tmp.cleanup()

    def push(self, cfg, text):
        self.pushed.append(text)
        return True

    def test_sent_by_day_held_at_night_and_flushed_in_the_morning(self):
        d = self.tmp.name
        self.assertEqual(notify.send(d, "a", NOON, self.cfg, self.push), "sent")
        self.assertEqual(notify.send(d, "b", NIGHT, self.cfg, self.push), "held")
        self.assertEqual(notify.send(d, "c", NIGHT, self.cfg, self.push), "held")
        self.assertTrue(notify.flush(d, NOON + 86400, self.cfg, self.push))
        self.assertEqual(self.pushed, ["a", "Overnight:\n- b\n- c"])
        self.assertFalse(notify.flush(d, NOON + 86400, self.cfg, self.push))  # nothing left
        self.assertEqual(len(open(os.path.join(d, "log", "notify.jsonl")).readlines()), 3)

    def test_without_a_channel_it_is_only_logged_and_a_failing_channel_does_not_raise(self):
        d = self.tmp.name
        self.assertEqual(notify.send(d, "a", NOON, os.path.join(d, "none.json")), "logged")

        def broken(cfg, text):
            raise OSError("down")
        self.assertEqual(notify.send(d, "b", NOON, self.cfg, broken), "failed")


class Outside(unittest.TestCase):
    def load(self):
        loader = importlib.machinery.SourceFileLoader("studio_watchdog", os.path.join(ROOT, "bin", "studio-watchdog"))
        spec = importlib.util.spec_from_loader("studio_watchdog", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod

    def test_paperclip_down_and_a_stale_clerk_are_reported(self):
        mod = self.load()
        with tempfile.TemporaryDirectory() as d:
            found = mod.problems(time.time(), url="http://127.0.0.1:9", data=d)
            self.assertEqual([k for k, _ in found], ["paperclip"])
            self.assertIn("not answering", found[0][1])
