"""Usage-cap controller (research section 3.2): admit an agent run only if the studio stays inside its caps.

Readings are the provider's own account percentages (Claude: `claude -p /usage`). The account meter also
counts Benjamin's personal use, so studio use is attributed by interval: usage that accrues between two
readings while any studio run is active is counted as studio use (a conservative bound: personal use at the
same moment is counted against the studio, never the other way round). Readings are taken when a run starts
and when it ends, so the set of active runs is constant between consecutive readings.

Before a run starts, its estimated cost is reserved and every check must pass:
  studio 5-hour used + reserved + this job + margin <= five_hour_cap   (12 Claude, 15 Codex)
  studio weekly used + reserved + this job + margin <= weekly_cap      (80)
  account 5-hour used + reserved + this job + margin <= 100
  account weekly used + reserved + this job + margin + personal allowance still unused <= 100
No reading means no admission. Estimates start from policy and move to the largest recent measured run
for that agent. These are operating caps, not a proof against overshoot: usage is reported late and rounded.
"""
import json
import os
import re
import time
import uuid

WINDOWS = ("five_hour", "week")
LINE = re.compile(r"^\s*Current (session|week \(([^)]*)\)):\s*([\d.]+)% used(?:\s*·\s*resets (.+?))?\s*$")


class QuotaError(Exception):
    pass


def parse_usage(text):
    """{"five_hour": {"pct", "key"}, "week": {...}, "other": {label: pct}} from `claude /usage` output."""
    out = {"other": {}}
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        kind, model, pct, reset = m.group(1), m.group(2), float(m.group(3)), (m.group(4) or "").strip()
        if kind == "session":
            out["five_hour"] = {"pct": pct, "key": reset}
        elif model and model.lower() == "all models":
            out["week"] = {"pct": pct, "key": reset}
        else:
            out["other"][model] = pct
    missing = [w for w in WINDOWS if w not in out]
    if missing:
        raise QuotaError(f"usage reading has no {' or '.join(missing)} line")
    return out


def empty():
    return {"last": None, "studio": {w: {} for w in WINDOWS}, "active": {}, "samples": {}}


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def observe(ledger, reading, now):
    """Attribute usage since the last reading, then remember this reading."""
    last = ledger.get("last")
    active = ledger["active"]
    for w in WINDOWS:
        cur = reading[w]
        prev = (last or {}).get(w)
        if prev is None:
            delta = 0.0  # nothing to compare with; the first reading is taken before any run starts
        elif prev["key"] == cur["key"]:
            delta = max(0.0, cur["pct"] - prev["pct"])
        else:
            delta = cur["pct"]  # a new window began since the last reading
        if active and delta > 0:
            studio = ledger["studio"][w]
            studio[cur["key"]] = round(studio.get(cur["key"], 0.0) + delta, 3)
            for run in active.values():
                run["used"][w] = round(run["used"][w] + delta, 3)
        ledger["studio"][w] = {k: v for k, v in ledger["studio"][w].items() if k == cur["key"]}
    ledger["last"] = {"t": now, **{w: reading[w] for w in WINDOWS}}


def _finish(ledger, token):
    run = ledger["active"].pop(token)
    samples = ledger["samples"].setdefault(run["agent"], [])
    samples.append([run["used"]["five_hour"], run["used"]["week"]])
    del samples[:-20]


def _drop_finished(ledger, policy, now, pid_alive):
    """Runs whose process is gone (or that are too old) were active until this reading; now they end."""
    for token, run in list(ledger["active"].items()):
        if run.get("ended") or not pid_alive(run["pid"]) or now - run["t"] > policy["max_run_hours"] * 3600:
            _finish(ledger, token)


def estimate(ledger, agent, policy):
    samples = ledger["samples"].get(agent, [])
    if len(samples) < policy["estimate_samples"]:
        return dict(policy["default_job"])
    return {w: max(policy["min_job"][w], max(s[i] for s in samples)) for i, w in enumerate(WINDOWS)}


def status(ledger, reading, policy):
    reserved = {w: sum(max(0.0, r["reserve"][w] - r["used"][w]) for r in ledger["active"].values()) for w in WINDOWS}
    studio = {w: ledger["studio"][w].get(reading[w]["key"], 0.0) for w in WINDOWS}
    return {"account": {w: reading[w]["pct"] for w in WINDOWS}, "studio": studio, "reserved": reserved,
            "resets": {w: reading[w]["key"] for w in WINDOWS}, "caps": {"five_hour": policy["five_hour_cap"],
            "week": policy["weekly_cap"]}, "active_runs": len(ledger["active"])}


def admit(ledger, reading, agent, pid, policy, now, pid_alive=_pid_alive):
    """Returns (token, []) when admitted, else (None, reasons). Mutates the ledger either way."""
    observe(ledger, reading, now)
    _drop_finished(ledger, policy, now, pid_alive)
    job = estimate(ledger, agent, policy)
    s = status(ledger, reading, policy)
    m = policy["margin"]
    reasons = []

    def need(label, used, w, limit, extra=0.0):
        total = used + s["reserved"][w] + job[w] + m[w] + extra
        if total > limit:
            reasons.append(f"{label}: used {used:g} + reserved {s['reserved'][w]:g} + this run {job[w]:g} + margin "
                           f"{m[w]:g}{f' + personal {extra:g}' if extra else ''} = {total:g} > {limit:g} "
                           f"(resets {reading[w]['key'] or 'unknown'})")

    need("studio 5-hour", s["studio"]["five_hour"], "five_hour", policy["five_hour_cap"])
    need("studio weekly", s["studio"]["week"], "week", policy["weekly_cap"])
    need("account 5-hour", s["account"]["five_hour"], "five_hour", 100)
    personal_used = max(0.0, s["account"]["week"] - s["studio"]["week"])
    need("account weekly", s["account"]["week"], "week", 100, max(0.0, policy["personal_weekly"] - personal_used))
    for model, pct in reading.get("other", {}).items():
        if pct + m["week"] > 100:
            reasons.append(f"{model} weekly limit {pct:g}% used")
    if reasons:
        return None, reasons
    token = uuid.uuid4().hex
    ledger["active"][token] = {"agent": agent, "pid": pid, "t": now, "reserve": job,
                               "used": {w: 0.0 for w in WINDOWS}}
    return token, []


def release(ledger, token, reading, now):
    """End a run. Without a reading it stays active (conservatively) until the next reading ends it."""
    if token not in ledger["active"]:
        return
    if reading is None:
        ledger["active"][token]["ended"] = True
        return
    observe(ledger, reading, now)
    _finish(ledger, token)


def load_policy(path, provider):
    with open(path) as f:
        return json.load(f)[provider]


class Ledger:
    """The ledger file, locked for the whole read-decide-write. Owned by paperclip; agents cannot write it."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        import fcntl
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        self.f = open(os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600), "r+")
        fcntl.flock(self.f, fcntl.LOCK_EX)
        text = self.f.read()
        self.data = json.loads(text) if text.strip() else empty()
        return self.data

    def __exit__(self, *exc):
        if exc[0] is None:
            self.f.seek(0)
            self.f.truncate()
            json.dump(self.data, self.f, indent=1)
            self.f.flush()
            os.fsync(self.f.fileno())
        self.f.close()


def now():
    return time.time()
