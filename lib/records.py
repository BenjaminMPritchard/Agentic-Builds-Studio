"""The Clerk's efficiency records (research section 11): deterministic, append-only, no model calls.

collect() turns finished Paperclip runs into one record each (identity, runtime, timing, outcome, tokens as
the provider reported them) and joins the usage-cap controller's record for the same run (studio points used
in each window, attributed as a bound). Records are appended to records/runs.jsonl and never rewritten; a
run id already recorded is skipped. report() summarises them per agent. Claude and Codex usage stay in separate
columns and are never added together; API-equivalent cost is an estimate, not money spent.
"""
import json
import os
import statistics
import time

TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "error"}
TOKEN_FIELDS = ("inputTokens", "cachedInputTokens", "cacheCreationInputTokens", "outputTokens", "rawInputTokens")


def _ts(iso):
    if not iso:
        return None
    try:
        return time.mktime(time.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except ValueError:
        return None


def load_jsonl(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass  # a torn last line is skipped, never repaired in place
    except FileNotFoundError:
        pass
    return out


def usage_by_run(quota_dir):
    """{run id: (provider, usage record)} from the controller's <provider>-runs.jsonl files."""
    out = {}
    for provider in ("claude", "codex"):
        for rec in load_jsonl(os.path.join(quota_dir, f"{provider}-runs.jsonl")):
            if rec.get("run"):
                out[rec["run"]] = (provider, rec)
    return out


def record(run, agent_names, usage):
    u = run.get("usageJson") or {}
    ctx = run.get("contextSnapshot") or {}
    rec = {
        "run": run["id"], "agent_id": run.get("agentId"), "agent": agent_names.get(run.get("agentId"), "?"),
        "issue": ctx.get("issueId"), "wake": ctx.get("wakeReason"), "status": run.get("status"),
        "error_code": run.get("errorCode"), "exit_code": run.get("exitCode"),
        "created_at": run.get("createdAt"), "started_at": run.get("startedAt"), "finished_at": run.get("finishedAt"),
        "model": u.get("model"), "provider": u.get("provider"), "billing": u.get("billingType"),
        "cost_status": u.get("costStatus"), "api_equivalent_usd": u.get("costUsd"),
        "fresh_session": u.get("freshSession"),
        "tokens": {k: u[k] for k in TOKEN_FIELDS if isinstance(u.get(k), (int, float))},
        "studio_usage": None,
    }
    if run["id"] in usage:
        provider, q = usage[run["id"]]
        rec["studio_usage"] = {"provider": provider, "five_hour": q["used"]["five_hour"], "week": q["used"]["week"],
                               "attribution": q.get("attribution"), "ended": q.get("ended"),
                               "windows": q.get("windows")}
    return rec


def _ends_with_newline(path):
    with open(path, "rb") as f:
        f.seek(-1, os.SEEK_END)
        return f.read(1) == b"\n"


def collect(runs, agent_names, usage, records_path):
    """Append a record for every finished run not yet recorded. Returns the number appended."""
    seen = {r["run"] for r in load_jsonl(records_path)}
    new = [record(r, agent_names, usage) for r in sorted(runs, key=lambda r: r.get("createdAt") or "")
           if r.get("status") in TERMINAL and r["id"] not in seen]
    if new:
        os.makedirs(os.path.dirname(records_path), exist_ok=True)
        torn = os.path.exists(records_path) and os.path.getsize(records_path) and not _ends_with_newline(records_path)
        with open(records_path, "a") as f:
            if torn:
                f.write("\n")  # never glue a new record onto a torn line
            for rec in new:
                f.write(json.dumps(rec) + "\n")
    return len(new)


def _pct(values, q):
    values = sorted(values)
    if not values:
        return None
    return values[min(len(values) - 1, int(round(q * (len(values) - 1))))]


def _fmt(x, unit=""):
    return "–" if x is None else f"{x:g}{unit}"


def report(records, issues_by_id=None, now=None):
    issues_by_id = issues_by_id or {}
    lines = ["# Studio efficiency records", f"_generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(now or time.time()))}; "
             f"{len(records)} finished runs_", "",
             "Deterministic summary of `records/runs.jsonl` (research 11). Studio usage is the usage-cap controller's "
             "bounded attribution in percentage points of each provider's own window; Claude and Codex are separate "
             "columns and are never added. API-equivalent cost is Paperclip's estimate, not money spent. Runs admitted "
             "before per-run usage records existed have no usage figures.", ""]
    by_agent = {}
    for r in records:
        by_agent.setdefault(r["agent"], []).append(r)
    lines += ["| Agent | Model | Runs | Succeeded / failed / cancelled | Duration median / p90 (min) "
              "| Claude points per run, 5h / week (median) | Codex points per run, 5h / week (median) "
              "| Output tokens median | Issues done / in review / other |",
              "| --- | --- | ---: | --- | --- | --- | --- | ---: | --- |"]
    for agent in sorted(by_agent):
        rs = by_agent[agent]
        models = sorted({r.get("model") or "–" for r in rs})
        counts = {s: sum(r["status"] == s for r in rs) for s in ("succeeded", "failed", "cancelled")}
        durations = [(_ts(r["finished_at"]) - _ts(r["started_at"])) / 60 for r in rs
                     if _ts(r.get("finished_at")) and _ts(r.get("started_at"))]
        cols = []
        for provider in ("claude", "codex"):
            u = [r["studio_usage"] for r in rs if (r.get("studio_usage") or {}).get("provider") == provider]
            cols.append("–" if not u else f"{statistics.median(x['five_hour'] for x in u):g} / "
                                          f"{statistics.median(x['week'] for x in u):g} (n={len(u)})")
        out_tokens = [r["tokens"]["outputTokens"] for r in rs if "outputTokens" in (r.get("tokens") or {})]
        issue_ids = {r["issue"] for r in rs if r.get("issue")}
        states = [issues_by_id.get(i, {}).get("status") for i in issue_ids]
        med = _fmt(round(statistics.median(durations), 1)) if durations else "–"
        p90 = _fmt(round(_pct(durations, 0.9), 1)) if durations else "–"
        lines.append(f"| {agent} | {', '.join(models)} | {len(rs)} | {counts['succeeded']} / {counts['failed']} / "
                     f"{counts['cancelled']} | {med} / {p90} | {cols[0]} | {cols[1]} | "
                     f"{_fmt(statistics.median(out_tokens)) if out_tokens else '–'} | "
                     f"{states.count('done')} / {states.count('in_review')} / "
                     f"{len(states) - states.count('done') - states.count('in_review')} |")
    lines += ["", "**Not measured yet** (research 11.1–11.3): first-pass acceptance and rework share (need review "
              "outcomes per work package), human intervention minutes, queue and response latency against targets, "
              "local energy. Issue states above are where each issue stands now, not proof of acceptance."]
    return "\n".join(lines) + "\n"
