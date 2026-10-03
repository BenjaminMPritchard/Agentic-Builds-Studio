"""Agents act on GitHub as the agents' App, never with an inherited personal token."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from lib.github_app import GitHubAppError, account_installation_token
from tests.test_github_app import Base, FakeOpener

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AccountToken(Base):
    def test_token_for_an_accounts_installation(self):
        opener = FakeOpener([{"id": 42}, {"token": "ghs_agents"}])
        self.assertEqual(account_installation_token("Agentic-Builds-Studio-Client-Pages", 7, self.key_path, opener=opener),
                         "ghs_agents")
        lookup, mint = opener.calls
        self.assertEqual(lookup.full_url, "https://api.github.com/users/Agentic-Builds-Studio-Client-Pages/installation")
        self.assertEqual(mint.full_url, "https://api.github.com/app/installations/42/access_tokens")
        self.assertEqual(mint.get_method(), "POST")
        self.assertTrue(mint.get_header("Authorization").startswith("Bearer "))

    def test_bad_owner_and_missing_token_raise(self):
        with self.assertRaises(GitHubAppError):
            account_installation_token("owner/repo", 7, self.key_path, opener=FakeOpener([]))
        with self.assertRaises(GitHubAppError):
            account_installation_token("someone", 7, self.key_path, opener=FakeOpener([{"id": 1}, {}]))


class AgentExecToken(unittest.TestCase):
    """agent-exec is copied beside a fake agent-github-token so no network or key is involved."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "bin", "agent-exec"), os.path.join(self.tmp, "agent-exec"))
        os.symlink(os.path.join(ROOT, "bin", "agent-stage"), os.path.join(self.tmp, "agent-stage"))
        self.config = os.path.join(self.tmp, "agents-app.json")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    grant_line = '[ "$1" = --new-grant ] && { echo 0123456789abcdef0123456789abcdef; exit 0; }\n'

    def fake_token_cmd(self, body):
        p = os.path.join(self.tmp, "agent-github-token")
        with open(p, "w") as f:
            f.write("#!/usr/bin/env bash\n" + self.grant_line + body + "\n")
        os.chmod(p, 0o755)

    def run_exec(self, configured=True, owner=None):
        if configured:
            with open(self.config, "w") as f:
                json.dump({"app_id": 7, "key_path": "/nonexistent"}, f)
        env = {**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1", "STUDIO_AGENTS_APP_CONFIG": self.config,
               "GH_TOKEN": "personal-token-of-benjamin", "GITHUB_TOKEN": "personal-token-of-benjamin"}
        if owner:
            env["STUDIO_AGENT_GITHUB_OWNER"] = owner
        return subprocess.run([os.path.join(self.tmp, "agent-exec"), "--settings", "/srv/studio/claude/liaison.json"],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL, env=env)

    def test_app_token_replaces_the_personal_token(self):
        self.fake_token_cmd('[ "$1" = "Agentic-Builds-Studio-Client-Pages" ] && echo ghs_app_token_123')
        r = self.run_exec()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GH_TOKEN=ghs_app_", r.stdout)
        self.assertIn("GITHUB_TOKEN=\n", r.stdout)  # the inherited GITHUB_TOKEN is unset
        self.assertNotIn("personal-token", r.stdout)

    def test_owner_setting_selects_the_account(self):
        self.fake_token_cmd('[ "$1" = "BenjaminMPritchard" ] && echo ghs_studio_repo || exit 1')
        r = self.run_exec(owner="BenjaminMPritchard")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GH_TOKEN=ghs_stud", r.stdout)

    def test_no_token_means_the_run_does_not_start(self):
        self.fake_token_cmd("exit 1")
        r = self.run_exec()
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.stdout, "")
        self.assertIn("not starting", r.stderr)

    def test_without_app_config_the_environment_passes_through(self):
        self.fake_token_cmd("echo should-not-be-called; exit 1")
        r = self.run_exec(configured=False)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("GH_TOKEN=personal", r.stdout)  # unchanged: nothing configured yet
        self.assertNotIn("should-not-be-called", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
