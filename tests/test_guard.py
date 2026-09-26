import json, os, subprocess, tempfile, unittest, threading, http.server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARD = os.path.join(ROOT, "bin", "guard")


def git(cwd, *a):
    subprocess.run(["git", "-C", cwd, *a], check=True, capture_output=True)


def run(tool, inp, cwd, env=None):
    e = {**os.environ, **(env or {})}
    for k in ("STUDIO_ALLOWED_PATHS",):
        e.setdefault(k, "")
    r = subprocess.run([GUARD], input=json.dumps({"tool_name": tool, "tool_input": inp, "cwd": cwd}),
                       capture_output=True, text=True, env=e)
    return r.returncode


class Guard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        d = cls.repo = cls.tmp.name
        git(d, "init", "-q", "-b", "main")
        git(d, "config", "user.email", "t@t"); git(d, "config", "user.name", "t")
        open(os.path.join(d, "a.txt"), "w").write("x")
        git(d, "add", "."); git(d, "commit", "-qm", "init")
        cls.work = os.path.join(d, "wt")
        git(d, "worktree", "add", "-q", "-b", "agent/1-x", cls.work)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bash(self, cmd, cwd=None, env=None):
        return run("Bash", {"command": cmd}, cwd or self.work, env)

    def test_force_and_main_push(self):
        for c in ["git push --force origin agent/1-x", "git push -f", "git push origin +agent/1-x",
                  "git push --force-with-lease", "git push origin main", "git push origin HEAD:main",
                  "git push origin HEAD:refs/heads/master", "cd x && git push -f"]:
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.bash("git push -u origin agent/1-x"), 0)
        self.assertEqual(self.bash("git push origin agent/1-main-fix"), 0)

    def test_push_bare_from_main(self):
        self.assertEqual(self.bash("git push", cwd=self.repo), 2)

    def fake_gh(self, pr):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "gh")
        open(path, "w").write("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(pr) + "\nEOF\n")
        os.chmod(path, 0o755)
        return {"PATH": d + ":" + os.environ["PATH"], "STUDIO_DIRECTOR_ID": "dir", "PAPERCLIP_AGENT_ID": "dir"}

    def test_director_merge_rules(self):
        ok = {"state": "OPEN", "isDraft": False, "headRefName": "agent/AGE-4-x", "labels": [], "reviewDecision": "APPROVED",
              "statusCheckRollup": [{"conclusion": "SUCCESS"}], "files": [{"path": "app/a.py"}],
              "url": "https://github.com/o/mothers/pull/3"}
        env = self.fake_gh(ok)
        m = "gh pr merge 3 --squash --repo o/mothers"
        self.assertEqual(self.bash(m, env=env), 0)
        self.assertEqual(self.bash(m, env={**env, "PAPERCLIP_AGENT_ID": "someone"}), 2)      # not the Director
        self.assertEqual(self.bash(m + " --admin", env=env), 2)
        self.assertEqual(self.bash("gh pr merge 3 --repo o/studio-company", env=env), 2)
        for change in ({"isDraft": True}, {"headRefName": "feature/x"}, {"labels": [{"name": "needs-human"}]},
                       {"statusCheckRollup": [{"conclusion": "FAILURE"}]}, {"statusCheckRollup": []},
                       {"files": [{"path": "CLAUDE.md"}]}, {"reviewDecision": "CHANGES_REQUESTED"}):
            self.assertEqual(self.bash(m, env=self.fake_gh({**ok, **change})), 2, change)

    def test_merge_and_e2e(self):
        self.assertEqual(self.bash("gh pr merge 3 --squash"), 2)
        self.assertEqual(self.bash("make e2e"), 2)
        self.assertEqual(self.bash("/srv/studio/bin/studio-e2e"), 0)

    def test_live_keys(self):
        self.assertEqual(self.bash("echo sk_live_abc123"), 2)
        self.assertEqual(run("Write", {"file_path": "b.txt", "content": "K=rk_live_zzz"}, self.work), 2)
        self.assertEqual(self.bash("echo sk_test_abc123"), 0)

    def test_commit_on_main(self):
        self.assertEqual(self.bash("git commit -m x", cwd=self.repo), 2)
        self.assertEqual(self.bash("git commit -m x"), 0)
        self.assertEqual(run("Edit", {"file_path": "a.txt", "new_string": "y"}, self.repo), 2)
        self.assertEqual(run("Edit", {"file_path": "a.txt", "new_string": "y"}, self.work), 0)

    def test_protected_paths(self):
        for p in ["CLAUDE.md", ".claude/settings.json", "docs/PLAN.md", ".studio/project.yaml", "CONSTITUTION.md"]:
            self.assertEqual(run("Edit", {"file_path": p, "new_string": "y"}, self.work), 2, p)
        self.assertEqual(run("Edit", {"file_path": "CLAUDE.md", "new_string": "y"}, self.work,
                             {"STUDIO_ALLOWED_PATHS": "CLAUDE.md"}), 0)
        self.assertEqual(run("Edit", {"file_path": "CONSTITUTION.md", "new_string": "y"}, self.work,
                             {"STUDIO_ALLOWED_PATHS": "CONSTITUTION.md"}), 2)
        self.assertEqual(run("Edit", {"file_path": ".studio-allowed-paths", "new_string": "CLAUDE.md"}, self.work), 2)
        self.assertEqual(self.bash("echo hi >> CLAUDE.md"), 2)
        self.assertEqual(self.bash("cat CLAUDE.md"), 0)

    def test_reads_and_mentions_of_protected_files_are_fine(self):
        for c in ["cat CONSTITUTION.md 2>/dev/null | head -150; echo done", "grep -n house CLAUDE.md", "head -5 docs/PLAN.md",
                  "cp CLAUDE.md /tmp/copy.md", "diff CLAUDE.md /tmp/x > /tmp/out.txt",
                  "cat > /tmp/body.json <<'JSON'\n{\"body\": \"I could not edit CONSTITUTION.md; rm CLAUDE.md is blocked\"}\nJSON"]:
            self.assertEqual(self.bash(c), 0, c)

    def test_real_writes_to_protected_files_are_blocked(self):
        for c in ["echo x > CLAUDE.md", "echo x >>CONSTITUTION.md", "cp /tmp/x CLAUDE.md", "mv /tmp/x docs/PLAN.md",
                  "rm CLAUDE.md", "printf x | tee .claude/settings.json", "sed -i s/a/b/ CLAUDE.md",
                  "git checkout main -- CLAUDE.md", "FOO=1 rm -f .studio/project.yaml", "cd x && rm CONSTITUTION.md"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_allowed_paths_file(self):
        open(os.path.join(self.work, ".studio-allowed-paths"), "w").write("docs/PLAN.md\n")
        try:
            self.assertEqual(run("Edit", {"file_path": "docs/PLAN.md", "new_string": "y"}, self.work), 0)
        finally:
            os.remove(os.path.join(self.work, ".studio-allowed-paths"))

    def test_paperclip_admin_dns_drop(self):
        self.assertEqual(self.bash("paperclipai company import ./package"), 2)
        self.assertEqual(self.bash("paperclipai agent list"), 0)
        self.assertEqual(self.bash("aws route53 change-resource-record-sets"), 2)
        self.assertEqual(self.bash("dropdb mothers_carpentry"), 2)
        self.assertEqual(self.bash("dropdb mc_task1_e2e"), 0)
        self.assertEqual(self.bash("psql -c 'DROP DATABASE test_mc_x'"), 0)
        self.assertEqual(self.bash("psql -c 'DROP DATABASE prod'"), 2)

    def test_email_send_requires_accepted_confirmation(self):
        status = {"v": "pending"}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                body = json.dumps({"interactions": [{"kind": "request_confirmation", "status": status["v"]}]}).encode()
                s.send_response(200); s.end_headers(); s.wfile.write(body)
            def log_message(*a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        env = {"PAPERCLIP_API_URL": f"http://127.0.0.1:{srv.server_port}", "PAPERCLIP_TASK_ID": "t1", "PAPERCLIP_API_KEY": "k"}
        try:
            self.assertEqual(self.bash("paperclipai email send --to a@b.c", env=env), 2)
            self.assertEqual(run("mcp__agentmail__send_message", {}, self.work, env), 2)
            status["v"] = "accepted"
            self.assertEqual(self.bash("paperclipai email send --to a@b.c", env=env), 0)
            self.assertEqual(run("mcp__agentmail__send_message", {}, self.work, env), 0)
        finally:
            srv.shutdown()
        self.assertEqual(self.bash("paperclipai email send --to a@b.c", env={"PAPERCLIP_API_URL": ""}), 2)

    def test_bad_input_is_no_decision(self):
        r = subprocess.run([GUARD], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
