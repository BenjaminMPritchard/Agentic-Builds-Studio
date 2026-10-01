"""Usage caps: readings, studio attribution, admission and the agent-exec wiring."""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from lib import quota
from lib.quota import QuotaError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "policy", "quota.json")) as _f:
    POLICY = json.load(_f)["claude"]
POLICY = {**POLICY, "five_hour_cap": 12}  # the controller scenarios below are worked for a 12-point cap

USAGE = """You are currently using your subscription to power your Claude Code usage

Current session: {s}% used · resets {sk}
Current week (all models): {w}% used · resets {wk}

What's contributing to your limits usage?
Last 24h · 724 requests · 3 sessions
"""


NOW = 1790650000.0  # 2026-09-29 ~03:46 London: a fixed clock for reset-time parsing


def reading(s, w, sk="Sep 29, 6:50am (Europe/London)", wk="Oct 5, 9am (Europe/London)", extra=""):
    return quota.parse_usage(USAGE.format(s=s, w=w, sk=sk, wk=wk) + extra, now=NOW)


def alive(pid):
    return pid != 999


class Parse(unittest.TestCase):
    def test_real_output(self):
        r = reading(73, 22)
        self.assertEqual(r["five_hour"], {"pct": 73.0, "key": "Sep 29, 6:50am (Europe/London)", "at": 1790661000.0})
        self.assertEqual(r["week"], {"pct": 22.0, "key": "Oct 5, 9am (Europe/London)", "at": 1791187200.0})
        self.assertEqual(r["other"], {})

    def test_reset_times_are_read_as_times(self):
        self.assertEqual(quota.parse_reset("7:40am (Europe/London)", NOW), 1790664000.0)  # today, no date
        self.assertEqual(quota.parse_reset("Jan 2, 9am (Europe/London)", NOW), 1798880400.0)  # next year
        for bad in ("", "soon", "Sep 29, 6:50am (Not/AZone)"):
            self.assertIsNone(quota.parse_reset(bad, NOW), bad)

    def test_model_specific_week_is_kept_separately(self):
        r = reading(1, 2, extra="Current week (Opus): 40% used · resets Oct 5, 9am (Europe/London)\n")
        self.assertEqual(r["other"], {"Opus": 40.0})

    def test_no_reading_is_an_error_not_zero(self):
        for text in ("", "Error: not logged in", "Current session: 5% used · resets 1pm\n"):
            with self.assertRaises(QuotaError, msg=text):
                quota.parse_usage(text)


class ParseCodex(unittest.TestCase):
    # The shape `account/rateLimits/read` returned for Benjamin's Plus account on 2026-09-30.
    REAL = {"ordinaryUsageAllowed": False, "rateLimitsByLimitId": {"codex": {
        "limitId": "codex", "primary": {"usedPercent": 100, "windowDurationMins": 300, "resetsAt": 1790739358},
        "secondary": {"usedPercent": 37, "windowDurationMins": 10080, "resetsAt": 1791151189},
        "credits": {"hasCredits": False, "unlimited": False, "balance": "0"}, "planType": "plus"}}}

    def test_real_result(self):
        r = quota.parse_codex(self.REAL)
        self.assertEqual(r["five_hour"], {"pct": 100.0, "key": "Sep 30 03:35 UTC", "at": 1790739358.0})
        self.assertEqual(r["week"], {"pct": 37.0, "key": "Oct 04 21:59 UTC", "at": 1791151189.0})

    def test_windows_are_found_by_length_not_by_slot(self):
        swapped = {"rateLimitsByLimitId": {"codex": {
            "primary": {"usedPercent": 5, "windowDurationMins": 10080, "resetsAt": 2},
            "secondary": {"usedPercent": 50, "windowDurationMins": 300, "resetsAt": 1}}}}
        r = quota.parse_codex(swapped)
        self.assertEqual((r["five_hour"]["pct"], r["week"]["pct"]), (50.0, 5.0))

    def test_other_buckets_count_only_toward_account_headroom(self):
        res = dict(self.REAL["rateLimitsByLimitId"])
        res["gpt-6-astra"] = {"primary": {"usedPercent": 99.8, "windowDurationMins": 10080, "resetsAt": 3}}
        r = quota.parse_codex({"rateLimitsByLimitId": res})
        self.assertEqual(r["other"], {"gpt-6-astra week": 99.8})

    def test_anything_unexpected_is_no_reading(self):
        for bad in ({}, {"rateLimitsByLimitId": {"other": {}}},
                    {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 1, "windowDurationMins": 60}}}},
                    {"rateLimitsByLimitId": {"codex": {"primary": {"usedPercent": 1, "windowDurationMins": 300}}}},
                    {"rateLimitsByLimitId": {"codex": {"primary": {"windowDurationMins": 300},
                                                        "secondary": {"usedPercent": 1, "windowDurationMins": 10080}}}}):
            with self.assertRaises(QuotaError, msg=bad):
                quota.parse_codex(bad)


class Controller(unittest.TestCase):
    def setUp(self):
        self.l = quota.empty()
        self.t = 1000.0

    def admit(self, r, agent="rec", pid=1):
        self.t += 60
        return quota.admit(self.l, r, agent, pid, POLICY, self.t, pid_alive=alive)

    def test_usage_while_a_run_is_active_counts_as_studio_and_otherwise_as_personal(self):
        tok, why = self.admit(reading(50, 20))
        self.assertTrue(tok, why)
        quota.release(self.l, tok, reading(53, 20.5), self.t)
        # Personal use between runs is not studio use.
        tok2, _ = self.admit(reading(70, 25))
        s = quota.status(self.l, reading(70, 25), POLICY)
        self.assertEqual(s["studio"], {"five_hour": 3.0, "week": 0.5})
        self.assertEqual(self.l["samples"]["rec"], [[3.0, 0.5]])
        self.assertIn(tok2, self.l["active"])

    def test_the_studio_five_hour_cap_refuses_a_run(self):
        tok, _ = self.admit(reading(10, 10))
        quota.release(self.l, tok, reading(18.5, 11), self.t)  # studio has used 8.5 of 12
        tok, why = self.admit(reading(18.5, 11))
        self.assertIsNone(tok)  # 8.5 + 3 (estimate) + 1 (margin) > 12
        self.assertTrue(any(w.startswith("studio 5-hour") for w in why), why)

    def test_exactly_at_the_cap_is_allowed(self):
        tok, _ = self.admit(reading(10, 10))
        quota.release(self.l, tok, reading(18, 10), self.t)
        self.l["studio"]["five_hour"]["Sep 29, 6:50am (Europe/London)"] = 8.0
        tok, why = self.admit(reading(18, 10))
        self.assertTrue(tok, why)

    def test_reservations_of_active_runs_count(self):
        runs = [self.admit(reading(0, 0), pid=p)[0] for p in (1, 2, 3)]  # 3 x (3 + 1 margin) <= 12
        self.assertTrue(all(runs))
        tok, why = self.admit(reading(0, 0), pid=4)
        self.assertIsNone(tok)
        self.assertIn("reserved 9", why[0])

    def test_a_new_window_starts_studio_use_again(self):
        tok, _ = self.admit(reading(10, 10))
        quota.release(self.l, tok, reading(20, 11), self.t)
        tok, why = self.admit(reading(2, 11, sk="Sep 29, 11:50am (Europe/London)"))
        self.assertTrue(tok, why)
        self.assertEqual(quota.status(self.l, reading(2, 11, sk="Sep 29, 11:50am (Europe/London)"), POLICY)
                         ["studio"]["five_hour"], 0.0)

    def test_a_usage_reset_starts_the_window_again(self):
        # 2026-10-01: Benjamin reset Codex use. The reset time moved by 58 minutes (inside the tolerance for a
        # reworded time), so the old window's 100 points were carried over and every run was refused.
        tok, _ = self.admit(reading(0, 10))
        quota.release(self.l, tok, reading(100, 30), self.t)
        for sk in ("Sep 29, 6:50am (Europe/London)", "Sep 29, 7:48am (Europe/London)"):
            self.l["studio"]["five_hour"] = {"Sep 29, 6:50am (Europe/London)": 100.0}
            self.l["last"]["five_hour"] = reading(100, 30)["five_hour"]
            tok, why = self.admit(reading(3, 30, sk=sk), pid=7)
            self.assertTrue(tok, (sk, why))
            self.assertEqual(quota.status(self.l, reading(3, 30, sk=sk), POLICY)["studio"]["five_hour"], 0.0, sk)
            quota.release(self.l, tok, reading(3, 30, sk=sk), self.t)

    def fresh(self, studio_week, account_week):
        self.l = quota.empty()
        self.l["studio"]["week"]["Oct 5, 9am (Europe/London)"] = studio_week
        return self.admit(reading(0, account_week))

    def test_a_reworded_reset_time_is_the_same_window(self):
        # 2026-09-30: Scout's run moved the account from 27% to 30%; /usage said "7:40am" before the run and
        # "7:39am" after. That is one window: the run used 3 points, not 30.
        tok, _ = self.admit(reading(27, 31, sk="Sep 30, 7:40am (Europe/London)", wk="Oct 5, 9am (Europe/London)"))
        after = reading(30, 32, sk="Sep 30, 7:39am (Europe/London)", wk="Oct 5, 8:59am (Europe/London)")
        quota.release(self.l, tok, after, self.t)
        self.assertEqual(quota.status(self.l, after, POLICY)["studio"], {"five_hour": 3.0, "week": 1.0})
        self.assertEqual(self.l["finished"][0]["used"], {"five_hour": 3.0, "week": 1.0})

    def test_a_ledger_written_before_the_fix_is_still_read_correctly(self):
        self.l["last"] = {"t": NOW, "five_hour": {"pct": 27.0, "key": "Sep 30, 7:40am (Europe/London)"},
                          "week": {"pct": 31.0, "key": "Oct 5, 9am (Europe/London)"}}  # no "at": old format
        self.l["studio"]["week"] = {"Oct 5, 9am (Europe/London)": 1.0}
        quota.observe(self.l, reading(28, 31, sk="Sep 30, 7:39am (Europe/London)", wk="Oct 5, 8:59am (Europe/London)"), NOW)
        self.assertEqual(self.l["studio"]["week"], {"Oct 5, 8:59am (Europe/London)": 1.0})  # kept, not dropped

    def test_a_run_across_a_window_reset_counts_in_the_new_window(self):
        tok, _ = self.admit(reading(10, 10))
        new = reading(2, 10.5, sk="Sep 29, 11:50am (Europe/London)")
        quota.release(self.l, tok, new, self.t)
        self.assertEqual(quota.status(self.l, new, POLICY)["studio"], {"five_hour": 2.0, "week": 0.5})

    def test_the_weekly_caps(self):
        self.assertTrue(self.fresh(79, 79)[0])  # 79 + 0.5 + 0.5 = 80: at the studio cap, allowed
        tok, why = self.fresh(79.5, 79.5)
        self.assertIsNone(tok)
        self.assertTrue(any(w.startswith("studio weekly") for w in why), why)
        # Personal use 5 of 20: 15 stays free for Ben. 75 + 0.5 + 0.5 + 15 = 91 fits.
        self.assertTrue(self.fresh(70, 75)[0])
        # Personal use far beyond 20 does not stop the studio below its own cap: 95 + 1 = 96 fits.
        self.assertTrue(self.fresh(10, 95)[0])
        # Ben's unused share is added on top: 79.5 studio + 0.5 personal leaves 19.5 for him -> refused twice.
        tok, why = self.fresh(79.5, 80)
        self.assertTrue(any("personal 19.5" in w for w in why), why)

    def test_account_week_nearly_full_refuses(self):
        tok, why = self.admit(reading(0, 99.5))
        self.assertIsNone(tok)
        self.assertTrue(any(w.startswith("account weekly") for w in why), why)

    def test_account_five_hour_nearly_full_refuses(self):
        tok, why = self.admit(reading(97, 10))
        self.assertIsNone(tok)
        self.assertTrue(any(w.startswith("account 5-hour") for w in why), why)

    def test_a_model_limit_that_is_full_refuses(self):
        r = reading(0, 0, extra="Current week (Opus): 100% used · resets Oct 5, 9am (Europe/London)\n")
        self.assertIsNone(self.admit(r)[0])

    def test_estimates_follow_measured_runs_after_enough_samples(self):
        self.l["samples"]["rec"] = [[5.0, 1.0], [2.0, 0.1], [0.2, 0.0]]
        self.assertEqual(quota.estimate(self.l, "rec", POLICY), {"five_hour": 5.0, "week": 1.0})
        self.l["samples"]["rec"] = [[0.2, 0.0]] * 3
        self.assertEqual(quota.estimate(self.l, "rec", POLICY), POLICY["min_job"])
        self.assertEqual(quota.estimate(self.l, "other", POLICY), POLICY["default_job"])

    def test_an_estimate_above_the_cap_is_held_to_what_an_empty_window_allows(self):
        # 2026-09-30: one Principal run was charged 45 points (Benjamin's own use at the same time counted too);
        # the estimate then exceeded the 12-point cap and the Principal could never start again.
        self.l["samples"]["rec"] = [[45.0, 3.0], [2.0, 0.1], [1.0, 0.1]]
        est = quota.estimate(self.l, "rec", POLICY)
        self.assertEqual(est["five_hour"], POLICY["five_hour_cap"] - POLICY["margin"]["five_hour"])
        self.assertEqual(est["week"], 3.0)
        tok, why = self.admit(reading(0, 0))
        self.assertIsNotNone(tok, why)  # an empty window admits it

    def test_a_run_whose_process_is_gone_is_not_charged_with_later_usage(self):
        # 2026-09-30: a Paperclip restart killed a run and its release watcher; hours of Benjamin's own use
        # were then charged to it at the next admission.
        tok, _ = self.admit(reading(10, 10), pid=999)  # pid 999 is "gone" in these tests
        tok2, _ = self.admit(reading(25, 12))
        self.assertNotIn(tok, self.l["active"])
        self.assertEqual(self.l["samples"]["rec"], [[0.0, 0.0]])
        self.assertEqual(quota.status(self.l, reading(25, 12), POLICY)["studio"], {"five_hour": 0.0, "week": 0.0})
        self.assertEqual(self.l["finished"][0]["ended"], "process gone")
        self.assertIn(tok2, self.l["active"])

    def test_release_without_a_reading_keeps_the_run_counted(self):
        tok, _ = self.admit(reading(10, 10))
        quota.release(self.l, tok, None, self.t)
        self.assertTrue(self.l["active"][tok]["ended"])
        self.admit(reading(13, 10), pid=2)
        self.assertNotIn(tok, self.l["active"])
        self.assertEqual(self.l["samples"]["rec"], [[3.0, 0.0]])

    def test_each_finished_run_leaves_one_record(self):
        tok, _ = self.admit(reading(10, 10))
        self.l["active"][tok]["run"] = "run-a"
        quota.release(self.l, tok, reading(13, 10.5), self.t)
        gone, _ = self.admit(reading(13, 10.5), pid=999)  # its process will be gone at the next admission
        self.l["active"][gone]["run"] = "run-b"
        self.admit(reading(14, 10.5), pid=2)
        recs = self.l["finished"]
        self.assertEqual([(r["run"], r["ended"]) for r in recs], [("run-a", "released"), ("run-b", "process gone")])
        self.assertEqual(recs[0]["used"], {"five_hour": 3.0, "week": 0.5})
        self.assertEqual((recs[0]["attribution"], recs[0]["windows"]["five_hour"]),
                         ("bounded", "Sep 29, 6:50am (Europe/London)"))
        path = os.path.join(tempfile.mkdtemp(), "claude-runs.jsonl")
        self.assertEqual(quota.flush_finished(self.l, path), 2)
        self.assertEqual(quota.flush_finished(self.l, path), 0)  # written once
        self.assertEqual([json.loads(l)["run"] for l in open(path)], ["run-a", "run-b"])
        self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
        shutil.rmtree(os.path.dirname(path))

    def test_a_correction_sets_the_current_window(self):
        tok, _ = self.admit(reading(10, 10))
        quota.release(self.l, tok, reading(40, 40), self.t)
        self.assertEqual(quota.correct(self.l, "five_hour", 3), ("Sep 29, 6:50am (Europe/London)", 30.0))
        self.assertEqual(quota.status(self.l, reading(40, 40), POLICY)["studio"]["five_hour"], 3.0)
        with self.assertRaises(QuotaError):
            quota.correct(quota.empty(), "week", 1)

    def test_very_old_runs_are_ended(self):
        tok, _ = self.admit(reading(10, 10))
        self.t += POLICY["max_run_hours"] * 3600 + 1
        self.admit(reading(10, 10), pid=2)
        self.assertNotIn(tok, self.l["active"])


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.claude = os.path.join(self.tmp, "claude")
        self.usage(40, 10)
        self.env = {**os.environ, "STUDIO_QUOTA_DIR": os.path.join(self.tmp, "q"), "STUDIO_QUOTA_CLAUDE_CLI": self.claude,
                    "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-run", "ANTHROPIC_API_KEY": "sk-ant-api"}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def usage(self, s, w, code=0):
        with open(self.claude, "w") as f:
            f.write("#!/usr/bin/env bash\n[ \"$1 $2\" = \"-p /usage\" ] || exit 9\n"
                    "[ -z \"$CLAUDE_CODE_OAUTH_TOKEN$ANTHROPIC_API_KEY\" ] || exit 8\ncat <<'EOF'\n"
                    + USAGE.format(s=s, w=w, sk="1pm", wk="Mon") + f"EOF\nexit {code}\n")
        os.chmod(self.claude, 0o755)

    def q(self, *args):
        return subprocess.run([os.path.join(ROOT, "bin", "studio-quota"), *args], capture_output=True, text=True,
                              env=self.env)

    def test_admit_release_and_status(self):
        r = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", str(os.getpid()), "--run", "run-9")
        self.assertEqual(r.returncode, 0, r.stderr)
        token = r.stdout.strip()
        self.usage(45, 11)
        self.assertEqual(self.q("release", "--provider", "claude", token).returncode, 0)
        s = json.loads(self.q("status", "--provider", "claude").stdout)
        self.assertEqual((s["studio"], s["active_runs"]), ({"five_hour": 5.0, "week": 1.0}, 0))
        rec = json.loads(open(os.path.join(self.tmp, "q", "claude-runs.jsonl")).read())
        self.assertEqual((rec["run"], rec["agent"], rec["used"]), ("run-9", "rec", {"five_hour": 5.0, "week": 1.0}))
        self.assertEqual(os.stat(os.path.join(self.tmp, "q", "claude.json")).st_mode & 0o777, 0o600)

    def test_a_run_is_stopped_when_studio_use_reaches_the_cap(self):
        # 2026-10-01: admission passed at 0% and one Codex run then took the whole five-hour window.
        token = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", str(os.getpid())).stdout.strip()
        run = subprocess.Popen(["sleep", "30"])
        self.usage(40 + 23, 12)  # 23 points of studio use since admission; the Claude cap is 22
        env = {**self.env, "STUDIO_QUOTA_POLL": "0.05", "STUDIO_QUOTA_SETTLE": "0", "STUDIO_QUOTA_CHECK": "0.2"}
        rel = subprocess.Popen([os.path.join(ROOT, "bin", "studio-quota"), "release", "--provider", "claude",
                                "--after-pid", str(run.pid), token], env=env, stderr=subprocess.PIPE, text=True)
        self.assertEqual(run.wait(timeout=10), -15)  # SIGTERM
        self.assertIn("reached the cap 22", rel.communicate(timeout=10)[1])
        stop = json.loads(open(os.path.join(self.tmp, "q", "stops.jsonl")).read())
        self.assertEqual((stop["pid"], stop["token"]), (run.pid, token))

    def test_a_run_inside_the_caps_is_left_alone(self):
        token = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", str(os.getpid())).stdout.strip()
        run = subprocess.Popen(["sleep", "1"])
        self.usage(45, 11)
        env = {**self.env, "STUDIO_QUOTA_POLL": "0.05", "STUDIO_QUOTA_SETTLE": "0", "STUDIO_QUOTA_CHECK": "0.2"}
        rel = subprocess.Popen([os.path.join(ROOT, "bin", "studio-quota"), "release", "--provider", "claude",
                                "--after-pid", str(run.pid), token], env=env)
        time.sleep(1.5)  # several checks while the run is alive
        self.assertEqual(run.wait(timeout=5), 0)
        rel.wait(timeout=10)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "q", "stops.jsonl")))

    def test_release_waits_for_the_run_to_end(self):
        r = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", str(os.getpid()))
        token = r.stdout.strip()
        run = subprocess.Popen(["sleep", "1"])
        env = {**self.env, "STUDIO_QUOTA_POLL": "0.05", "STUDIO_QUOTA_SETTLE": "0"}
        rel = subprocess.Popen([os.path.join(ROOT, "bin", "studio-quota"), "release", "--provider", "claude",
                                "--after-pid", str(run.pid), token], env=env)
        time.sleep(0.5)
        self.assertIsNone(rel.poll())  # still waiting while the run is alive
        run.wait()
        self.assertEqual(rel.wait(timeout=5), 0)
        self.assertEqual(json.loads(self.q("status", "--provider", "claude").stdout)["active_runs"], 0)

    def test_refusal_and_no_reading(self):
        self.usage(99, 10)
        r = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", "1")
        self.assertEqual((r.returncode, r.stdout), (5, ""))
        self.assertIn("account 5-hour", r.stderr)
        self.usage(1, 1, code=1)
        r = self.q("admit", "--provider", "claude", "--agent", "rec", "--pid", "1")
        self.assertEqual((r.returncode, r.stdout), (6, ""))
        self.env.update(STUDIO_QUOTA_CODEX_CLI=os.path.join(self.tmp, "missing-codex"), STUDIO_QUOTA_CODEX_USER="")
        r = self.q("admit", "--provider", "codex", "--agent", "rec", "--pid", "1")
        self.assertEqual((r.returncode, r.stdout), (6, ""))
        self.assertIn("no codex usage reading", r.stderr)

    def fake_codex(self, five, week, extra=None):
        result = {"rateLimitsByLimitId": {"codex": {
            "primary": {"usedPercent": five, "windowDurationMins": 300, "resetsAt": 1790739358},
            "secondary": {"usedPercent": week, "windowDurationMins": 10080, "resetsAt": 1791151189}}, **(extra or {})}}
        path = os.path.join(self.tmp, "codex")
        with open(path, "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, os, sys\n"
                    "assert sys.argv[1:] == ['app-server'] and not os.environ.get('OPENAI_API_KEY')\n"
                    "assert os.environ['CODEX_HOME'] == os.environ['EXPECT_HOME']\n"
                    "for line in sys.stdin:\n"
                    "    m = json.loads(line)\n"
                    "    if m.get('id') == 1: print(json.dumps({'id': 1, 'result': {}}), flush=True)\n"
                    "    if m.get('id') == 2:\n"
                    f"        print(json.dumps({{'method': 'account/updated'}}), flush=True)\n"
                    f"        print(json.dumps({{'id': 2, 'result': {json.dumps(result)}}}), flush=True)\n")
        os.chmod(path, 0o755)
        home = os.path.join(self.tmp, "codex-home")
        self.env.update(STUDIO_QUOTA_CODEX_CLI=path, STUDIO_CODEX_HOME=home, EXPECT_HOME=home, OPENAI_API_KEY="sk-x",
                        STUDIO_QUOTA_CODEX_USER="")  # no sudo in tests

    def test_codex_reading_and_its_own_cap(self):
        self.fake_codex(10, 37)
        s = json.loads(self.q("status", "--provider", "codex").stdout)
        self.assertEqual((s["account"], s["caps"]), ({"five_hour": 10.0, "week": 37.0}, {"five_hour": 28, "week": 80}))
        r = self.q("admit", "--provider", "codex", "--agent", "cx", "--pid", str(os.getpid()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.fake_codex(100, 37)  # the account's five-hour window is used up
        r = self.q("admit", "--provider", "codex", "--agent", "cx", "--pid", "2")
        self.assertEqual(r.returncode, 5)
        self.assertIn("account 5-hour", r.stderr)
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "q", "codex.json")))  # its own ledger
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "q", "claude.json")))


class AgentExecWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "bin", "agent-exec"), os.path.join(self.tmp, "agent-exec"))
        os.symlink(os.path.join(ROOT, "bin", "agent-stage"), os.path.join(self.tmp, "agent-stage"))
        self.log = os.path.join(self.tmp, "log")
        self.fake = os.path.join(self.tmp, "quota")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def exec_(self, admit_exit):
        with open(self.fake, "w") as f:
            f.write(f'#!/usr/bin/env bash\necho "$*" >> {self.log}\n'
                    f'[ "$1" = admit ] && {{ [ {admit_exit} = 0 ] && echo tok123; echo refused >&2; exit {admit_exit}; }}\n'
                    'exit 0\n')
        os.chmod(self.fake, 0o755)
        env = {**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1", "STUDIO_AGENTS_APP_CONFIG": "/nonexistent",
               "STUDIO_QUOTA": self.fake, "STUDIO_QUOTA_POLL": "0.1", "STUDIO_QUOTA_SETTLE": "0",
               "PAPERCLIP_AGENT_ID": "agent-1", "PAPERCLIP_RUN_ID": "run-7"}
        return subprocess.run([os.path.join(self.tmp, "agent-exec"), "--settings", "/srv/studio/claude/liaison.json"],
                              capture_output=True, text=True, env=env, timeout=10)

    def lines(self, want):
        for _ in range(50):
            if os.path.exists(self.log) and len(open(self.log).read().splitlines()) >= want:
                break
            time.sleep(0.1)
        return open(self.log).read().splitlines()

    def test_an_admitted_run_is_released_after_it_ends(self):
        r = self.exec_(0)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("setpriv", r.stdout)
        log = self.lines(2)
        self.assertRegex(log[0], r"^admit --provider claude --agent agent-1 --pid \d+ --run run-7$")
        self.assertRegex(log[1], r"^release --provider claude --after-pid \d+ tok123$")

    def test_a_refused_run_does_not_start(self):
        r = self.exec_(5)
        self.assertEqual((r.returncode, r.stdout), (5, ""))
        self.assertIn("refused", r.stderr)
        time.sleep(0.3)
        self.assertEqual(len(self.lines(1)), 1)


if __name__ == "__main__":
    unittest.main()
