"""One-line notices to Benjamin about stuck work (lib/watchdog.py) and PRs ready for his merge (lib/merge_gate.py).

Every notice is logged to <data>/log/notify.jsonl and listed in the Clerk's digest. When /etc/studio/notify.json
names a channel, it is also pushed there:

  {"ntfy_url": "https://<host>/<topic>", "token_file": "/etc/studio/ntfy-token"}   # token_file optional

During quiet hours (22:00-07:00 local) notices are held, then sent together as one message by the first Clerk
tick after them (`flush`).
A notice is text only: no secrets, keys or customer data, because it leaves the machine.
"""
import json
import os
import time
import urllib.request

CONFIG = os.environ.get("STUDIO_NOTIFY_CONFIG", "/etc/studio/notify.json")
QUIET = (22, 7)  # local hours: from 22:00 until 07:00


def quiet(now):
    h = time.localtime(now).tm_hour
    return h >= QUIET[0] or h < QUIET[1]


def _config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _push(cfg, text):
    headers = {"Title": "Agentic Studio", "Tags": "warning"}
    if cfg.get("token_file"):
        with open(cfg["token_file"]) as f:
            headers["Authorization"] = "Bearer " + f.read().strip()
    req = urllib.request.Request(cfg["ntfy_url"], data=text.encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return 200 <= r.status < 300


def send(data_dir, text, now=None, config=None, push=_push):
    """Log a notice and push it (or hold it during quiet hours). Returns "sent", "held", "logged" or "failed"."""
    now = time.time() if now is None else now
    log_dir = os.path.join(data_dir, "log")
    os.makedirs(log_dir, exist_ok=True)
    held_path = os.path.join(data_dir, "notify-held.json")
    cfg = _config(config or CONFIG)
    outcome = "logged"
    if cfg and cfg.get("ntfy_url"):
        held = _config(held_path) or []
        if quiet(now):
            held.append(text)
            outcome = "held"
        else:
            body = "\n".join(["Overnight:"] + [f"- {t}" for t in held] + [f"- {text}"]) if held else text
            try:
                outcome = "sent" if push(cfg, body) else "failed"
            except Exception:  # a channel that is down must not stop the Clerk; the log and digest still have it
                outcome = "failed"
            if outcome == "sent":
                held = []
        with open(held_path, "w") as f:
            json.dump(held, f)
    with open(os.path.join(log_dir, "notify.jsonl"), "a") as f:
        f.write(json.dumps({"ts": int(now), "text": text, "outcome": outcome}) + "\n")
    return outcome


def flush(data_dir, now=None, config=None, push=_push):
    """Send the notices held overnight as one message, once quiet hours are over."""
    now = time.time() if now is None else now
    held_path = os.path.join(data_dir, "notify-held.json")
    held, cfg = _config(held_path) or [], _config(config or CONFIG)
    if not held or quiet(now) or not (cfg and cfg.get("ntfy_url")):
        return False
    try:
        ok = push(cfg, "\n".join(["Overnight:"] + [f"- {t}" for t in held]))
    except Exception:
        return False
    if ok:
        with open(held_path, "w") as f:
            json.dump([], f)
    return ok
