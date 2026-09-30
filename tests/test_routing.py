"""policy/routing.json stays consistent with itself, the usage caps, the agents and the research's model rules."""
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(*p):
    with open(os.path.join(ROOT, *p)) as f:
        return json.load(f) if p[-1].endswith(".json") else f.read()


class Routing(unittest.TestCase):
    def setUp(self):
        self.r = load("policy", "routing.json")
        self.agents = self.r["agents"]

    def test_every_route_names_known_agents_and_has_an_active_option(self):
        for route in self.r["routes"]:
            names = route["first"] + route["fallback"] + route.get("review", [])
            for n in names:
                self.assertIn(n, self.agents, (route["class"], n))
            active = [n for n in route["first"] + route["fallback"] if self.agents[n]["status"] == "active"]
            self.assertTrue(active, f"{route['class']} has no active agent to route to")
            for key in ("class", "examples", "escalate_when", "accept"):
                self.assertTrue(route.get(key), (route["class"], key))

    def test_agents_are_well_formed(self):
        for name, a in self.agents.items():
            self.assertIn(a["status"], ("active", "planned"), name)
            self.assertIn(a["provider"], ("claude", "codex", "local", "script"), name)
            if a["provider"] in ("claude", "codex", "local"):
                self.assertTrue(a.get("model"), name)

    def test_active_claude_agents_have_instructions(self):
        for name, a in self.agents.items():
            if a["provider"] == "claude" and a["status"] == "active":
                self.assertTrue(os.path.isdir(os.path.join(ROOT, "agents", name.lower())), name)

    def test_no_retired_or_paid_models(self):
        # Research 4.1/4.2: GPT-5.4 variants retired 2026-08-31, GPT-5.5 retires 2026-10-14; Fable needs usage
        # credits on Pro, which the no-extra-spend rule excludes.
        for name, a in self.agents.items():
            model = a.get("model") or ""
            self.assertNotRegex(model, r"^gpt-5\.(4|5)\b", name)
            self.assertNotIn("fable", model, name)

    def test_caps_match_the_enforced_policy(self):
        quota = load("policy", "quota.json")
        for provider in ("claude", "codex"):
            self.assertEqual(self.r["caps"][provider],
                             {"five_hour": quota[provider]["five_hour_cap"], "week": quota[provider]["weekly_cap"]})

    def test_the_skill_names_every_agent_and_the_evidence_packet(self):
        skill = load("skills", "routing-table", "SKILL.md")
        for name in self.agents:
            self.assertTrue(re.sub(r"-\d$", "", name) in skill, f"{name} is not in the routing-table skill")
        for field in self.r["rules"]["evidence_packet"]:
            self.assertTrue(f"`{field}`" in skill, f"evidence field {field} is not in the skill")
        planned = [n for n, a in self.agents.items() if a["status"] == "planned"]
        for n in planned:  # any agent still planned must be named as such in the skill
            self.assertTrue(n in skill[skill.index("**Only route to active agents.**"):], f"{n} is not listed as planned")

    def test_director_and_packets_point_at_the_table(self):
        self.assertIn("skill `routing-table`", load("agents", "director", "AGENTS.md"))
        self.assertIn("routing-table", load("skills", "task-packet", "SKILL.md"))
        self.assertIn("**Route:**", load("templates", "task-packet.md"))


if __name__ == "__main__":
    unittest.main()
