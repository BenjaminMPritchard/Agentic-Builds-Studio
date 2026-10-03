import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXEC = os.path.join(ROOT, "bin", "agent-exec")


def run(*args, **env):
    return subprocess.run([EXEC, *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          env={**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1",
                               # the host's real App config must not leak in; token handling is in test_agent_identity
                               "STUDIO_AGENTS_APP_CONFIG": "/nonexistent/agents-app.json",
                               "STUDIO_AGENT_CACHE": "/nonexistent/agent-cache", **env})


class AgentExec(unittest.TestCase):
    def test_runs_the_cli_as_studio_agent_with_parent_death_kill(self):
        r = run("--print", "-", "--settings", "/srv/studio/claude/director.json")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith(
            "sudo -n -E -H -u studio-agent -- /usr/bin/setpriv --pdeathsig KILL -- "
            "/home/studio-agent/.local/bin/claude --print - --settings /srv/studio/claude/director.json"))

    def test_claude_runs_share_one_package_cache_when_it_exists(self):
        with tempfile.TemporaryDirectory() as cache:
            r = run("--print", "-", "--settings", "/srv/studio/claude/director.json", STUDIO_AGENT_CACHE=cache)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"UV_CACHE_DIR={cache}/uv\nnpm_config_cache={cache}/npm\n", r.stdout)

    def test_refuses_without_settings_so_guard_cannot_be_skipped(self):
        r = run("--print", "-")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")
        self.assertIn("--settings", r.stderr)

    def test_a_refusal_reads_the_prompt_so_paperclip_never_writes_into_a_closed_pipe(self):
        # Paperclip crashed on that EPIPE (2026-10-02). 1 MB is far more than a pipe holds, so without the read the
        # write below fails with BrokenPipeError once the wrapper has exited.
        p = subprocess.Popen([EXEC, "--print", "-"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.PIPE, env={**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1"})
        p.stdin.write(b"x" * (1 << 20))
        p.stdin.close()
        self.assertEqual(p.wait(timeout=15), 2)
        self.assertIn(b"--settings", p.stderr.read())


if __name__ == "__main__":
    unittest.main()
