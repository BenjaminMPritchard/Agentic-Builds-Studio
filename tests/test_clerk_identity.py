"""bin/clerk acts as its Paperclip service user when its key file exists, and only then."""
import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_clerk(key_file):
    with mock.patch.dict(os.environ, {"STUDIO_CLERK_KEY_FILE": key_file}):
        loader = importlib.machinery.SourceFileLoader("clerk_cli", os.path.join(ROOT, "bin", "clerk"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod


class ClerkIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.key = os.path.join(self.tmp, "board-key")
        self.env = mock.patch.dict(os.environ, {"PAPERCLIP_API_KEY": "run-jwt", "PAPERCLIP_RUN_ID": "run-1"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        for f in os.listdir(self.tmp):
            os.remove(os.path.join(self.tmp, f))
        os.rmdir(self.tmp)

    def test_with_its_key_the_clerk_is_the_service_user_not_a_run(self):
        fd = os.open(self.key, os.O_WRONLY | os.O_CREAT, 0o600)
        os.write(fd, b"pcp_board_clerk\n")
        os.close(fd)
        pc = load_clerk(self.key).client()
        self.assertEqual((pc.key, pc.run_id), ("pcp_board_clerk", ""))

    def test_a_key_others_can_read_is_refused(self):
        with open(self.key, "w") as f:
            f.write("pcp_board_clerk\n")
        os.chmod(self.key, 0o644)
        with self.assertRaises(PermissionError):
            load_clerk(self.key).client()

    def test_without_its_key_the_clerk_is_the_agent_run(self):
        pc = load_clerk(self.key).client()
        self.assertEqual((pc.key, pc.run_id), ("run-jwt", "run-1"))


if __name__ == "__main__":
    unittest.main()
