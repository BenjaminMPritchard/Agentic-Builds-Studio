"""Notices to Benjamin. Every notice is logged to <data>/log/notify.jsonl; the Clerk's digest lists them too.

Only three kinds reach his phone (Benjamin, 2026-10-12): a PR waiting for his merge, a decision only he can make
(a human-only Paperclip card) and "the Studio is down". Callers pass `phone=True` for those, with a short `title`
and, when there is one, a `click` link. Everything else (usage-cap pauses, retries, blocked or finished work) is
logged only. Phone notices are sent at once, day or night. When /etc/studio/notify.json names a channel they are
pushed there:

  {"ntfy_url": "https://<host>/<topic>", "token_file": "/etc/studio/ntfy-token"}   # token_file optional

A phone notice that could not be sent is kept and retried by the next Clerk tick (`flush`).
A notice is text only: no secrets, keys or customer data, because it leaves the machine.
"""
import json
import os
import time
import urllib.request

CONFIG = os.environ.get("STUDIO_NOTIFY_CONFIG", "/etc/studio/notify.json")
QUIET = (22, 7)  # local hours, 22:00-07:00: the watchdog wakes no agent then. Phone notices still go at once.
MAX_BYTES = 3800  # ntfy refuses a message over 4,096 bytes
MAX_HELD = 60


def quiet(now):
    h = time.localtime(now).tm_hour
    return h >= QUIET[0] or h < QUIET[1]


def _config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def link(path, config=None):
    """A Paperclip page for a notice's tap, when notify.json names `paperclip_url` (reachable from the phone)."""
    base = (_config(config or CONFIG) or {}).get("paperclip_url")
    return base.rstrip("/") + path if base else None


def _push(cfg, text, title="Agentic Studio", click=None):
    headers = {"Title": title.encode("ascii", "ignore").decode(), "Tags": "bell"}  # HTTP headers are ASCII
    if click:
        headers["Click"] = click
    if cfg.get("token_file"):
        with open(cfg["token_file"]) as f:
            headers["Authorization"] = "Bearer " + f.read().strip()
    req = urllib.request.Request(cfg["ntfy_url"], data=text.encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return 200 <= r.status < 300


def _log(data_dir, now, text, outcome, title=None):
    log_dir = os.path.join(data_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    rec = {"ts": int(now), "text": text, "outcome": outcome, **({"title": title} if title else {})}
    with open(os.path.join(log_dir, "notify.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


def _try(cfg, push, notice):
    try:
        return bool(push(cfg, notice["text"][:MAX_BYTES], notice.get("title") or "Agentic Studio", notice.get("click")))
    except Exception:  # a channel that is down must not stop the Clerk; the log and digest still have it
        return False


def send(data_dir, text, now=None, config=None, push=_push, phone=False, title=None, click=None):
    """Log a notice; with phone=True also push it now. Returns "sent", "failed" (kept for retry) or "logged"."""
    now = time.time() if now is None else now
    cfg = _config(config or CONFIG)
    outcome = "logged"
    if phone and cfg and cfg.get("ntfy_url"):
        notice = {"text": text, "title": title, "click": click}
        outcome = "sent" if _try(cfg, push, notice) else "failed"
        if outcome == "failed":
            held_path = os.path.join(data_dir, "notify-held.json")
            held = [h for h in (_config(held_path) or []) if isinstance(h, dict)]
            with open(held_path, "w") as f:
                json.dump((held + [notice])[-MAX_HELD:], f)
    _log(data_dir, now, text, outcome, title)
    return outcome


def flush(data_dir, now=None, config=None, push=_push):
    """Retry phone notices that could not be sent. Returns True when nothing is left waiting."""
    held_path = os.path.join(data_dir, "notify-held.json")
    held = [h for h in (_config(held_path) or []) if isinstance(h, dict)]  # old plain-text entries were log-only
    cfg = _config(config or CONFIG)
    if not (cfg and cfg.get("ntfy_url")):
        return not held
    left = [h for h in held if not _try(cfg, push, h)]
    with open(held_path, "w") as f:
        json.dump(left, f)
    return not left
