"""Usage-cap controller (research section 3.2): admit an agent run only if the studio stays inside its caps.

Readings are the provider's own account percentages (Claude: `claude -p /usage`). The account meter also
counts Benjamin's personal use, so studio use is attributed by interval: usage that accrues between two
readings while any studio run is active is counted as studio use (a conservative bound: personal use at the
same moment is counted against the studio, never the other way round). Readings are taken when a run starts
and when it ends, so the set of active runs is constant between consecutive readings.

Before a run starts, its estimated cost is reserved and every check must pass:
  studio 5-hour used + reserved + this job + margin <= five_hour_cap   (policy/quota.json: 30 Claude, 60 Codex)
  studio weekly used + reserved + this job + margin <= weekly_cap      (80 Claude, 100 Codex)
  account 5-hour used + reserved + this job + margin <= 100
  account weekly used + reserved + this job + margin + personal allowance still unused <= 100
The policy's `reserve` keeps some five-hour points back for the agents it names (the Director): every other agent
works to five_hour_cap minus the reserve, and a named agent's own estimate counts for at most the reserve less
the margin.
No reading means no admission. Estimates start from policy and move to the largest recent measured run
for that agent. While a run is active its watcher also reads usage every minute (over_cap) and stops the
run once studio use reaches a cap: admission alone let one Codex run take a whole five-hour window. These are
operating caps, not a proof against overshoot: usage is reported late and rounded, and the check is periodic.
"""
import json
import os
import re
import time
import uuid

WINDOWS = ("five_hour", "week")
DROP = 1.0  # percentage points of rounding noise tolerated before a falling reading means a new window
LINE = re.compile(r"^\s*Current (session|week \(([^)]*)\)):\s*([\d.]+)% used(?:\s*·\s*resets (.+?))?\s*$")


class QuotaError(Exception):
    pass


SAME_WINDOW_SECONDS = 3600  # reset times that differ by less than this are one window (Claude rounds them)
RESET = re.compile(r"^(?:([A-Z][a-z]{2}) (\d{1,2}), )?(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*\(([^)]+)\)$")
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def parse_reset(text, now):
    """Epoch seconds for a `claude /usage` reset such as "Sep 29, 6:50am (Europe/London)" or "7:40am
    (Europe/London)"; None if it cannot be read (the text is then compared as it is)."""
    import datetime
    from zoneinfo import ZoneInfo
    m = RESET.match((text or "").strip())
    if not m:
        return None
    mon, day, hour, minute, ampm, zone = m.groups()
    try:
        tz = ZoneInfo(zone)
    except Exception:
        return None
    hour = int(hour) % 12 + (12 if ampm == "pm" else 0)
    today = datetime.datetime.fromtimestamp(now, tz)
    if mon:
        at = today.replace(month=MONTHS[mon], day=int(day), hour=hour, minute=int(minute or 0), second=0, microsecond=0)
        if at.timestamp() < now - 2 * 86400:  # "Jan 2" read in late December is next year
            at = at.replace(year=at.year + 1)
    else:
        at = today.replace(hour=hour, minute=int(minute or 0), second=0, microsecond=0)
        if at.timestamp() < now - 3600:
            at += datetime.timedelta(days=1)
    return at.timestamp()


def same_window(prev, cur, now=None):
    """Whether two readings may be one window; observe() still treats a falling reading as a new one. A reading
    with no reset time (Claude shows none at a window's start) is not evidence of a new window. 2026-10-20: the key
    went between "" and "Oct 20, 8:10am" from 03:12, and each change counted the whole account as new use."""
    if prev["key"] == cur["key"] or not prev["key"] or not cur["key"]:
        return True
    now = time.time() if now is None else now
    # Readings stored before reset times were parsed carry only the text: parse it now.
    a = prev.get("at") if prev.get("at") is not None else parse_reset(prev["key"], now)
    b = cur.get("at") if cur.get("at") is not None else parse_reset(cur["key"], now)
    return a is not None and b is not None and abs(a - b) < SAME_WINDOW_SECONDS


def parse_usage(text, now=None):
    """{"five_hour": {"pct", "key", "at"}, "week": {...}, "other": {label: pct}} from `claude /usage` output."""
    now = time.time() if now is None else now
    out = {"other": {}}
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        kind, model, pct, reset = m.group(1), m.group(2), float(m.group(3)), (m.group(4) or "").strip()
        if kind == "session":
            out["five_hour"] = {"pct": pct, "key": reset, "at": parse_reset(reset, now)}
        elif model and model.lower() == "all models":
            out["week"] = {"pct": pct, "key": reset, "at": parse_reset(reset, now)}
        else:
            out["other"][model] = pct
    missing = [w for w in WINDOWS if w not in out]
    if missing:
        raise QuotaError(f"usage reading has no {' or '.join(missing)} line")
    return out


CODEX_WINDOWS = {300: "five_hour", 10080: "week"}  # by duration in minutes, never by "primary"/"secondary"


def parse_codex(result):
    """Reading from the Codex App Server's `account/rateLimits/read` result. The studio caps apply to the
    `codex` bucket; every other bucket (a per-model limit) counts only toward account headroom. A window of
    an unexpected length, or no `codex` bucket, is an error: no reading, no run."""
    buckets = (result or {}).get("rateLimitsByLimitId") or {}
    if "codex" not in buckets:
        raise QuotaError("Codex rate limits have no `codex` bucket")
    out = {"other": {}}
    for bucket_id, bucket in buckets.items():
        for slot in ("primary", "secondary"):
            w = (bucket or {}).get(slot)
            if not w:
                continue
            kind = CODEX_WINDOWS.get(w.get("windowDurationMins"))
            if kind is None:
                raise QuotaError(f"Codex bucket {bucket_id} has a {w.get('windowDurationMins')}-minute window")
            if w.get("usedPercent") is None:
                raise QuotaError(f"Codex bucket {bucket_id} {kind} has no usage figure")
            if bucket_id == "codex":
                at = w.get("resetsAt")
                out[kind] = {"pct": float(w["usedPercent"]), "at": float(at) if at else None,
                             "key": time.strftime("%b %d %H:%M UTC", time.gmtime(at)) if at else ""}
            else:
                out["other"][f"{bucket_id} {kind}"] = float(w["usedPercent"])
    missing = [w for w in WINDOWS if w not in out]
    if missing:
        raise QuotaError(f"Codex rate limits have no {' or '.join(missing)} window")
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
        elif same_window(prev, cur, now) and cur["pct"] >= prev["pct"] - DROP:
            delta = max(0.0, cur["pct"] - prev["pct"])
            if prev["key"] != cur["key"]:  # the reset time was reworded or rounded: keep the window's total
                studio = ledger["studio"][w]
                studio[cur["key"]] = round(studio.get(cur["key"], 0.0) + studio.pop(prev["key"], 0.0), 3)
        else:
            # A new window began since the last reading. Use never falls inside one window, so a drop is a new
            # window too, even with an unchanged reset time (Benjamin reset Codex use on 2026-10-01).
            delta = cur["pct"]
            ledger["studio"][w].pop(cur["key"], None)
        if active and delta > 0:
            studio = ledger["studio"][w]
            studio[cur["key"]] = round(studio.get(cur["key"], 0.0) + delta, 3)
            for run in active.values():
                run["used"][w] = round(run["used"][w] + delta, 3)  # the bound: all use while the run was active
                share = run.setdefault("share", {x: 0.0 for x in WINDOWS})
                share[w] = round(share[w] + delta / len(active), 3)  # its part of that: split between active runs
        ledger["studio"][w] = {k: v for k, v in ledger["studio"][w].items() if k == cur["key"]}
    ledger["last"] = {"t": now, **{w: reading[w] for w in WINDOWS}}


WRAP_UP_POINTS = 2  # a run is asked to wrap up this close to a cap, so its wrap-up fits inside the cap
WRAP_UP_MINUTES = 10  # and is stopped only if it is still going this long after being asked


def held_back(policy, agent):
    """Five-hour points this agent may not use: the reserve, unless the reserve is for this agent. Benjamin,
    2026-10-14: the Director must always be able to run; Builder runs of 17 points used to leave it nothing."""
    r = policy.get("reserve") or {}
    return 0.0 if agent in r.get("agents", ()) else float(r.get("five_hour", 0))


def _cap_text(policy, agent, w):
    back = held_back(policy, agent) if w == "five_hour" else 0.0
    cap = {"five_hour": policy["five_hour_cap"], "week": policy["weekly_cap"]}[w]
    return cap - back, (f"{cap - back:g}-point cap ({cap:g}, less {back:g} kept for the Director)" if back
                        else f"{cap:g}-point cap")


def over_cap(ledger, reading, policy, now, headroom=0, agent=None, token=None, every=0):
    """Take a reading during a run; the reasons studio use is within `headroom` of a cap (empty while not). The
    cap is the agent's own: less the reserve unless the reserve is for it.

    With the run's `token` and the seconds until the next check (`every`), a run asked to wrap up (headroom > 0)
    is asked one check early when, at its own pace since admission, it would pass the wrap-up line before then.
    2026-10-18: a Builder-2 run used 25 points in 10 minutes; checks two minutes apart saw it first at 23 of 18.
    With policy["week_pace"], a run is also asked to wrap up once today's share of the week is spent."""
    observe(ledger, reading, now)
    s = status(ledger, reading, policy)
    run = ledger["active"].get(token) if token else None
    out = []
    for w, label in (("five_hour", "5-hour"), ("week", "weekly")):
        cap, text = _cap_text(policy, agent, w)
        used = s["studio"][w]
        resets = f"resets {s['resets'][w] or 'unknown'}"
        if used >= cap - headroom:
            out.append(f"studio {label} use {used:g} of the {text} ({resets})")
        elif run and headroom > 0 and every > 0:
            ahead = run["used"][w] / max(60.0, now - run["t"]) * every
            if used + ahead >= cap - headroom:
                out.append(f"studio {label} use {used:g} of the {text}, and this run's pace adds about "
                           f"{ahead:.0f} more by the next check ({resets})")
    # Today's share of the week (week_pace) only ever asks for a wrap-up, never a stop without one. 2026-10-19:
    # admission checked only that the smallest run fitted, so two Codex runs spent 7.8 of a 3.6-point day.
    pace = week_pace(ledger, reading, policy, now, update=False) if headroom > 0 else None
    if pace:
        spent, budget, _ = pace
        ahead = run["used"]["week"] / max(60.0, now - run["t"]) * every if run and every > 0 else 0.0
        if spent >= budget:
            out.append(f"studio weekly pace: used {spent:g} of today's {budget:g}")
        elif spent + ahead >= budget:
            out.append(f"studio weekly pace: used {spent:g} of today's {budget:g}, and this run's pace adds about "
                       f"{ahead:.1f} more by the next check")
    return out


def account_nearly_out(reading, policy):
    """True when the account itself is within the margin of 100% in either window: past that, Benjamin's own use
    would be cut off, so a run asked to wrap up is stopped without waiting for it."""
    return any(reading[w]["pct"] >= 100 - policy["margin"][w] for w in WINDOWS)


def _finish(ledger, token, now, how):
    run = ledger["active"].pop(token)
    samples = ledger["samples"].setdefault(run["agent"], [])
    samples.append([run["used"]["five_hour"], run["used"]["week"]])
    del samples[:-20]
    # One record per run for the Clerk (research 11.1, quotas): attributed use is a bound, not a measurement.
    last = ledger.get("last") or {}
    ledger.setdefault("finished", []).append({
        "run": run.get("run") or None, "agent": run["agent"], "admitted_at": run["t"], "ended_at": now,
        "ended": how, "used": run["used"], "reserved": run["reserve"], "attribution": "bounded",
        "windows": {w: (last.get(w) or {}).get("key") for w in WINDOWS}})


def flush_finished(ledger, path):
    """Append finished-run records to `path` (JSON lines) and drop them from the ledger. Called while the
    ledger is locked, so each record is written once; the Clerk also de-duplicates by run id."""
    done = ledger.pop("finished", [])
    if not done:
        return 0
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        for rec in done:
            f.write(json.dumps(rec) + "\n")
    return len(done)


GONE_RECENT = 15 * 60  # seconds: a run gone since a reading this recent still gets the usage reported after it


def _drop_gone(ledger, policy, now, pid_alive):
    """Before counting new usage: a run whose process is gone (or that is too old) ended at some unknown time,
    so it gets none of the usage since the last reading. Otherwise a run killed with its release watcher (a
    service restart) would absorb everything the account uses until the next admission (2026-09-30: 15 points
    of Benjamin's own use). A run gone since a reading under GONE_RECENT old ended just now, as the next run
    starts before its watcher has released it: it still gets the usage reported since, which is its own, as
    usage is reported late. 2026-10-18: back-to-back Codex runs each lost theirs, and the studio counted 63 of a
    5-hour window the account showed at 86."""
    last = (ledger.get("last") or {}).get("t")
    for token, run in list(ledger["active"].items()):
        if run.get("ended"):
            continue
        if not pid_alive(run["pid"]):
            if last is not None and now - last <= GONE_RECENT:
                run["ended"] = "process gone"  # counted, then finished by _drop_ended
            else:
                _finish(ledger, token, now, "process gone")
        elif now - run["t"] > policy["max_run_hours"] * 3600:
            _finish(ledger, token, now, "too old")


def _drop_ended(ledger, now):
    """After counting: runs released without a reading, or gone since a recent one, ended just before this
    reading; now they end."""
    for token, run in list(ledger["active"].items()):
        if run.get("ended"):
            _finish(ledger, token, now, run["ended"] if isinstance(run["ended"], str) else "released without a reading")


def estimate(ledger, agent, policy):
    """The largest of the agent's recent runs, but never more than half the cap. An estimate near the cap refuses
    the agent as soon as the window has any use in it (2026-10-01: Codex-Principal at 27 of 28 could not start with
    6 used), and with no new runs no smaller sample could ever replace it. Half is enough to reserve: the mid-run
    checks stop a run that takes the window over the cap, so the reservation need not cover a whole large run."""
    samples = ledger["samples"].get(agent, [])
    if len(samples) < policy["estimate_samples"]:
        return dict(policy["default_job"])
    caps = {"five_hour": policy["five_hour_cap"], "week": policy["weekly_cap"]}
    return {w: min(caps[w] / 2, max(policy["min_job"][w], max(s[i] for s in samples)))
            for i, w in enumerate(WINDOWS)}


def status(ledger, reading, policy):
    # A run's reservation shrinks by its share of the use, not by all use while it was active. 2026-10-20: with
    # several runs active each one's "used" grew by everyone's use, the reservations all went to 0, and a third
    # and fourth run started into a window already full: studio use reached 45 of a 26-point cap.
    reserved = {w: sum(max(0.0, r["reserve"][w] - r.get("share", r["used"])[w]) for r in ledger["active"].values())
                for w in WINDOWS}
    studio = {w: ledger["studio"][w].get(reading[w]["key"], 0.0) for w in WINDOWS}
    return {"account": {w: reading[w]["pct"] for w in WINDOWS}, "studio": studio, "reserved": reserved,
            "resets": {w: reading[w]["key"] for w in WINDOWS}, "caps": {"five_hour": policy["five_hour_cap"],
            "week": policy["weekly_cap"]}, "active_runs": len(ledger["active"])}


def week_room(ledger, reading, policy):
    """Points left this week for studio runs: the smaller of the studio's weekly cap and the account's own week,
    keeping Benjamin's personal share and the margin back, as admit() does."""
    s, m = status(ledger, reading, policy), policy["margin"]["week"]
    personal_used = max(0.0, s["account"]["week"] - s["studio"]["week"])
    studio = policy["weekly_cap"] - s["studio"]["week"] - s["reserved"]["week"] - m
    account = 100 - s["account"]["week"] - s["reserved"]["week"] - m - max(0.0, policy["personal_weekly"] - personal_used)
    return min(studio, account)


DAY = 86400


def week_pace(ledger, reading, policy, now, update=True):
    """With policy["week_pace"]: today's share of the week left, as (spent today, today's budget, the day's start),
    or None. The week left is the smaller of the studio's weekly cap and the account's own week, less the margin;
    each day (24 hours from the first reading after the last day ended) gets that, spread over the days to the
    reset, at least one. A day that spends less leaves more for the days after, and the last day gets everything
    left. 2026-10-18: Codex's 5-hour cap of 60 let it spend its whole week in under three days; it was at 78 of
    100 with six days to go, while Claude's smaller 5-hour cap paces its week on its own."""
    if not policy.get("week_pace"):
        return None
    w = reading["week"]
    if w.get("at") is None or w["at"] <= now:
        return None
    s = status(ledger, reading, policy)
    left = min(policy["weekly_cap"] - s["studio"]["week"], 100 - s["account"]["week"]) - policy["margin"]["week"]
    p = ledger.get("pace")
    if not p or p.get("key") != w["key"] or now - p["t"] >= DAY:
        p = {"key": w["key"], "t": now, "left": left,
             "budget": round(max(0.0, left) / max(1.0, (w["at"] - now) / DAY), 3)}
        if update:
            ledger["pace"] = p
    return max(0.0, p["left"] - left), p["budget"], p["t"]


def pace_out(ledger, reading, policy, now):
    """True when today's share of the week (week_pace) has no room for even the smallest run."""
    pace = week_pace(ledger, reading, policy, now, update=False)
    return bool(pace) and pace[0] + policy["min_job"]["week"] > pace[1]


def admit(ledger, reading, agent, pid, policy, now, pid_alive=_pid_alive, run=None):
    """Returns (token, []) when admitted, else (None, reasons). Mutates the ledger either way."""
    _drop_gone(ledger, policy, now, pid_alive)
    observe(ledger, reading, now)
    _drop_ended(ledger, now)
    job = estimate(ledger, agent, policy)
    s = status(ledger, reading, policy)
    m = policy["margin"]
    reasons = []
    limits = {"five_hour": policy["five_hour_cap"] - held_back(policy, agent), "week": policy["weekly_cap"]}
    for w in WINDOWS:
        # Benjamin, 2026-10-16 ("yes quota fill"): with no other run holding points, a run starts in whatever room is
        # left, down to min_job; the wrap-up near the cap ends it. Codex-Builder (estimate 30) sat idle with 29 of 60
        # left, and the Director (estimate 4) was refused at 18 of 22 on 2026-10-15. With runs active the full
        # estimate still counts, so several runs cannot squeeze into the same last points.
        if not s["reserved"][w]:
            room = limits[w] - s["studio"][w] - m[w]
            job = {**job, w: min(job[w], max(policy["min_job"][w], room))}

    def need(label, used, w, limit, extra=0.0):
        total = used + s["reserved"][w] + job[w] + m[w] + extra
        if total > limit:
            reasons.append(f"{label}: used {used:g} + reserved {s['reserved'][w]:g} + this run {job[w]:g} + margin "
                           f"{m[w]:g}{f' + personal {extra:g}' if extra else ''} = {total:g} > {limit:g} "
                           f"(resets {reading[w]['key'] or 'unknown'})")

    need("studio 5-hour", s["studio"]["five_hour"], "five_hour", limits["five_hour"])
    need("studio weekly", s["studio"]["week"], "week", limits["week"])
    need("account 5-hour", s["account"]["five_hour"], "five_hour", 100)
    personal_used = max(0.0, s["account"]["week"] - s["studio"]["week"])
    need("account weekly", s["account"]["week"], "week", 100, max(0.0, policy["personal_weekly"] - personal_used))
    pace = week_pace(ledger, reading, policy, now)
    if pace:
        spent, budget, start = pace
        if spent + s["reserved"]["week"] + policy["min_job"]["week"] > budget:
            reasons.append(f"studio weekly pace: used {spent:g} + reserved {s['reserved']['week']:g} today of today's "
                           f"{budget:g} (the week left spread over the days to its reset at {reading['week']['key']}); "
                           f"the next day starts {time.strftime('%b %d %H:%M', time.localtime(start + DAY))}")
    for model, pct in reading.get("other", {}).items():
        if pct + m["week"] > 100:
            reasons.append(f"{model} weekly limit {pct:g}% used")
    if reasons:
        return None, reasons
    token = uuid.uuid4().hex
    ledger["active"][token] = {"agent": agent, "pid": pid, "t": now, "reserve": job, "run": run,
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
    _finish(ledger, token, now, "released")


def correct(ledger, window, points):
    """Set the studio's attributed use in the current `window` by hand (a repair, logged by the caller).
    Returns (window key, previous value)."""
    last = ledger.get("last") or {}
    if window not in WINDOWS or not last.get(window):
        raise QuotaError(f"no current {window} window to correct")
    key = last[window]["key"]
    before = ledger["studio"][window].get(key, 0.0)
    ledger["studio"][window] = {key: float(points)}
    return key, before


def load_policy(path, provider, override=None, now=None):
    """The provider's policy, with a temporary cap override (see `override`) applied while it lasts."""
    with open(path) as f:
        policy = json.load(f)[provider]
    if override and os.path.exists(override):
        with open(override) as f:
            o = json.load(f)
        t = now if now is not None else time.time()
        # each window carries its own end; "until" is the one-window format written before 2026-10-06
        policy = {**policy, **{k: o[k] for k in ("five_hour_cap", "weekly_cap")
                               if k in o and t < o.get(f"{k}_until", o.get("until", 0))}}
    return policy


def override(window, points, until):
    """A temporary cap, which Benjamin sets for a night of extra work: `points` (at most 100) for `window`
    until the epoch time `until`, after which policy/quota.json applies again with no further step."""
    if window not in WINDOWS:
        raise QuotaError(f"unknown window {window}")
    if not 0 < points <= 100:
        raise QuotaError("a cap is between 0 and 100 points")
    key = {"five_hour": "five_hour_cap", "week": "weekly_cap"}[window]
    return {key: float(points), f"{key}_until": float(until)}


def merge_override(existing, new, now):
    """`new` added to the override already on file, keeping the other window's override while it lasts.
    2026-10-06: overriding both windows in turn kept only the second, so the five-hour cap was back at 22."""
    kept = {}
    for k in ("five_hour_cap", "weekly_cap"):
        end = (existing or {}).get(f"{k}_until", (existing or {}).get("until", 0))
        if k in (existing or {}) and now < end:
            kept.update({k: existing[k], f"{k}_until": end})
    return {**kept, **new}


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
