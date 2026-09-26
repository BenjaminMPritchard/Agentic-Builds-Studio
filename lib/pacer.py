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


# ---- real subscription usage (Paperclip: GET /api/companies/{id}/costs/quota-windows) -----------------
SESSION_LIMIT = float(os.environ.get("PACER_SESSION_PCT", 85))  # pause new Claude work above this % of the 5-hour session
WEEK_LIMIT = float(os.environ.get("PACER_WEEK_PCT", 0))         # weekly hold is off by default (0); set e.g. 95 to enable


def parse_windows(report):
    """{"session": window, "week": window} from the anthropic entry of the quota report; {} if unavailable."""
    for prov in report or []:
        if prov.get("provider") == "anthropic" and prov.get("ok"):
            out = {}
            for w in prov.get("windows", []):
                label = (w.get("label") or "").lower()
                if w.get("usedPercent") is None:
                    continue
                if "session" in label:
                    out["session"] = w
                elif "week" in label and "all" in label:
                    out["week"] = w
            return out
    return {}


def _when(iso):
    return (iso or "?")[:16].replace("T", " ") + " UTC" if iso else "?"


def decide(win, session_limit=None, week_limit=None):
    """Hold (pause heavy Claude work) when either allowance is over its limit. Unknown usage never holds."""
    limits = (("session", SESSION_LIMIT if session_limit is None else session_limit, "5-hour session"), ("week", WEEK_LIMIT if week_limit is None else week_limit, "weekly"))
    reasons = [f"{name} allowance {win[k]['usedPercent']:.0f}% used (limit {lim:.0f}%), resets {_when(win[k].get('resetsAt'))}"
               for k, lim, name in limits if lim and k in win and win[k]["usedPercent"] >= lim]
    return {"hold": bool(reasons), "reasons": reasons}


def describe(win):
    if not win:
        return "usage unknown"
    return ", ".join(f"{k} {w['usedPercent']:.0f}% (resets {_when(w.get('resetsAt'))})" for k, w in win.items())
