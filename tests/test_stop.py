import os, tempfile, unittest

from lib import stop

C = "company"


class FakePC:
    """Pause cancels the agent's active runs and stamps a new pausedAt, as Paperclip does."""
    def __init__(self, agents, runs=()):
        self.agents = {a["id"]: dict(a) for a in agents}
        self.run_list = [dict(r) for r in runs]
        self.clock, self.calls = 0, []

    def list_agents(self, company_id):
        return [dict(a) for a in self.agents.values()]

    def runs(self, company_id, limit=50):
        return [dict(r) for r in self.run_list]

    def pause_agent(self, aid):
        self.clock += 1
        self.calls.append(("pause", aid))
        a = self.agents[aid]
        a.update(status="paused", pausedAt=f"t{self.clock}")
        for r in self.run_list:
            if r["agentId"] == aid and r["status"] in stop.ACTIVE:
                r["status"] = "cancelled"
        return dict(a)

    def resume_agent(self, aid):
        self.calls.append(("resume", aid))
        self.agents[aid].update(status="idle", pausedAt=None)


def agent(aid, status="idle", paused_at=None):
    return {"id": aid, "name": aid, "status": status, "pausedAt": paused_at}


class Stop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "stop-state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_stop_pauses_only_unpaused_agents_and_resume_restores_only_those(self):
        pc = FakePC([agent("a"), agent("h", "paused", "human-t0")])
        stop.stop(pc, C, self.path)
        self.assertEqual(pc.calls, [("pause", "a")])
        stop.resume(pc, C, self.path)
        self.assertEqual(pc.agents["a"]["status"], "idle")
        self.assertEqual(pc.agents["h"], agent("h", "paused", "human-t0"))  # human pause untouched

    def test_resume_leaves_an_agent_repaused_since(self):
        pc = FakePC([agent("a")])
        stop.stop(pc, C, self.path)
        pc.agents["a"]["pausedAt"] = "human-later"  # a human paused it again after us
        out = stop.resume(pc, C, self.path)
        self.assertEqual(pc.agents["a"]["status"], "paused")
        self.assertNotIn(("resume", "a"), pc.calls)
        self.assertTrue(any("paused again" in line for line in out))
        self.assertEqual(stop.load_state(self.path)["paused_by_stop"], {})

    def test_resume_twice_is_harmless(self):
        pc = FakePC([agent("a")])
        stop.stop(pc, C, self.path)
        stop.resume(pc, C, self.path)
        stop.resume(pc, C, self.path)
        self.assertEqual(pc.calls.count(("resume", "a")), 1)

    def test_drain_waits_for_active_runs_and_never_cancels_them(self):
        pc = FakePC([agent("idle"), agent("busy")], runs=[{"agentId": "busy", "status": "running"}])
        ticks = []

        def sleep(_):
            ticks.append(1)
            if len(ticks) == 2:
                pc.run_list[0]["status"] = "succeeded"  # the run finishes on its own
        done, _ = stop.drain(pc, C, self.path, timeout=100, interval=1, sleep=sleep, now=lambda: len(ticks))
        self.assertTrue(done)
        self.assertEqual(pc.calls, [("pause", "idle"), ("pause", "busy")])
        self.assertEqual(pc.run_list[0]["status"], "succeeded")  # not cancelled

    def test_drain_times_out_without_forcing(self):
        pc = FakePC([agent("busy")], runs=[{"agentId": "busy", "status": "running"}])
        ticks = []
        done, out = stop.drain(pc, C, self.path, timeout=3, interval=1, sleep=lambda _: ticks.append(1),
                               now=lambda: len(ticks))
        self.assertFalse(done)
        self.assertEqual(pc.calls, [])
        self.assertEqual(pc.run_list[0]["status"], "running")
        self.assertIn("busy", out[-1])

    def test_each_pause_is_recorded_before_the_next(self):
        pc = FakePC([agent("a"), agent("b")])
        orig = pc.pause_agent

        def pause_then_crash(aid):
            if aid == "b":
                raise RuntimeError("crash")
            return orig(aid)
        pc.pause_agent = pause_then_crash
        with self.assertRaises(RuntimeError):
            stop.stop(pc, C, self.path)
        self.assertIn("a", stop.load_state(self.path)["paused_by_stop"])

    def test_status_labels_pause_owner(self):
        pc = FakePC([agent("a"), agent("h", "paused", "human-t0"), agent("r")], runs=[{"agentId": "r", "status": "running"}])
        stop.stop(pc, C, self.path)
        pc.agents["r"]["status"] = "idle"; pc.agents["r"]["pausedAt"] = None
        pc.run_list[0]["status"] = "running"
        lines = {line.split()[0]: line for line in stop.status(pc, C, self.path)}
        self.assertIn("studio-stop", lines["a"])
        self.assertIn("other", lines["h"])
        self.assertIn("active run", lines["r"])


if __name__ == "__main__":
    unittest.main()
