"""Long agent runs keep GitHub access: run grants, token renewal, the gh wrapper and the git credential helper."""
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from lib import agent_grant
from lib.agent_grant import GrantError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRANT = "0123456789abcdef0123456789abcdef"


def load(name):
    path = os.path.join(ROOT, "bin", name)
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def script(path, body):
    with open(path, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    os.chmod(path, 0o755)
    return path


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.t = 1_000_000.0

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def now(self):
        return self.t


class Grants(Tmp):
    def test_grant_names_the_account_until_it_expires(self):
        d = os.path.join(self.tmp, "g")
        gid = agent_grant.create("BenjaminMPritchard", d, hours=8, now=self.now)
        self.assertRegex(gid, r"^[0-9a-f]{32}$")
        self.assertEqual(agent_grant.resolve(gid, d, now=self.now), "BenjaminMPritchard")
        self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, gid + ".json")).st_mode), 0o600)
        self.t += 8 * 3600
        with self.assertRaises(GrantError):
            agent_grant.resolve(gid, d, now=self.now)

    def test_expired_and_malformed_grants_are_pruned_when_a_run_starts(self):
        d = os.path.join(self.tmp, "g")
        old = agent_grant.create("a", d, hours=1, now=self.now)
        with open(os.path.join(d, "junk.json"), "w") as f:
            f.write("not json")
        self.t += 2 * 3600
        new = agent_grant.create("b", d, now=self.now)
        self.assertEqual(sorted(os.listdir(d)), [new + ".json"])
        with self.assertRaises(GrantError):
            agent_grant.resolve(old, d, now=self.now)

    def test_ids_and_owners_are_validated(self):
        d = os.path.join(self.tmp, "g")
        for bad in ("../../etc/passwd", GRANT.upper(), GRANT[:-1], "", None):
            with self.assertRaises(GrantError):
                agent_grant.resolve(bad, d, now=self.now)
        with self.assertRaises(GrantError):
            agent_grant.resolve(GRANT, d, now=self.now)  # well-formed but unknown
        agent_grant.create("x", d, now=self.now)  # a real grant file, then copies that only a loose ID check would reach
        with open(os.path.join(self.tmp, "outside.json"), "w") as f:
            json.dump({"owner": "attacker", "expires": self.t + 3600}, f)
        with open(os.path.join(d, GRANT.upper() + ".json"), "w") as f:
            json.dump({"owner": "attacker", "expires": self.t + 3600}, f)
        for bad in ("../outside", GRANT.upper()):
            with self.assertRaises(GrantError):
                agent_grant.resolve(bad, d, now=self.now)
        for bad in ("owner/repo", "-x", "", "a b"):
            with self.assertRaises(GrantError):
                agent_grant.create(bad, d, now=self.now)


class TokenCommand(Tmp):
    """bin/agent-github-token, which runs as paperclip."""

    def setUp(self):
        super().setUp()
        self.mod = load("agent-github-token")
        self.config = os.path.join(self.tmp, "agents-app.json")
        with open(self.config, "w") as f:
            json.dump({"app_id": 5110225, "key_path": "/etc/studio/agents-app.pem"}, f)
        self.grants = os.path.join(self.tmp, "g")
        self.minted = []

    def main(self, *args):
        def mint(owner, app_id, key_path):
            self.minted.append(owner)
            return "ghs_" + owner
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = self.mod.main(["agent-github-token", *args], mint=mint, grant_dir=self.grants, config=self.config)
        return code, out.getvalue().strip(), err.getvalue()

    def test_a_grant_yields_a_token_for_its_own_account_only(self):
        code, gid, _ = self.main("--new-grant", "BenjaminMPritchard")
        self.assertEqual(code, 0)
        self.assertEqual(self.main("--grant", gid)[:2], (0, "ghs_BenjaminMPritchard"))
        self.assertEqual(self.minted, ["BenjaminMPritchard"])

    def test_extra_or_malformed_arguments_are_refused_before_any_token_is_made(self):
        _, gid, _ = self.main("--new-grant", "BenjaminMPritchard")
        for args in (("--grant", gid, "Agentic-Builds-Studio-Client-Pages"), ("--grant",), ("--grant", "../x"),
                     ("--grant", GRANT), ("-x",), ()):
            self.assertEqual(self.main(*args)[0], 1, args)
        self.assertEqual(self.minted, [])


class Renewal(Tmp):
    """bin/agent-gh-token, which runs as studio-agent inside the run."""

    def setUp(self):
        super().setUp()
        self.mod = load("agent-gh-token")
        self.cache = os.path.join(self.tmp, "cache")
        self.calls = []
        self.renew_result = subprocess.CompletedProcess([], 0, "ghs_renewed\n", "")

    def run_(self, cmd, **kw):
        self.calls.append(cmd)
        return self.renew_result

    def main(self, issued_ago=None, grant=GRANT, token="ghs_initial"):
        env = {"STUDIO_AGENT_GITHUB_GRANT": grant, "STUDIO_AGENT_TOKEN_CACHE": self.cache}
        if token:
            env["GH_TOKEN"] = token
        if issued_ago is not None:
            env["STUDIO_AGENT_TOKEN_ISSUED_AT"] = str(self.t - issued_ago)
        out = io.StringIO()
        old = os.environ.get("STUDIO_AGENT_TOKEN_CACHE")
        os.environ["STUDIO_AGENT_TOKEN_CACHE"] = self.cache
        try:
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                code = self.mod.main(env=env, now=self.now, run=self.run_)
        finally:
            os.environ.pop("STUDIO_AGENT_TOKEN_CACHE") if old is None else os.environ.__setitem__("STUDIO_AGENT_TOKEN_CACHE", old)
        return code, out.getvalue().strip()

    def test_the_starting_token_is_used_while_fresh(self):
        self.assertEqual(self.main(issued_ago=44 * 60), (0, "ghs_initial"))
        self.assertEqual(self.calls, [])

    def test_an_old_token_is_renewed_through_the_grant_and_cached(self):
        self.assertEqual(self.main(issued_ago=46 * 60), (0, "ghs_renewed"))
        self.assertEqual(self.calls, [["/usr/bin/sudo", "-n", "-u", "paperclip", "--",
                                       "/srv/studio/bin/agent-github-token", "--grant", GRANT]])
        path = os.path.join(self.cache, GRANT + ".json")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(self.cache).st_mode), 0o700)
        self.t += 30 * 60
        self.assertEqual(self.main(issued_ago=76 * 60), (0, "ghs_renewed"))  # from the cache
        self.assertEqual(len(self.calls), 1)
        self.t += 16 * 60
        self.renew_result = subprocess.CompletedProcess([], 0, "ghs_second\n", "")
        self.assertEqual(self.main(issued_ago=92 * 60), (0, "ghs_second"))
        self.assertEqual(len(self.calls), 2)

    def test_missing_issue_time_counts_as_old(self):
        self.assertEqual(self.main(issued_ago=None), (0, "ghs_renewed"))

    def test_an_issue_time_in_the_future_counts_as_old(self):
        self.assertEqual(self.main(issued_ago=-3600), (0, "ghs_renewed"))

    def test_a_refused_renewal_fails_and_caches_nothing(self):
        self.renew_result = subprocess.CompletedProcess([], 1, "", "grant has expired")
        self.assertEqual(self.main(issued_ago=61 * 60), (1, ""))
        self.renew_result = subprocess.CompletedProcess([], 1, "usage: ...\n", "")
        self.assertEqual(self.main(issued_ago=61 * 60), (1, ""))
        self.assertFalse(os.path.exists(os.path.join(self.cache, GRANT + ".json")))

    def test_no_or_malformed_grant_fails_without_asking(self):
        for grant in ("", "../x", "a b"):
            self.assertEqual(self.main(issued_ago=0, grant=grant)[0], 1, grant)
        self.assertEqual(self.calls, [])


class Wrappers(Tmp):
    """agent-bin/gh and bin/agent-git-credential, run as real processes with a fake gh and a fake renewal."""

    def setUp(self):
        super().setUp()
        self.fake_gh = script(os.path.join(self.tmp, "gh"), 'echo "token=${GH_TOKEN:-none} args=$*"')
        self.renew = script(os.path.join(self.tmp, "renew"), '[ "$1" = %s ] && echo ghs_renewed' % GRANT)
        self.env = {**os.environ, "STUDIO_REAL_GH": self.fake_gh, "STUDIO_AGENT_TOKEN_RENEW": self.renew,
                    "STUDIO_AGENT_TOKEN_CACHE": os.path.join(self.tmp, "cache"), "GH_TOKEN": "ghs_initial",
                    "STUDIO_AGENT_GITHUB_GRANT": GRANT, "STUDIO_AGENT_TOKEN_ISSUED_AT": "0"}

    def run_(self, cmd, env, stdin=""):
        return subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env)

    def test_gh_gets_a_renewed_token_in_a_long_run(self):
        r = self.run_([os.path.join(ROOT, "agent-bin", "gh"), "pr", "create"], self.env)
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "token=ghs_renewed args=pr create"), r.stderr)

    def test_gh_without_a_grant_passes_through(self):
        env = {k: v for k, v in self.env.items() if k != "STUDIO_AGENT_GITHUB_GRANT"}
        r = self.run_([os.path.join(ROOT, "agent-bin", "gh"), "auth", "status"], env)
        self.assertEqual(r.stdout.strip(), "token=ghs_initial args=auth status")

    def test_an_explicit_site_read_token_is_used_as_given(self):
        env = {**self.env, "GH_TOKEN_SITE_READ": "github_pat_read", "GH_TOKEN": "github_pat_read"}
        r = self.run_([os.path.join(ROOT, "agent-bin", "gh"), "api", "repos/o/site"], env)
        self.assertEqual(r.stdout.strip(), "token=github_pat_read args=api repos/o/site")
        env["GH_TOKEN"] = "something-else"  # any other token is still replaced by the App token
        r = self.run_([os.path.join(ROOT, "agent-bin", "gh"), "pr", "list"], env)
        self.assertEqual(r.stdout.strip(), "token=ghs_renewed args=pr list")

    def test_gh_stops_when_no_token_can_be_had(self):
        env = {**self.env, "STUDIO_AGENT_TOKEN_RENEW": script(os.path.join(self.tmp, "no"), "exit 1")}
        r = self.run_([os.path.join(ROOT, "agent-bin", "gh"), "pr", "list"], env)
        self.assertEqual(r.returncode, 4)
        self.assertNotIn("token=", r.stdout)

    def test_git_credential_helper_answers_get_only(self):
        helper = os.path.join(ROOT, "bin", "agent-git-credential")
        r = self.run_([helper, "get"], self.env, "protocol=https\nhost=github.com\n\n")
        self.assertEqual((r.returncode, r.stdout), (0, "username=x-access-token\npassword=ghs_renewed\n"), r.stderr)
        for op in ("store", "erase"):
            r = self.run_([helper, op], self.env, "protocol=https\nhost=github.com\npassword=x\n\n")
            self.assertEqual((r.returncode, r.stdout), (0, ""))


class AgentExecWiring(Tmp):
    def setUp(self):
        super().setUp()
        shutil.copy(os.path.join(ROOT, "bin", "agent-exec"), os.path.join(self.tmp, "agent-exec"))
        os.symlink(os.path.join(ROOT, "bin", "agent-stage"), os.path.join(self.tmp, "agent-stage"))
        self.config = os.path.join(self.tmp, "agents-app.json")
        with open(self.config, "w") as f:
            json.dump({"app_id": 7, "key_path": "/nonexistent"}, f)

    def exec_(self, token_body):
        script(os.path.join(self.tmp, "agent-github-token"), token_body)
        env = {**os.environ, "STUDIO_AGENT_EXEC_DRY_RUN": "1", "STUDIO_AGENTS_APP_CONFIG": self.config,
               "PATH": "/usr/bin:/bin"}
        return subprocess.run([os.path.join(self.tmp, "agent-exec"), "--settings", "/srv/studio/claude/liaison.json"],
                              capture_output=True, text=True, env=env)

    def test_the_run_gets_a_grant_the_gh_wrapper_and_the_credential_helper(self):
        r = self.exec_('[ "$1" = --new-grant ] && [ "$2" = Agentic-Builds-Studio-Client-Pages ] && { echo %s; exit 0; }\n'
                       'echo ghs_start' % GRANT)
        self.assertEqual(r.returncode, 0, r.stderr)
        agent_bin = os.path.realpath(os.path.join(self.tmp, "..", "agent-bin"))
        self.assertTrue(r.stdout.startswith(
            f"sudo -n -E -H -u studio-agent PATH={agent_bin}:/usr/bin:/bin /usr/bin/setpriv --pdeathsig KILL -- "),
            r.stdout)
        # sudo reads VAR=value only before `--`; after it, PATH=... is the command and no rule matches.
        sudo_args = r.stdout.split()[:r.stdout.split().index("/usr/bin/setpriv")]
        self.assertNotIn("--", sudo_args)
        self.assertIn(f"GRANT={GRANT}\n", r.stdout)
        self.assertIn(f"CREDENTIAL=!{os.path.realpath(self.tmp)}/agent-git-credential\n", r.stdout)

    def test_no_grant_means_the_run_does_not_start(self):
        r = self.exec_('[ "$1" = --new-grant ] && exit 1\necho ghs_start')
        self.assertEqual((r.returncode, r.stdout), (3, ""))
        self.assertIn("no GitHub grant", r.stderr)


class SudoRule(unittest.TestCase):
    def test_agents_may_renew_only_through_a_grant(self):
        rules = open(os.path.join(ROOT, "deploy", "studio-agent", "sudoers")).read()
        self.assertIn("studio-agent ALL=(paperclip) NOPASSWD: /srv/studio/bin/agent-github-token --grant *\n", rules)
        self.assertEqual(rules.count("agent-github-token"), 1)
        renew = load("agent-gh-token").RENEW
        self.assertEqual(renew[-2:], ["/srv/studio/bin/agent-github-token", "--grant"])


if __name__ == "__main__":
    unittest.main()
