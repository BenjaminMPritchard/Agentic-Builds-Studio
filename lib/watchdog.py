"""The watchdog: finds stuck work, retries it once, then tells Benjamin in one line (Clerk step, no LLM).

Benjamin, 2026-10-02: agents kept dying, getting stuck or freezing, and nobody noticed until he looked. Each rule
below retries first and escalates only when the retry did not help. Every action has a receipt key, so a
problem is acted on and reported once, not on every tick.

  failed     an agent's latest run failed (not a usage-cap refusal: resume_capped wakes those). Retried once on the
             same issue 10 minutes later; if it fails again the same way, Benjamin is told.
  silent     a run has written nothing for 30 minutes: Benjamin is told. At 60 minutes it is cancelled and the
             agent woken again on the same issue.
  idle       an issue is todo or in progress, its agent is idle and nothing has happened for 2 hours: the agent is
             woken on it, at most twice a day; after that Benjamin is told.
  blocked    an issue is blocked: Benjamin is told once per blocking, in plain words. A block caused by the usage
             cap is not reported on its own: the "paused" notice covers it.

Benjamin, 2026-10-02: "I just want my notifications to actually tell me what's going on." So the watchdog also
reports what the Studio as a whole is doing, not only single issues:

  paused     an agent's run was refused by the usage cap: once per pause, which budget ran out, what work is saved
             and waiting, and when it carries on.
  running    the first run after a pause: who is working on what again.
  finished   an issue was marked done.

Nothing is woken during quiet hours (lib/notify.QUIET): work runs while Benjamin is awake.
"""
import datetime
import re

RETRY_AFTER = 10 * 60
SILENT_NOTIFY = 30 * 60
SILENT_CANCEL = 60 * 60
IDLE_AFTER = 2 * 3600
IDLE_WAKES_PER_DAY = 2
CAP_REFUSED = re.compile(r"studio-quota: \w+ cap reached")
CAP_DETAIL = re.compile(r"studio (5-hour|week): used ([\d.]+) .*?> ([\d.]+)")
RESETS = re.compile(r"resets (?:\w+ \d+, )?([^()]+?)\s*\(")
# Paperclip's own status comments, in plain words for the notice (Benjamin, 2026-10-02: "a bit more readable").
PLAIN = [
    (re.compile(r"disposition", re.I), "Its run ended without handing the work on (to review, done or blocked)"),
    (re.compile(r"environment lease", re.I), "The last run's clean-up has not finished"),
    (re.compile(r"no live execution path", re.I), "Nothing is scheduled to carry it on"),
]


def epoch(iso):
    try:
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return None


def signature(run):
    """The kind of failure, without the numbers that change between attempts."""
    return (run.get("errorCode") or "") + ":" + re.sub(r"[\d.]+", "#", (run.get("error") or "")[:100])


def short(text, n=140):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def plain(comment):
    """Paperclip's status comment in plain words, or None when it is not one of Paperclip's."""
    for pattern, text in PLAIN:
        if pattern.search(comment or ""):
            return text
    return None


def heading(issue, who, n=70):
    """"AGE-28 Production settings for Render staging, Builder-1": the plan's numbering ("8s-1: ") left out."""
    title = re.sub(r"^\s*[\w.-]{1,8}:\s+", "", issue.get("title") or "")
    return f"{issue.get('identifier', issue['id'])} {short(title, n)}" + (f", {who}" if who else "")


def situation(latest, capped, name, issues, watch, workers):
    """What the Studio as a whole is doing: paused by the usage cap, running again, tasks finished."""
    out = []
    open_by_agent = {}
    for i in issues:
        if i.get("status") in ("todo", "in_progress", "blocked") and i.get("assigneeAgentId"):
            open_by_agent.setdefault(i["assigneeAgentId"], []).append(i)
    by_id = {i["id"]: i for i in issues}

    def doing(agent, run=None):
        issue = by_id.get(((run or {}).get("contextSnapshot") or {}).get("issueId")) or (open_by_agent.get(agent) or [None])[0]
        return heading(issue, name.get(agent, agent), 45) if issue else name.get(agent, agent)

    pause = watch.get("paused")
    if isinstance(pause, str):  # the first version kept only the run id
        pause = watch["paused"] = {"run": pause, "since": "", "reset": None}
    if capped:
        first = latest[sorted(capped)[0]]
        detail, reset = CAP_DETAIL.search(first.get("error") or ""), RESETS.search(first.get("error") or "")
        when = reset.group(1) if reset else None
        # A new pause, not the same one seen again: none is open, or the open one began a whole window ago and
        # no run went through since (the reset time itself moves by a minute between readings, 2026-10-03).
        since = epoch(pause.get("since")) if pause else None
        if not pause or (since and (epoch(first.get("createdAt")) or 0) - since >= 5 * 3600):
            budget = "this week's" if detail and detail.group(1) == "week" else "this 5-hour"
            used = f" ({detail.group(2)} of {detail.group(3)} points)" if detail else ""
            waiting = "; ".join(doing(a, latest[a]) for a in sorted(capped, key=lambda a: name.get(a, a)))
            watch["paused"] = {"run": first["id"], "since": first.get("createdAt", ""), "reset": when}
            out.append(("notify", f"paused:{first['id']}",
                        f"Studio paused: {budget} usage budget is used up{used}. Work is saved and waiting: {waiting}. "
                        f"It carries on by itself after {when or 'the budget resets'}. Nothing for you to do."))
    elif pause:
        # Running again means an agent's run was let through after the pause began; the Clerk's own runs and
        # failures for other reasons are not that (2026-10-03: "running again" was sent while still capped).
        busy = sorted((a for a, r in latest.items() if a in workers and r.get("status") in ("running", "succeeded")
                       and r.get("createdAt", "") > pause.get("since", "")), key=lambda a: name.get(a, a))
        if busy:
            del watch["paused"]
            out.append(("notify", f"running:{pause['run']}",
                        "Studio running again after the usage cap: " + "; ".join(doing(a, latest[a]) for a in busy) + "."))

    done = {i["id"] for i in issues if i.get("status") == "done"}
    if "done_seen" not in watch:  # first tick: what was already done is not news
        watch["done_seen"] = sorted(done)
    else:
        seen = set(watch["done_seen"])
        for i in issues:
            if i["id"] in done and i["id"] not in seen:
                who = name.get(i.get("assigneeAgentId"), "") if i.get("assigneeAgentId") else ""
                out.append(("notify", f"finished:{i['id']}", f"Finished: {heading(i, who)}."))
        watch["done_seen"] = sorted(done)
    return out


def plan(now, agents, runs, issues, watch, quiet=False):
    """Actions for this tick, each (kind, key, ...): ("wake", key, agent_id, issue_id, reason),
    ("cancel", key, run_id), ("notify", key, text). `watch` is the Clerk's saved watchdog state; it is updated."""
    out = []
    name = {a["id"]: a.get("name", a["id"]) for a in agents}
    status = {a["id"]: a.get("status") for a in agents}
    ident = {i["id"]: i.get("identifier", i["id"]) for i in issues}
    latest = {}
    for r in runs:
        if r.get("createdAt", "") > latest.get(r["agentId"], {}).get("createdAt", ""):
            latest[r["agentId"]] = r
    fails = watch.setdefault("fails", {})

    for agent, r in latest.items():
        issue = (r.get("contextSnapshot") or {}).get("issueId")
        where = f" on {ident.get(issue, issue)}" if issue else ""
        who = name.get(agent, agent)
        if status.get(agent) == "paused":
            continue
        if r.get("status") == "succeeded":
            fails.pop(agent, None)
        elif r.get("status") == "failed" and not CAP_REFUSED.search(r.get("error") or ""):
            sig, ended = signature(r), epoch(r.get("finishedAt") or r.get("createdAt")) or now
            seen = fails.get(agent)
            if seen and seen["sig"] == sig and seen["run"] != r["id"]:
                out.append(("notify", f"failed-twice:{agent}:{sig}",
                            f"{who} failed twice{where}: {short(r.get('error'))}. Retried once; needs a look."))
            elif not seen or seen["sig"] != sig:
                if now - ended >= RETRY_AFTER and not quiet:
                    fails[agent] = {"sig": sig, "run": r["id"]}
                    out.append(("wake", f"retry:{r['id']}", agent, issue, f"Your last run failed ({short(r.get('error'), 80)}); trying once more"))
        elif r.get("status") == "running":
            last = epoch(r.get("lastOutputAt") or r.get("startedAt") or r.get("createdAt")) or now
            silent = now - last
            if silent >= SILENT_CANCEL:
                out.append(("cancel", f"cancel:{r['id']}", r["id"]))
                out.append(("notify", f"cancelled:{r['id']}",
                            f"{who} wrote nothing for {int(silent / 60)} min{where}; run cancelled and retried."))
                if not quiet:
                    out.append(("wake", f"after-cancel:{r['id']}", agent, issue, "Your last run froze and was cancelled; carry on from your commits and notes"))
            elif silent >= SILENT_NOTIFY:
                out.append(("notify", f"silent:{r['id']}",
                            f"{who} has written nothing for {int(silent / 60)} min{where}. Cancelled and retried at 60 min if still silent."))

    capped = {a for a, r in latest.items() if r.get("status") == "failed" and CAP_REFUSED.search(r.get("error") or "")
              and status.get(a) != "paused"}
    workers = {a["id"] for a in agents if a.get("adapterType") != "process"}  # not the Clerk or other scripts
    out.extend(situation(latest, capped, name, issues, watch, workers))

    day = datetime.date.fromtimestamp(now).isoformat()
    for i in issues:
        st, agent = i.get("status"), i.get("assigneeAgentId")
        head = heading(i, name.get(agent, agent) if agent else None)
        if st == "blocked":
            if agent in capped:
                continue  # the "paused" notice covers it
            why, said = plain(i.get("_latest_comment")), i.get("_latest_comment")
            text = f"{head}: stuck. {why}. Needs a look." if why else \
                f"{head}: blocked." + (f" Latest: {short(said, 160)}" if said else "")
            out.append(("notify", f"blocked:{i['id']}:{i.get('updatedAt')}", text))
            continue
        if st not in ("todo", "in_progress") or not agent or status.get(agent) != "idle":
            continue
        last_run = epoch((latest.get(agent) or {}).get("createdAt")) or 0
        updated = epoch(i.get("updatedAt")) or 0
        if now - max(last_run, updated) < IDLE_AFTER:
            continue
        hours = int((now - max(last_run, updated)) / 3600)
        wakes = watch.setdefault("idle", {}).setdefault(i["id"], {})
        if wakes.get("day") != day:
            wakes.clear()
            wakes.update(day=day, n=0)
        if wakes["n"] < IDLE_WAKES_PER_DAY:
            if not quiet:
                wakes["n"] += 1
                out.append(("wake", f"idle:{i['id']}:{day}:{wakes['n']}", agent, i["id"],
                            f"Nothing has happened on this issue for {hours} h; carry on with it"))
        else:
            out.append(("notify", f"idle:{i['id']}:{day}",
                        f"{head}: no progress for {hours} h, after 2 wakes today. Needs a look."))
    return out
