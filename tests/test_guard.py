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

    def test_studio_repo_is_not_cloned_from_the_runtime(self):
        for c in ["git clone /srv/studio/company-tmp studio-company", "git clone -q /srv/studio/company x",
                  "cd /srv/studio/work/recorder && git clone file:///srv/studio/company"]:
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.bash("git clone https://github.com/BenjaminMPritchard/Agentic-Builds-Studio.git x"), 0)

    def test_push_bare_from_main(self):
        self.assertEqual(self.bash("git push", cwd=self.repo), 2)

    def fake_gh(self, pr):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "gh")
        open(path, "w").write("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(pr) + "\nEOF\n")
        os.chmod(path, 0o755)
        return {"PATH": d + ":" + os.environ["PATH"], "STUDIO_DIRECTOR_ID": "dir", "PAPERCLIP_AGENT_ID": "dir"}

    def test_director_cannot_merge_without_project_gate(self):
        ok = {"state": "OPEN", "isDraft": False, "headRefName": "agent/AGE-4-x", "labels": [], "reviewDecision": "APPROVED",
              "statusCheckRollup": [{"conclusion": "SUCCESS"}], "files": [{"path": "app/a.py"}],
              "url": "https://github.com/o/mothers/pull/3"}
        env = self.fake_gh(ok)
        m = "gh pr merge 3 --squash --repo o/mothers"
        self.assertEqual(self.bash(m, env=env), 2)
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
        self.assertEqual(run("Write", {"file_path": "new/dir/b.txt", "content": "y"}, self.repo), 2)
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

    def test_codex_apply_patch_gets_the_same_file_checks(self):
        def patch(body):
            return {"command": "*** Begin Patch\n" + body + "\n*** End Patch"}
        ok = patch("*** Update File: src/app.py\n@@\n-a\n+b")
        self.assertEqual(run("apply_patch", ok, self.work), 0)
        for body in ("*** Update File: CONSTITUTION.md\n@@\n-a\n+b",
                     "*** Add File: notes.txt\n+hello\n*** Update File: .claude/settings.json\n@@\n-a\n+b",
                     "*** Update File: src/app.py\n*** Move to: docs/PLAN.md\n@@\n-a\n+b",
                     "*** Add File: k.env\n+KEY=sk_live_abc123"):
            self.assertEqual(run("apply_patch", patch(body), self.work), 2, body)
        self.assertEqual(run("apply_patch", ok, self.repo), 2)  # on main
        self.assertEqual(run("apply_patch", {"command": "rm -rf /"}, self.work), 2)  # not a patch

    def test_sub_agent_tools_are_refused_for_claude_and_codex(self):
        for tool in ("spawn_agent", "Agent", "Task", "wait_agent", "delegate_task"):
            self.assertEqual(run(tool, {"message": "do it"}, self.work), 2, tool)
        self.assertEqual(run("Read", {"file_path": "a.txt"}, self.work), 0)

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

    def test_dropdb_with_flags_checks_the_real_database_name(self):
        for c in ["dropdb --maintenance-db=postgres://u:p@h:5432/postgres --if-exists mc_wt_x",
                  "dropdb -h 127.0.0.1 -U mothers_carpentry --if-exists test_mc_wt_x",
                  "dropdb --if-exists mc_wt_x_e2e && echo ok"]:
            self.assertEqual(self.bash(c), 0, c)
        for c in ["dropdb --maintenance-db=postgres://u:p@h/postgres mothers_carpentry",
                  "dropdb -h 127.0.0.1 -U mothers_carpentry mothers_carpentry",
                  "psql -c 'DROP DATABASE IF EXISTS mothers_carpentry'"]:
            self.assertEqual(self.bash(c), 2, c)

    def test_email_send_requires_accepted_confirmation(self):
        status = {"v": "pending", "revision": "rev-new", "resolver": "owner"}

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(s):
                if s.path.endswith("/documents/email-draft"):
                    response = {"latestRevisionId": "rev-new", "body": "draft"}
                else:
                    response = [{"kind": "request_confirmation", "status": status["v"],
                        "effectiveResolverPolicy": "human_only", "resolvedByUserId": status["resolver"], "resolvedByAgentId": None,
                        "payload": {"target": {"type": "issue_document", "key": "email-draft", "revisionId": status["revision"]}}}]
                body = json.dumps(response).encode()
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
            status["revision"] = "rev-old"
            self.assertEqual(self.bash("paperclipai email send --to a@b.c", env=env), 2)
            status["revision"] = "rev-new"; status["resolver"] = None
            self.assertEqual(self.bash("paperclipai email send --to a@b.c", env=env), 2)
        finally:
            srv.shutdown()
        self.assertEqual(self.bash("paperclipai email send --to a@b.c", env={"PAPERCLIP_API_URL": ""}), 2)

    def test_bad_input_is_no_decision(self):
        r = subprocess.run([GUARD], input="not json", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)

    def test_merge_gate_is_the_only_autonomous_merge_path(self):
        self.assertEqual(self.bash("gh pr merge 5 --squash"), 2)
        self.assertEqual(self.bash("gh api -X PUT repos/o/r/pulls/5/merge"), 2)
        self.assertEqual(self.bash("curl -X PUT https://api.github.com/repos/o/r/pulls/5/merge"), 2)
        self.assertEqual(
            self.bash("/srv/studio/bin/merge-gate merge --issue i --repo o/r --pr 5 --head " + "a" * 40), 0)
        self.assertEqual(self.bash("gh pr view 5"), 0)

    def test_drain_stop_pause_and_resume_are_human_only(self):
        for c in ("studio-stop resume", "/srv/studio/bin/studio-stop stop",
                  "curl -X POST localhost:3100/api/agents/abc-1/resume",
                  "curl -X POST localhost:3100/api/agents/abc-1/pause"):
            self.assertEqual(self.bash(c), 2, c)
        self.assertEqual(self.bash("python -m unittest tests.test_stop"), 0)

    def test_policy_directory_is_never_allowed(self):
        self.assertEqual(run("Write", {"file_path": "policy/autonomous-merge.json", "content": "{}"}, self.work,
                             {"STUDIO_ALLOWED_PATHS": "policy/**"}), 2)
        self.assertEqual(self.bash("sed -i s/x/y/ policy/autonomous-merge.json"), 2)


if __name__ == "__main__":
    unittest.main()
