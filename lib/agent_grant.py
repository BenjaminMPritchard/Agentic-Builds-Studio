"""Run grants: which GitHub account one agent run may get App tokens for, and until when.

agent-exec (running as paperclip) creates a grant when a run starts and passes only its random ID to the
confined agent. When the agent's token nears expiry it asks for a fresh one through sudo, naming the grant;
the grant, not the agent, decides the account. Grants live in a directory only paperclip can read and
expire on their own, so a process left behind after a run cannot keep getting tokens.
"""
import json
import os
import re
import secrets
import time

GRANT_DIR = "/srv/studio/data/agent-grants"
DEFAULT_HOURS = 8
ID = re.compile(r"^[0-9a-f]{32}$")
OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


class GrantError(Exception):
    pass


def _path(grant_dir, grant_id):
    if not isinstance(grant_id, str) or not ID.match(grant_id):
        raise GrantError("grant ID is malformed")
    return os.path.join(grant_dir, grant_id + ".json")


def prune(grant_dir=GRANT_DIR, now=time.time):
    try:
        names = os.listdir(grant_dir)
    except FileNotFoundError:
        return
    t = now()
    for name in names:
        p = os.path.join(grant_dir, name)
        try:
            with open(p) as f:
                expired = json.load(f)["expires"] <= t
        except (OSError, ValueError, KeyError, TypeError):
            expired = True  # unreadable or malformed grants are removed too
        if expired:
            try:
                os.remove(p)
            except OSError:
                pass


def create(owner, grant_dir=GRANT_DIR, hours=DEFAULT_HOURS, now=time.time):
    if not isinstance(owner, str) or not OWNER.match(owner):
        raise GrantError("owner must be a GitHub user or organisation name")
    os.makedirs(grant_dir, mode=0o700, exist_ok=True)
    os.chmod(grant_dir, 0o700)
    prune(grant_dir, now)
    grant_id = secrets.token_hex(16)
    fd = os.open(_path(grant_dir, grant_id), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"owner": owner, "expires": now() + hours * 3600}, f)
    return grant_id


def resolve(grant_id, grant_dir=GRANT_DIR, now=time.time):
    """The account a live grant names; GrantError if the grant is unknown, malformed or expired."""
    try:
        with open(_path(grant_dir, grant_id)) as f:
            g = json.load(f)
    except FileNotFoundError:
        raise GrantError("grant is unknown or has been removed") from None
    except (OSError, ValueError) as e:
        raise GrantError(f"grant is unreadable: {type(e).__name__}") from None
    if not (isinstance(g, dict) and isinstance(g.get("owner"), str) and isinstance(g.get("expires"), (int, float))):
        raise GrantError("grant is malformed")
    if g["expires"] <= now():
        raise GrantError("grant has expired")
    return g["owner"]
