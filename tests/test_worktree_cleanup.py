import os, subprocess, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEANUP = os.path.join(ROOT, "bin", "worktree-cleanup")
LOCAL = "DATABASE_URL=postgres://u:p@127.0.0.1:5432/x\n"


class WorktreeCleanup(unittest.TestCase):
    def run_in(self, name="AGE-3-pallet", db="mc_age_3_pallet", env_file=LOCAL, pattern=None):
        with tempfile.TemporaryDirectory() as tmp:
            wt = os.path.join(tmp, name)
            os.makedirs(wt)
            if db is not None:
                open(os.path.join(wt, ".studio-worktree"), "w").write(f"STUDIO_DB_NAME={db}\n")
            open(os.path.join(wt, ".env"), "w").write(env_file)
            if pattern is not None:
                os.makedirs(os.path.join(wt, ".studio"))
                open(os.path.join(wt, ".studio", "project.yaml"), "w").write(f'isolation:\n  db_name: "{pattern}"\n')
            r = subprocess.run([CLEANUP], cwd=wt, capture_output=True, text=True,
                               env={**os.environ, "STUDIO_SETUP_DRY_RUN": "1"})
            return r.returncode, r.stdout, r.stderr

    def test_drops_only_this_worktrees_databases(self):
        rc, out, _ = self.run_in()
        self.assertEqual(rc, 0)
        self.assertEqual(out.split("\n")[:3], ["would drop mc_age_3_pallet", "would drop test_mc_age_3_pallet",
                                               "would drop mc_age_3_pallet_e2e"])

    def test_custom_per_worktree_pattern(self):
        rc, out, _ = self.run_in(db="site_age_3_pallet", pattern="site_{task}")
        self.assertEqual(rc, 0)
        self.assertIn("would drop site_age_3_pallet", out)

    def test_no_marker_is_a_no_op(self):
        rc, out, _ = self.run_in(db=None)
        self.assertEqual(rc, 0)
        self.assertIn("nothing to drop", out)

    def refused(self, why, **kw):
        rc, out, err = self.run_in(**kw)
        self.assertNotEqual(rc, 0)
        self.assertNotIn("would drop", out)
        self.assertIn(why, err)

    def test_marker_naming_the_shared_database_is_refused(self):
        self.refused("expected 'mc_age_3_pallet'", db="mothers_carpentry")

    def test_marker_naming_another_worktree_is_refused(self):
        self.refused("expected 'mc_age_3_pallet'", db="mc_age_4_other")

    def test_system_database_is_refused(self):
        self.refused("expected", db="postgres")

    def test_shared_pattern_is_refused(self):
        self.refused("shared, not per worktree", db="mothers_carpentry", pattern="mothers_carpentry")

    def test_remote_database_host_is_refused(self):
        self.refused("not loopback", env_file="DATABASE_URL=postgres://u:p@db.example.com:5432/x\n")

    def test_missing_database_url_is_refused(self):
        self.refused("not loopback", env_file="")

    def test_localhost_and_ipv6_loopback_are_accepted(self):
        for url in ("postgres://u:p@localhost:5432/x", "postgres://u:p@[::1]:5432/x", "postgresql://127.0.0.1/x"):
            rc, out, err = self.run_in(env_file=f"DATABASE_URL={url}\n")
            self.assertEqual(rc, 0, (url, err))


if __name__ == "__main__":
    unittest.main()
