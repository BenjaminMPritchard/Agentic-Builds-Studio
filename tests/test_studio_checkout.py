"""agent-bin/studio-checkout: agents start work from a GitHub clone, never from a local copy."""
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "agent-bin", "studio-checkout")
URL = "https://github.com/BenjaminMPritchard/Agentic-Builds-Studio.git"


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class Checkout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # A local bare repository stands in for GitHub: git rewrites the https URL to it, while the clone's
        # recorded origin stays the GitHub URL.
        github = os.path.join(self.tmp, "github")
        self.upstream = os.path.join(github, "BenjaminMPritchard", "Agentic-Builds-Studio.git")
        seed = os.path.join(self.tmp, "seed")
        os.makedirs(seed)
        git("init", "-q", "-b", "main", cwd=seed)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "one", cwd=seed)
        git("clone", "-q", "--bare", seed, self.upstream)
        self.seed = seed
        self.work = os.path.join(self.tmp, "work")
        os.makedirs(self.work)
        self.env = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": f"url.file://{github}/.insteadOf",
                    "GIT_CONFIG_VALUE_0": "https://github.com/", "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1"}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_(self, *args, env=None):
        return subprocess.run([HELPER, *args], cwd=self.work, capture_output=True, text=True, env=env or self.env)

    def test_clones_from_github_into_the_working_directory(self):
        r = self.run_("BenjaminMPritchard/Agentic-Builds-Studio")
        self.assertEqual(r.returncode, 0, r.stderr)
        clone = os.path.join(self.work, "Agentic-Builds-Studio")
        self.assertEqual(r.stdout.splitlines()[0], clone)
        self.assertIn("branch: main; ahead of origin/main: 0; behind: 0; uncommitted files: 0", r.stdout)
        self.assertEqual(git("config", "--get", "remote.origin.url", cwd=clone), URL)

    def test_a_second_run_fetches_and_keeps_local_work(self):
        self.run_("BenjaminMPritchard/Agentic-Builds-Studio")
        clone = os.path.join(self.work, "Agentic-Builds-Studio")
        git("switch", "-q", "-c", "agent/AGE-9-x", cwd=clone)
        with open(os.path.join(clone, "note.md"), "w") as f:
            f.write("draft\n")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "two", cwd=self.seed)
        git("push", "-q", self.upstream, "main", cwd=self.seed)
        r = self.run_("BenjaminMPritchard/Agentic-Builds-Studio")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("branch: agent/AGE-9-x; ahead of origin/main: 0; behind: 1; uncommitted files: 1", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(clone, "note.md")))

    def test_a_folder_that_is_not_the_github_clone_is_refused(self):
        local = os.path.join(self.work, "Agentic-Builds-Studio")
        git("clone", "-q", self.seed, local)  # like the Recorder's clone of /srv/studio/company-tmp
        r = self.run_("BenjaminMPritchard/Agentic-Builds-Studio")
        self.assertEqual((r.returncode, r.stdout), (3, ""))
        self.assertIn("move it aside", r.stderr)
        git("remote", "set-url", "origin", "https://x-access-token:secret@github.com/BenjaminMPritchard/"
            "Agentic-Builds-Studio.git", cwd=local)
        self.assertEqual(self.run_("BenjaminMPritchard/Agentic-Builds-Studio").returncode, 3)

    def test_bad_arguments_are_refused(self):
        for args in ((), ("no-slash",), ("../x/y",), ("a/..",), ("-c/x",), ("a/b", "--write"), ("a/b", "--read", "x")):
            self.assertEqual(self.run_(*args).returncode, 2, args)
        self.assertEqual(os.listdir(self.work), [])

    def test_read_mode_needs_the_site_read_token(self):
        env = {k: v for k, v in self.env.items() if k != "GH_TOKEN_SITE_READ"}
        self.assertEqual(self.run_("o/site", "--read", env=env).returncode, 4)


class ReadCredential(unittest.TestCase):
    """--read replaces the run's App credential helper with one that answers with GH_TOKEN_SITE_READ."""

    def test_site_read_token_answers_instead_of_the_app_helper(self):
        tmp = tempfile.mkdtemp()
        try:
            log = os.path.join(tmp, "args")
            fake = os.path.join(tmp, "git")
            with open(fake, "w") as f:
                f.write('#!/usr/bin/env bash\nprintf "%s\\0" "$@" > "$STUDIO_TEST_LOG"\nexit 1\n')
            os.chmod(fake, 0o755)
            env = {**os.environ, "PATH": f"{tmp}:{os.environ['PATH']}", "STUDIO_TEST_LOG": log,
                   "GH_TOKEN_SITE_READ": "github_pat_read", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1",
                   # as agent-exec sets it for the run
                   "GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "credential.https://github.com.helper",
                   "GIT_CONFIG_VALUE_0": "", "GIT_CONFIG_KEY_1": "credential.https://github.com.helper",
                   "GIT_CONFIG_VALUE_1": "!printf 'username=x-access-token\\npassword=ghs_app_token\\n'; :"}
            subprocess.run([HELPER, "Agentic-Builds-Studio-Client-Pages/site", "--read"], cwd=tmp, env=env,
                           capture_output=True)
            with open(log) as f:
                args = f.read().split("\0")[:-1]
            self.assertEqual(args[-4:-1], ["clone", "--quiet", "https://github.com/Agentic-Builds-Studio-Client-Pages/site.git"])
            self.assertNotIn("github_pat_read", " ".join(args))  # the token itself is never on a command line
            pre = args[:-4]
            env["PATH"] = os.environ["PATH"]
            r = subprocess.run(["git", *pre, "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                               capture_output=True, text=True, env=env)
            self.assertIn("password=github_pat_read\n", r.stdout, r.stderr)
            self.assertNotIn("ghs_app_token", r.stdout)
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
