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
  blocked    an issue is blocked: Benjamin is told once per blocking, with the latest comment's first line.

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

    day = datetime.date.fromtimestamp(now).isoformat()
    for i in issues:
        st, agent = i.get("status"), i.get("assigneeAgentId")
        label = f"{i.get('identifier', i['id'])} \"{short(i.get('title'), 50)}\""
        if st == "blocked":
            out.append(("notify", f"blocked:{i['id']}:{i.get('updatedAt')}", f"{label} is blocked." + (
                f" Latest: {short(i.get('_latest_comment'), 160)}" if i.get("_latest_comment") else "")))
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
                        f"{label} ({name.get(agent, agent)}) has had no progress for {hours} h, after 2 wakes today. Needs a look."))
    return out
