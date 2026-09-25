import glob, json, os, re, unittest

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = lambda *a: os.path.join(R, *a)


class Structure(unittest.TestCase):
    def test_agents_complete_and_short(self):
        for a in ["director", "principal", "builder-1", "builder-2", "liaison", "architect", "recorder"]:
            for f in ("AGENTS.md", "HEARTBEAT.md", "TOOLS.md"):
                self.assertTrue(os.path.isfile(p("agents", a, f)), f"{a}/{f}")
            self.assertLess(len(open(p("agents", a, "AGENTS.md")).read().splitlines()), 60)
        self.assertIn("never", open(p("agents/director/AGENTS.md")).read().lower())

    def test_settings_wire_the_guard_and_deny_rules(self):
        s = json.load(open(p("claude/settings.json")))
        deny = s["permissions"]["deny"]
        for r in ("Agent", "Bash(git push --force*)", "Bash(gh pr merge*)", "Bash(make e2e*)"):
            self.assertIn(r, deny)
        cmds = {h["command"] for e in s["hooks"]["PreToolUse"] for h in e["hooks"]}
        self.assertEqual(cmds, {"/srv/studio/bin/guard"})
        self.assertNotIn("allow", s["permissions"])
        eff = {n: json.load(open(p("claude", f"{n}.json"))) for n in ("director", "builder", "principal", "liaison", "architect")}
        self.assertEqual((eff["director"], eff["principal"], eff["architect"]), ({"maxEffortLevel": "medium"}, {"maxEffortLevel": "high"}, {}))

    def test_payloads(self):
        for f in glob.glob(p("package/payloads/*.json")):
            json.load(open(f))
        m = {n: json.load(open(p(f"package/payloads/agent-{n}.json"))) for n in
             ("director", "principal", "builder-1", "builder-2", "liaison", "architect", "recorder", "clerk", "worker")}
        self.assertEqual(m["director"]["adapterConfig"]["model"], "claude-opus-5-5")
        self.assertEqual(m["builder-1"]["adapterConfig"]["model"], "claude-sonnet-5")
        self.assertEqual(m["director"]["runtimeConfig"]["heartbeat"]["intervalSec"], 0)  # no Director timer
        self.assertEqual(m["worker"]["adapterConfig"]["command"], "/srv/studio/bin/qwen-run")
        for n, a in m.items():
            env = a["adapterConfig"].get("env", {})
            self.assertNotIn("ANTHROPIC_API_KEY", env, n)  # would bill the API instead of the subscription
            self.assertFalse(any("live" in json.dumps(v) for v in env.values()), n)
            if a["adapterType"] == "claude_local":
                self.assertIn("model", a["adapterConfig"], n)  # blank model defaults to Opus
                self.assertIs(a["permissions"]["canCreateAgents"], False, n)
        for n in ("architect", "recorder"):
            env = m[n]["adapterConfig"]["env"]
            self.assertIn("gh-studio-ops-internal", env["GH_TOKEN"]["secretId"])
            self.assertIn("gh-studio-ops-external", env["GH_TOKEN_SITE_READ"]["secretId"])
        routines = json.load(open(p("package/payloads/routines.json")))["routines"]
        self.assertNotIn("Director", [r["assignee"] for r in routines])

    def test_constitution_and_codeowners(self):
        c = open(p("CONSTITUTION.md")).read()
        for w in ("merge", "live keys", "DNS", "force-push", "sub-agents", "Architect"):
            self.assertIn(w, c)
        self.assertIn("CONSTITUTION.md @BenjaminMPritchard", open(p(".github/CODEOWNERS")).read())

    def test_project_yaml_bridge(self):
        y = open(p("projects/mothers-carpentry/project.yaml")).read()
        for w in ("repo: Agentic-Builds-Studio/Mothers-Carpentry-Webpage", "db_name: \"mc_{task}\"", "8001", "5174",
                  "roadmap: 1", "owner_questions: 4", "director_brief: 23", "merge: human"):
            self.assertIn(w, y)
        self.assertNotIn("sk_live", y)

    def test_no_secret_shaped_strings_anywhere(self):
        rx = re.compile(r"(sk|pk|rk)_live_[A-Za-z0-9]{6,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|sk-ant-\w{10,}")
        for f in glob.glob(p("**/*"), recursive=True):
            if os.path.isfile(f) and not f.endswith((".pyc",)) and "__pycache__" not in f and "/tests/" not in f:
                self.assertIsNone(rx.search(open(f, errors="ignore").read()), f)


if __name__ == "__main__":
    unittest.main()
