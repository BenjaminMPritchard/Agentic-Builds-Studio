import importlib.machinery, importlib.util, io, os, unittest
from contextlib import redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load():
    loader = importlib.machinery.SourceFileLoader("merge_gate_cli", os.path.join(ROOT, "bin", "merge-gate"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("merge_gate_cli", loader))
    loader.exec_module(mod)
    return mod


class ConfinedHop(unittest.TestCase):
    ARGS = ["merge-gate", "merge", "--issue", "i", "--repo", "o/r", "--pr", "1", "--head", "a" * 40]

    def test_confined_agent_is_re_run_as_paperclip_through_sudo(self):
        mg, out = load(), io.StringIO()
        with mock.patch.object(mg.pwd, "getpwuid", return_value=mock.Mock(pw_name="studio-agent")), \
                mock.patch.dict(os.environ, {"STUDIO_MERGE_GATE_DRY_HOP": "1"}), redirect_stdout(out):
            self.assertEqual(mg.main(self.ARGS), 0)
        self.assertEqual(out.getvalue().split(), ["sudo", "-n", "-H", "-u", "paperclip", "--", "/srv/studio/bin/merge-gate",
                                                  *self.ARGS[1:]])

    def test_hop_matches_the_sudoers_rule(self):
        rule = open(os.path.join(ROOT, "deploy", "studio-agent", "sudoers")).read()
        self.assertIn("studio-agent ALL=(paperclip) NOPASSWD: /srv/studio/bin/merge-gate check *, "
                      "/srv/studio/bin/merge-gate merge *", rule)

    def test_other_users_do_not_hop(self):
        mg = load()
        with mock.patch.object(mg.pwd, "getpwuid", return_value=mock.Mock(pw_name="paperclip")), \
                mock.patch.object(mg, "hop") as hop, mock.patch.object(mg.merge_gate, "run", return_value=(False, ["x"], False)), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(mg.main(self.ARGS), 1)
        hop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
