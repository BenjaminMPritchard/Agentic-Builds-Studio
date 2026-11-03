"""Keep the Studio Clerk's Paperclip permissions to what it needs (playbook/paperclip-auth.md).

The Clerk is a company operator so it can comment on, change and wake other agents' tasks. Its only grant is
`tasks:assign`. Paperclip 2026.1023.0 gives the operator role thirteen more by default (agents:create,
agents:configure, users:invite, tools:admin, ...) and inserts any that are missing at every start
(`backfillPrincipalAccessCompatibility`), so removing them through the API lasts only until the next restart.
This runs after each start, as `paperclip`, and deletes every Clerk grant except `tasks:assign` from the
embedded database. It touches no other member and no other table.
"""
import json
import re
import subprocess
import time
import urllib.request

CLERK_USER = "0qyW7iqrDqpMFNaBuOd9rM5n7TdYAdR1"  # Studio Clerk (it@benjaminmpritchard.com), operator
COMPANY = "bcf0f336-0c20-4194-9e21-fac517979ba0"
KEEP = ("tasks:assign",)
DB = "postgres://paperclip:paperclip@127.0.0.1:54329/paperclip"  # Paperclip's embedded Postgres; a fixed login
HEALTH = "http://127.0.0.1:3100/api/health"

_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
_KEY = re.compile(r"^[a-z_]+:[a-z_]+$")


def trim_sql(user=CLERK_USER, company=COMPANY, keep=KEEP):
    """The DELETE, with every value checked first: they are written into SQL text for psql."""
    if not (_ID.match(user) and _ID.match(company)) or not keep or not all(_KEY.match(k) for k in keep):
        raise ValueError("refusing an unexpected user, company or permission key")
    kept = ", ".join(f"'{k}'" for k in keep)
    return ("DELETE FROM principal_permission_grants WHERE principal_type = 'user' "
            f"AND principal_id = '{user}' AND company_id = '{company}' AND permission_key NOT IN ({kept}) "
            "RETURNING permission_key;")


def wait_healthy(timeout=240, step=5, url=HEALTH, opener=urllib.request.urlopen, sleep=time.sleep):
    """True once Paperclip answers status ok (its start-up backfill has run by then); False on timeout."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with opener(url, timeout=5) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return False
        sleep(step)


def trim(psql="psql", db=DB, run=subprocess.run):
    """Delete the extra grants; returns the permission keys removed (empty when there were none)."""
    r = run([psql, db, "-v", "ON_ERROR_STOP=1", "-Atqc", trim_sql()], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"psql exited {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}")
    return sorted(line for line in r.stdout.split() if line)
