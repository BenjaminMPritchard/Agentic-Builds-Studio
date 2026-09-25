"""Pacer: at most N heavy Claude runs at once, and hold heavy wakes after a usage-limit failure."""
import json
import os
import re
import time

HEAVY_ROLES = {"principal", "builder-1", "builder-2"}  # matched against the agent's name, lowercased
MAX_HEAVY = 2
LIMIT_WORDS = re.compile(r"usage limit|rate.?limit|limit reached|resets? at", re.I)
DEFAULT_HOLD_SEC = 3600  # TODO(check): parse the real reset time once we've seen how the limit error appears


def load(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def save(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(state, open(path, "w"))


def update(state, runs, agent_names, now=None):
    """Look at recent runs. Returns (state, heavy_running)."""
    now = now or time.time()
    heavy = 0
    for r in runs:
        name = agent_names.get(r.get("agentId"), "").lower()
        if r.get("status") == "running" and name in HEAVY_ROLES:
            heavy += 1
        if r.get("status") in ("failed", "error") and LIMIT_WORDS.search(str(r.get("error", ""))):
            rid = r.get("id")
            if rid != state.get("last_limit_run"):
                state.update(last_limit_run=rid, hold_until=now + DEFAULT_HOLD_SEC, limit_hit_at=now)
    return state, heavy


def heavy_allowed(state, heavy_running, now=None):
    now = now or time.time()
    if state.get("hold_until", 0) > now:
        return False, f"held until {time.strftime('%H:%M', time.localtime(state['hold_until']))} after a usage-limit failure"
    if heavy_running >= MAX_HEAVY:
        return False, f"{heavy_running} heavy runs already active (max {MAX_HEAVY})"
    return True, "ok"
