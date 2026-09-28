import os, subprocess, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEC = os.path.join(ROOT, "bin", "agent-exec")


def run(*args):
    return subprocess.run([EXEC, *args], capture_output=True, text=True,
                          env={**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1"})


class AgentExec(unittest.TestCase):
    def test_runs_the_cli_as_studio_agent_with_parent_death_kill(self):
        r = run("--print", "-", "--settings", "/srv/studio/claude/director.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith(
            "sudo -n -E -H -u studio-agent -- /usr/bin/setpriv --pdeathsig KILL -- "
            "/home/studio-agent/.local/bin/claude --print - --settings /srv/studio/claude/director.json"))

    def test_refuses_without_settings_so_guard_cannot_be_skipped(self):
        r = run("--print", "-")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")
        self.assertIn("--settings", r.stderr)


if __name__ == "__main__":
    unittest.main()
