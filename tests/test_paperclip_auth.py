"""Paperclip authenticated mode: human tools use a Board key file; the merge gate keeps only the agent's key."""
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from lib import paperclip, stop
from lib.paperclip import ApiError, Paperclip

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), os.path.join(ROOT, "bin", name))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class KeyFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "paperclip-board-key")
        self.env = mock.patch.dict(os.environ, {"STUDIO_BOARD_KEY_FILE": self.path})
        self.env.start()
        os.environ.pop("PAPERCLIP_API_KEY", None)

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def write(self, mode, text="pcp_board_key\n"):
        with open(self.path, "w") as f:
            f.write(text)
        os.chmod(self.path, mode)

    def test_no_file_means_no_key(self):
        self.assertEqual(paperclip.board_key(), "")
        self.assertEqual(Paperclip().key, "")

    def test_a_private_file_supplies_the_board_key(self):
        self.write(0o600)
        self.assertEqual(paperclip.board_key(), "pcp_board_key")
        self.assertEqual(Paperclip().key, "pcp_board_key")

    def test_a_file_others_can_read_is_refused(self):
        for mode in (0o640, 0o604, 0o644):
            self.write(mode)
            with self.assertRaises(PermissionError):
                paperclip.board_key()

    def test_a_file_belonging_to_someone_else_is_refused(self):
        self.write(0o600)
        with mock.patch.object(paperclip.os, "geteuid", return_value=os.geteuid() + 1):
            with self.assertRaises(PermissionError):
                paperclip.board_key()

    def test_an_agent_runs_own_key_always_wins(self):
        self.write(0o600)
        with mock.patch.dict(os.environ, {"PAPERCLIP_API_KEY": "agent_run_jwt"}):
            self.assertEqual(Paperclip().key, "agent_run_jwt")
        self.assertEqual(Paperclip(key="explicit").key, "explicit")


class StudioStop(unittest.TestCase):
    def setUp(self):
        self.mod = load("studio-stop")
        self.tmp = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"STUDIO_BOARD_KEY_FILE": os.path.join(self.tmp, "key"),
                                                "STUDIO_DATA": self.tmp})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp)

    def run_(self):
        err = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            code = self.mod.main(["studio-stop", "status"])
        return code, err.getvalue()

    def test_refused_board_access_explains_the_key_file(self):
        with mock.patch.object(stop, "status", side_effect=ApiError(401, "Board authentication required")):
            code, err = self.run_()
        self.assertEqual(code, 2)
        self.assertIn("~/.config/studio/paperclip-board-key", err)

    def test_an_unsafe_key_file_is_reported_not_used(self):
        path = os.path.join(self.tmp, "key")
        with open(path, "w") as f:
            f.write("k")
        os.chmod(path, 0o644)
        with mock.patch.object(stop, "status") as status:
            code, err = self.run_()
        self.assertEqual(code, 2)
        self.assertIn("mode 0600", err)
        status.assert_not_called()

    def test_other_api_errors_are_not_hidden(self):
        with mock.patch.object(stop, "status", side_effect=ApiError(500, "boom")):
            with self.assertRaises(ApiError):
                self.run_()


class GateHop(unittest.TestCase):
    def test_only_the_agents_key_and_run_id_cross_sudo(self):
        rules = open(os.path.join(ROOT, "deploy", "studio-agent", "sudoers")).read()
        keep = re.findall(r"^Defaults!(\S+) env_keep \+= \"([^\"]*)\"$", rules, re.M)
        self.assertEqual(keep, [("/srv/studio/bin/merge-gate", "PAPERCLIP_API_KEY PAPERCLIP_RUN_ID")])
        self.assertNotIn("PAPERCLIP_API_URL", rules.replace("# The API", ""))
        self.assertNotIn("SETENV", rules.split("studio-agent ALL=(paperclip)", 1)[1])

    def test_the_gate_reads_the_local_server_whatever_the_caller_sets(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Paperclip(key="k").base, "http://localhost:3100")


if __name__ == "__main__":
    unittest.main()
