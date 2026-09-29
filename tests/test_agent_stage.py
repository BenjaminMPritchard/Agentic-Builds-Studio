"""agent-exec stages Paperclip's instructions, prompt bundle and MCP config where studio-agent can read them."""
import grp
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from lib import agent_stage
from lib.agent_stage import StageError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MY_GROUP = grp.getgrgid(os.getegid()).gr_name


class Stage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "paperclip-home")  # stands in for /home/paperclip/.paperclip
        self.parent = os.path.join(self.tmp, "agent-runs")
        skill = os.path.join(self.home, "skills", "studio-house-rules")
        os.makedirs(skill)
        with open(os.path.join(skill, "SKILL.md"), "w") as f:
            f.write("house rules\n")
        self.bundle = os.path.join(self.home, "claude-prompt-cache", "abc")
        os.makedirs(os.path.join(self.bundle, ".claude", "skills"))
        os.symlink(skill, os.path.join(self.bundle, ".claude", "skills", "studio-house-rules"))
        self.instructions = os.path.join(self.bundle, "agent-instructions.md")
        with open(self.instructions, "w") as f:
            f.write("You are the Recorder.\n")
        self.mcp = os.path.join(self.home, "state", "mcp.json")
        os.makedirs(os.path.dirname(self.mcp))
        with open(self.mcp, "w") as f:
            json.dump({"mcpServers": {}}, f)
        self.args = ["--print", "-", "--model", "claude-sonnet-5", "--append-system-prompt-file", self.instructions,
                     "--mcp-config", self.mcp, "--strict-mcp-config", "--add-dir", self.bundle,
                     "--settings", "/srv/studio/claude/liaison.json"]

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def staged(self, **kw):
        return agent_stage.stage(self.args, parent=self.parent, group=MY_GROUP, **kw)

    def test_other_arguments_are_untouched_and_nothing_is_created_without_files(self):
        plain = ["--print", "-", "--settings", "/srv/studio/claude/liaison.json"]
        self.assertEqual(agent_stage.stage(plain, parent=self.parent, group="no-such-group"), plain)
        self.assertFalse(os.path.exists(self.parent))

    def test_files_and_the_bundle_are_copied_and_the_arguments_rewritten(self):
        out = self.staged()
        self.assertEqual(len(out), len(self.args))
        for flag in ("--append-system-prompt-file", "--mcp-config", "--add-dir"):
            src, dst = self.args[self.args.index(flag) + 1], out[out.index(flag) + 1]
            self.assertTrue(dst.startswith(self.parent + os.sep), dst)
            self.assertNotEqual(src, dst)
        keep = [a for a in self.args if not a.startswith(self.home)]
        self.assertEqual([a for a in out if not a.startswith(self.parent)], keep)
        with open(out[out.index("--append-system-prompt-file") + 1]) as f:
            self.assertEqual(f.read(), "You are the Recorder.\n")
        skill = os.path.join(out[out.index("--add-dir") + 1], ".claude", "skills", "studio-house-rules")
        self.assertFalse(os.path.islink(skill))  # the link into Paperclip's home is replaced by its contents
        with open(os.path.join(skill, "SKILL.md")) as f:
            self.assertEqual(f.read(), "house rules\n")

    def test_the_agent_group_can_read_but_not_write(self):
        out = self.staged()
        self.assertEqual(stat.S_IMODE(os.stat(self.parent).st_mode), 0o2750)
        run_dir = os.path.dirname(out[out.index("--add-dir") + 1])
        for d, dirs, files in os.walk(run_dir):
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o750, d)
            self.assertEqual(os.stat(d).st_gid, os.getegid())
            for f in files:
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, f)).st_mode), 0o640, f)

    def test_the_parent_is_given_the_agent_group(self):
        other = [g for g in os.getgroups() if g != os.getegid()]
        if not other:
            self.skipTest("needs a secondary group")
        os.makedirs(self.parent)
        out = agent_stage.stage(self.args, parent=self.parent, group=grp.getgrgid(other[0]).gr_name)
        self.assertEqual(os.stat(self.parent).st_gid, other[0])
        for d, dirs, files in os.walk(os.path.dirname(out[out.index("--add-dir") + 1])):
            self.assertEqual(os.stat(d).st_gid, other[0], d)
            for f in files:
                self.assertEqual(os.stat(os.path.join(d, f)).st_gid, other[0], f)

    def test_each_run_gets_its_own_folder(self):
        a, b = self.staged(), self.staged()
        self.assertNotEqual(os.path.dirname(a[a.index("--add-dir") + 1]), os.path.dirname(b[b.index("--add-dir") + 1]))

    def test_a_dangling_skill_link_does_not_stop_the_run(self):
        os.symlink(os.path.join(self.home, "gone"), os.path.join(self.bundle, ".claude", "skills", "gone"))
        out = self.staged()
        self.assertIn("--add-dir", out)

    def test_a_missing_file_stops_the_run(self):
        os.remove(self.instructions)
        with self.assertRaises(StageError):
            self.staged()

    def test_a_parent_the_runner_does_not_own_or_that_is_a_link_is_refused(self):
        os.makedirs(self.parent)
        with mock.patch.object(agent_stage.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(StageError):
                self.staged()
        os.rmdir(self.parent)
        elsewhere = os.path.join(self.tmp, "elsewhere")
        os.makedirs(elsewhere)
        os.symlink(elsewhere, self.parent)
        with self.assertRaises(StageError):
            self.staged()
        self.assertEqual(os.listdir(elsewhere), [])

    def test_run_folders_older_than_a_day_are_removed(self):
        out = self.staged()
        old = os.path.dirname(out[out.index("--add-dir") + 1])
        t = os.path.getmtime(old)
        os.utime(old, (t - 2 * 86400, t - 2 * 86400))
        new = self.staged()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(os.path.dirname(new[new.index("--add-dir") + 1])))


class AgentExecStaging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        shutil.copy(os.path.join(ROOT, "bin", "agent-exec"), os.path.join(self.tmp, "agent-exec"))
        os.symlink(os.path.join(ROOT, "bin", "agent-stage"), os.path.join(self.tmp, "agent-stage"))
        self.instructions = os.path.join(self.tmp, "agent-instructions.md")
        with open(self.instructions, "w") as f:
            f.write("x\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def exec_(self, instructions):
        env = {**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1", "STUDIO_AGENTS_APP_CONFIG": "/nonexistent",
               "STUDIO_AGENT_STAGE_DIR": os.path.join(self.tmp, "runs"), "STUDIO_AGENT_GROUP": MY_GROUP}
        return subprocess.run([os.path.join(self.tmp, "agent-exec"), "--print", "-", "--append-system-prompt-file",
                               instructions, "--settings", "/srv/studio/claude/liaison.json"],
                              capture_output=True, text=True, env=env)

    def test_the_cli_is_given_the_staged_copy(self):
        r = self.exec_(self.instructions)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(self.instructions + " ", r.stdout)
        self.assertIn(f"--append-system-prompt-file {os.path.join(self.tmp, 'runs')}/run-", r.stdout)
        self.assertIn(" --settings /srv/studio/claude/liaison.json", r.stdout)

    def test_if_staging_fails_the_run_does_not_start(self):
        r = self.exec_(os.path.join(self.tmp, "missing.md"))
        self.assertEqual((r.returncode, r.stdout), (3, ""))
        self.assertIn("could not stage", r.stderr)


if __name__ == "__main__":
    unittest.main()
