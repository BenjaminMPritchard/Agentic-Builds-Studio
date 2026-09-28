"""DRAIN / STOP / RESUME for the whole company. A human tool; deterministic, no model.

Paperclip's pause is a hard stop: it cancels the agent's active runs. So:
- drain: pause each unpaused agent once it has no active run; never forces. Unfinished agents are reported.
- stop:  pause every unpaused agent now (their active runs are cancelled).
- resume: resume only agents this tool paused, and only if their `pausedAt` is unchanged since then.
  Agents paused by anyone else (a human, the Clerk) are never resumed here.
State lives in <data>/stop-state.json: {"paused_by_stop": {agent_id: pausedAt}}.
"""
import json
import os
import time

ACTIVE = ("queued", "running")


def load_state(path):
    try:
        with open(path) as f:
            s = json.load(f)
        return s if isinstance(s.get("paused_by_stop"), dict) else {"paused_by_stop": {}}
    except FileNotFoundError:
        return {"paused_by_stop": {}}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def active_agents(pc, company_id):
    return {r.get("agentId") for r in pc.runs(company_id, limit=200) if r.get("status") in ACTIVE}


def _pause(pc, agent, state, path, out):
    after = pc.pause_agent(agent["id"])
    state["paused_by_stop"][agent["id"]] = (after or {}).get("pausedAt")
    save_state(path, state)  # record each pause as it happens, so a crash cannot orphan one
    out.append(f"paused {agent['name']}")


def stop(pc, company_id, path):
    state, out = load_state(path), []
    for a in pc.list_agents(company_id):
        if a.get("status") != "paused":
            _pause(pc, a, state, path, out)
    return out


def drain(pc, company_id, path, timeout=1800, interval=10, sleep=time.sleep, now=time.monotonic):
    """Returns (done, lines). done is False if some agent was still busy at the timeout."""
    state, out, deadline = load_state(path), [], now() + timeout
    while True:
        busy = active_agents(pc, company_id)
        waiting = []
        for a in pc.list_agents(company_id):
            if a.get("status") == "paused":
                continue
            if a["id"] in busy:
                waiting.append(a["name"])
            else:
                _pause(pc, a, state, path, out)
        if not waiting:
            return True, out
        if now() >= deadline:
            out.append("still running at timeout (not paused): " + ", ".join(sorted(waiting)))
            return False, out
        sleep(interval)


def resume(pc, company_id, path):
    state, out = load_state(path), []
    agents = {a["id"]: a for a in pc.list_agents(company_id)}
    for aid, paused_at in sorted(state["paused_by_stop"].items()):
        a = agents.get(aid)
        if not a:
            out.append(f"skip {aid}: agent no longer exists")
        elif a.get("status") != "paused":
            out.append(f"skip {a['name']}: no longer paused")
        elif a.get("pausedAt") != paused_at:
            out.append(f"skip {a['name']}: paused again since (left paused)")
            continue  # someone else owns this pause now; forget ours
        else:
            pc.resume_agent(aid)
            out.append(f"resumed {a['name']}")
        state["paused_by_stop"].pop(aid, None)
        save_state(path, state)
    for aid in [k for k in state["paused_by_stop"] if agents.get(k, {}).get("pausedAt") != state["paused_by_stop"][k]]:
        state["paused_by_stop"].pop(aid, None)
    save_state(path, state)
    return out


def status(pc, company_id, path):
    state, busy = load_state(path), active_agents(pc, company_id)
    lines = []
    for a in pc.list_agents(company_id):
        owner = "studio-stop" if state["paused_by_stop"].get(a["id"]) == a.get("pausedAt") and a.get("status") == "paused" \
            else ("other" if a.get("status") == "paused" else "")
        lines.append(f"{a['name']:12} {a.get('status', ''):8} {'active run' if a['id'] in busy else '':10} {owner}".rstrip())
    return lines
