"""agent-exec runs Codex agents only with the Studio's managed Codex limits in place."""
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUIREMENTS = os.path.join(ROOT, "deploy", "codex", "requirements.toml")


class CodexExec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "bin", "agent-exec"), os.path.join(self.tmp, "agent-exec"))
        os.symlink(os.path.join(ROOT, "bin", "agent-stage"), os.path.join(self.tmp, "agent-stage"))
        self.req = os.path.join(self.tmp, "requirements.toml")
        shutil.copy(REQUIREMENTS, self.req)
        self.log = os.path.join(self.tmp, "quota.log")
        quota = os.path.join(self.tmp, "quota")
        with open(quota, "w") as f:
            f.write(f'#!/usr/bin/env bash\necho "$*" >> {self.log}\n[ "$1" = admit ] && echo tok\nexit 0\n')
        os.chmod(quota, 0o755)
        self.env = {**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1", "STUDIO_AGENTS_APP_CONFIG": "/nonexistent",
                    "STUDIO_AGENT_PROVIDER": "codex", "STUDIO_CODEX_REQUIREMENTS": self.req,
                    "STUDIO_AGENT_STAGE_DIR": os.path.join(self.tmp, "runs"), "STUDIO_QUOTA": quota,
                    "STUDIO_QUOTA_POLL": "0.1", "STUDIO_QUOTA_SETTLE": "0", "PAPERCLIP_AGENT_ID": "cx",
                    "CODEX_HOME": "/home/paperclip/.paperclip/agents/cx/codex-home", "OPENAI_API_KEY": "sk-x",
                    "STUDIO_AGENT_CACHE": os.path.join(self.tmp, "no-cache")}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_(self, *args):
        return subprocess.run([os.path.join(self.tmp, "agent-exec"), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              env=self.env, cwd=self.tmp)

    def test_a_codex_run_uses_the_codex_cli_the_studio_home_and_its_own_cap(self):
        r = self.run_("exec", "--json", "--model", "gpt-6-sol", "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("/usr/bin/setpriv --pdeathsig KILL -- /usr/local/bin/codex exec --json --model gpt-6-sol -", r.stdout)
        self.assertIn("CODEX_HOME=/srv/studio/data/codex-home\n", r.stdout)  # not Paperclip's unreadable home
        self.assertIn("OPENAI_API_KEY=\n", r.stdout)  # no API billing
        self.assertTrue(open(self.log).read().startswith("admit --provider codex --agent cx"))

    def test_each_repositorys_git_folder_under_the_writable_roots_is_made_writable(self):
        # Codex mounts <root>/.git read-only; a .git named as a root of its own is writable, so builders can commit.
        projects = os.path.join(self.tmp, "projects")
        os.makedirs(os.path.join(projects, "mothers", "repo", ".git", "objects"))
        os.makedirs(os.path.join(projects, "mothers", "worktrees", "AGE-1"))
        open(os.path.join(projects, "mothers", "worktrees", "AGE-1", ".git"), "w").close()  # a worktree's pointer file
        roots = f'sandbox_workspace_write.writable_roots=["{projects}"]'
        r = self.run_("exec", "-c", roots, "--skip-git-repo-check", "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = shlex.split(r.stdout.splitlines()[0])
        git = os.path.join(projects, "mothers", "repo", ".git")
        self.assertEqual(argv[argv.index("-c", argv.index("exec")) + 1],
                         f'sandbox_workspace_write.writable_roots=["{projects}","{git}"]')
        self.assertEqual(argv[-2:], ["--skip-git-repo-check", "-"])  # extended in place, nothing appended

    def test_the_shared_package_cache_is_used_and_writable_in_the_sandbox(self):
        cache = os.path.join(self.tmp, "agent-cache")
        os.makedirs(cache)
        projects = os.path.join(self.tmp, "projects")
        os.makedirs(projects)
        self.env.update(STUDIO_AGENT_CACHE=cache, UV_CACHE_DIR="/tmp/run-1/uv")  # a run's own scratch cache loses
        r = self.run_("exec", "-c", f'sandbox_workspace_write.writable_roots=["{projects}"]', "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = shlex.split(r.stdout.splitlines()[0])
        self.assertIn(f'sandbox_workspace_write.writable_roots=["{cache}","{projects}"]', argv)
        self.assertIn(f"UV_CACHE_DIR={cache}/uv\n", r.stdout)
        self.assertIn(f"npm_config_cache={cache}/npm\n", r.stdout)

    def test_without_the_shared_cache_folder_nothing_changes(self):
        roots = f'sandbox_workspace_write.writable_roots=["{self.tmp}"]'
        r = self.run_("exec", "-c", roots, "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(roots, shlex.split(r.stdout.splitlines()[0]))
        self.assertIn("UV_CACHE_DIR=\n", r.stdout)

    def test_gh_reads_the_agents_own_settings_not_paperclips(self):
        self.env["GH_CONFIG_DIR"] = "/home/paperclip/.config/gh"
        r = self.run_("exec", "-")
        self.assertIn("GH_CONFIG_DIR=/home/studio-agent/.config/gh\n", r.stdout)

    def test_an_agent_without_writable_roots_gets_none(self):
        r = self.run_("exec", "--skip-git-repo-check", "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("writable_roots", r.stdout)

    def test_paperclips_files_in_the_codex_home_are_opened_to_the_agent_group(self):
        home = os.path.join(self.tmp, "codex-home")
        os.makedirs(os.path.join(home, "skills"), mode=0o700)
        cfg = os.path.join(home, "config.toml")
        fd = os.open(cfg, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        self.env["STUDIO_CODEX_HOME"] = home
        r = self.run_("exec", "-")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.stat(cfg).st_mode & 0o070, 0o060)
        self.assertEqual(os.stat(os.path.join(home, "skills")).st_mode & 0o070, 0o070)

    def test_a_config_codex_left_unreadable_is_removed_after_the_run(self):
        # Codex rewrites config.toml as studio-agent, mode 0600; Paperclip could not open it for the next run.
        home = os.path.join(self.tmp, "codex-home")
        os.makedirs(home)
        cfg = os.path.join(home, "config.toml")
        open(cfg, "w").close()
        os.chmod(cfg, 0)
        self.env["STUDIO_CODEX_HOME"] = home
        self.env.pop("STUDIO_AGENT_EXEC_DRY_RUN")  # the watcher runs only for a real start
        self.env["STUDIO_AGENT_CLI"] = "/bin/true"
        r = self.run_("exec", "-")
        for _ in range(50):
            if not os.path.exists(cfg):
                break
            time.sleep(0.1)
        self.assertFalse(os.path.exists(cfg), r.stderr)

    def test_paperclips_mcp_headers_are_given_the_key_codex_reads(self):
        home = os.path.join(self.tmp, "codex-home")
        os.makedirs(home)
        cfg = os.path.join(home, "config.toml")
        with open(cfg, "w") as f:
            f.write('model = "x"\nheaders = "not an mcp table"\n\n'
                    '[mcp_servers."paperclip-projects"]\nurl = "http://127.0.0.1:3100/mcp"\n'
                    'headers = { Authorization = "Bearer k" }\n[mcp_servers."paperclip-connections"]\n'
                    'url = "http://127.0.0.1:3100/c"\nheaders = { Authorization = "Bearer j" }\n\n[other]\nheaders = 1\n')
        self.env["STUDIO_CODEX_HOME"] = home
        self.assertEqual(self.run_("exec", "-").returncode, 0)
        text = open(cfg).read()
        self.assertIn('http_headers = { Authorization = "Bearer k" }', text)
        self.assertIn('http_headers = { Authorization = "Bearer j" }', text)  # the second MCP table too
        self.assertIn('headers = "not an mcp table"', text)  # outside MCP tables: untouched
        self.assertIn("[other]\nheaders = 1", text)

    def test_no_settings_file_is_needed_but_the_managed_limits_are(self):
        for line in ("allow_managed_hooks_only = true", 'command = "/srv/studio/bin/guard"', "multi_agent = false",
                     "multi_agent_v2 = false", 'allowed_sandbox_modes = ["read-only", "workspace-write"]'):
            text = open(REQUIREMENTS).read()
            self.assertIn(line, text)
            with open(self.req, "w") as f:
                f.write(text.replace(line, "# removed"))
            r = self.run_("exec", "-")
            self.assertEqual((r.returncode, r.stdout), (2, ""), line)
            self.assertIn("does not pin", r.stderr)
        os.remove(self.req)
        self.assertEqual(self.run_("exec", "-").returncode, 2)

    def test_bypass_flags_are_refused(self):
        for flag in ("--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust"):
            r = self.run_("exec", flag, "-")
            self.assertEqual((r.returncode, r.stdout), (2, ""), flag)

    def test_an_unknown_provider_is_refused(self):
        self.env["STUDIO_AGENT_PROVIDER"] = "gemini"
        self.assertEqual(self.run_("exec", "-").returncode, 2)

    def test_the_guard_hook_covers_codex_shell_and_patch_tools(self):
        text = open(REQUIREMENTS).read()
        self.assertIn('matcher = ".*"', text)


class CodexSudo(unittest.TestCase):
    def test_paperclip_may_start_only_the_system_codex_as_studio_agent(self):
        rules = open(os.path.join(ROOT, "deploy", "studio-agent", "sudoers")).read()
        self.assertIn("paperclip ALL=(studio-agent) NOPASSWD:SETENV: /usr/bin/setpriv --pdeathsig KILL -- "
                      "/usr/local/bin/codex *\n", rules)
        self.assertEqual(rules.count("codex *"), 1)


class CodexAgents(unittest.TestCase):
    def test_payloads_match_the_routing_table_and_stay_confined(self):
        routing = json.load(open(os.path.join(ROOT, "policy", "routing.json")))["agents"]
        for folder in ("codex-scout", "codex-builder", "codex-principal"):
            a = json.load(open(os.path.join(ROOT, "package", "payloads", f"agent-{folder}.json")))
            c, env = a["adapterConfig"], a["adapterConfig"]["env"]
            self.assertEqual(a["adapterType"], "codex_local")
            self.assertEqual((c["engine"], c["command"]), ("cli", "/srv/studio/bin/agent-exec"))
            self.assertIs(c["dangerouslyBypassApprovalsAndSandbox"], False)
            self.assertIs(c["fastMode"], False)  # fast mode spends included usage faster (research 4.1)
            self.assertEqual(env["STUDIO_AGENT_PROVIDER"]["value"], "codex")
            self.assertEqual(env["CODEX_HOME"]["value"], "/srv/studio/data/codex-home")
            self.assertEqual(env["OPENAI_API_KEY"], {"type": "plain", "value": ""})  # never API billing
            self.assertEqual((c["model"], c["modelReasoningEffort"]),
                             (routing[a["name"]]["model"], routing[a["name"]]["effort"]))
            for f in ("AGENTS.md", "HEARTBEAT.md", "TOOLS.md"):
                self.assertTrue(os.path.isfile(os.path.join(ROOT, "agents", folder, f)), (folder, f))
            text = open(os.path.join(ROOT, "agents", folder, "AGENTS.md")).read()
            self.assertIn("never", text)
            self.assertIn("sub-agents", text)


if __name__ == "__main__":
    unittest.main()
