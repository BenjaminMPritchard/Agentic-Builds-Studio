#!/usr/bin/env python3
"""Create an agent in Paperclip from package/payloads/agent-<name>.json (Board key). Dry run unless --apply.

  python3 package/create-agent.py scout codex-scout ... [--apply]

Placeholders are resolved from the live company: <director> is the Director's id, <claude-oauth> and
<gh-studio-ops-external> are secret ids (by secret name), and short skill names become the company's skill
keys. The agent is paused straight after it is created, so it never runs until Benjamin resumes it. An agent
whose name already exists is left alone.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))
from lib.paperclip import Paperclip  # noqa: E402

COMPANY = "bcf0f336-0c20-4194-9e21-fac517979ba0"
SECRETS = {"<claude-oauth>": "claude-oauth", "<gh-studio-ops-external>": "Github Studio Ops External"}
HERE = os.path.dirname(os.path.realpath(__file__))


def resolve(payload, agents, secrets, skills):
    text = json.dumps(payload)
    text = text.replace('"<director>"', json.dumps(agents["Director"]))
    for placeholder, name in SECRETS.items():
        if placeholder in text:
            text = text.replace(placeholder, secrets[name])
    body = json.loads(text)
    wanted = body.pop("desiredSkills", [])
    missing = [s for s in wanted if s not in skills]
    if missing:
        raise SystemExit(f"unknown skills for {body['name']}: {missing}")
    body["desiredSkills"] = [skills[s] for s in wanted]
    return body


def main(names, apply):
    pc = Paperclip()
    agents = {a["name"]: a["id"] for a in pc.list_agents(COMPANY)}
    secrets = {s["name"]: s["id"] for s in pc.call("GET", f"/api/companies/{COMPANY}/secrets")}
    skills = {s["slug"]: s["key"] for s in pc.call("GET", f"/api/companies/{COMPANY}/skills")}
    for name in names:
        with open(os.path.join(HERE, "payloads", f"agent-{name}.json")) as f:
            body = resolve(json.load(f), agents, secrets, skills)
        if body["name"] in agents:
            print(f"exists: {body['name']}")
            continue
        c = body["adapterConfig"]
        summary = (f"{body['name']}: {body['adapterType']} {c.get('model')} via {c.get('command')}, "
                   f"skills {len(body['desiredSkills'])}, then paused")
        if not apply:
            print("DRY RUN: create", summary)
            continue
        made = pc.call("POST", f"/api/companies/{COMPANY}/agents", body)
        pc.pause_agent(made["id"])
        print("created", summary, "->", made["id"], pc.call("GET", f"/api/agents/{made['id']}")["status"])


if __name__ == "__main__":
    args = sys.argv[1:]
    main([a for a in args if a != "--apply"], "--apply" in args)
