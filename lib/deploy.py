"""Keep the deployed copy (/srv/studio/company) in step with `main` on GitHub.

Safe by construction: fast-forward only, never over local edits, and the test suite must pass on the new
commit (in a throwaway worktree) before the live copy moves. A failing commit is reported once, not retried.
"""
import os
import shutil
import subprocess
import sys
import tempfile

TEST_CMD = [sys.executable, "-W", "ignore", "-m", "unittest", "discover", "-s", "tests", "-t", "."]


def git(repo, *args, timeout=120):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def sync(repo, branch="main", test_cmd=None, skip_sha=None, fetch_timeout=60, test_timeout=180):
    """Returns {"status": current|updated|dirty|diverged|tests_failed|fetch_failed, ...}."""
    rc, _, err = git(repo, "fetch", "--quiet", "origin", branch, timeout=fetch_timeout)
    if rc:
        return {"status": "fetch_failed", "detail": err[:200]}
    _, local, _ = git(repo, "rev-parse", "HEAD")
    _, remote, _ = git(repo, "rev-parse", f"origin/{branch}")
    if local == remote:
        return {"status": "current", "sha": local}
    if skip_sha == remote:  # already reported as failing; wait for a newer commit
        return {"status": "tests_failed", "sha": remote, "detail": "known failing commit", "repeat": True}
    if git(repo, "status", "--porcelain")[1]:
        return {"status": "dirty", "sha": remote, "detail": "uncommitted changes in the deployed copy"}
    if git(repo, "merge-base", "--is-ancestor", local, remote)[0]:
        return {"status": "diverged", "sha": remote, "detail": "deployed copy is not an ancestor of origin"}
    tmp = tempfile.mkdtemp(prefix="studio-deploy-")
    try:
        if git(repo, "worktree", "add", "--detach", "--quiet", tmp, remote)[0]:
            return {"status": "fetch_failed", "detail": "could not check out the new commit"}
        r = subprocess.run(test_cmd or TEST_CMD, cwd=tmp, capture_output=True, text=True, timeout=test_timeout)
        if r.returncode:
            return {"status": "tests_failed", "sha": remote, "detail": (r.stdout + r.stderr)[-400:]}
    finally:
        git(repo, "worktree", "remove", "--force", tmp)
        shutil.rmtree(tmp, ignore_errors=True)
    changed = git(repo, "diff", "--name-only", local, remote)[1].splitlines()
    rc, _, err = git(repo, "merge", "--ff-only", "--quiet", f"origin/{branch}")
    if rc:
        return {"status": "diverged", "sha": remote, "detail": err[:200]}
    return {"status": "updated", "sha": remote, "from": local, "changed": changed}
