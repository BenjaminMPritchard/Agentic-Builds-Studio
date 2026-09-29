"""Stage the files Paperclip gives the Claude CLI where the confined agent user can read them.

The claude_local adapter writes the agent's instructions, its prompt bundle (skills, as symlinks into
Paperclip's home) and any MCP config under Paperclip's home, then passes their paths as
--append-system-prompt-file, --add-dir and --mcp-config. The CLI runs as studio-agent, which cannot read
Paperclip's home, so agent-exec (still running as paperclip) copies them into a per-run folder and rewrites
those arguments. Symlinks are copied as their targets.

The per-run folders live under a parent that only paperclip can write (/srv/studio/data/agent-runs, group
studio, mode 2750), so an agent cannot plant links there to make paperclip write elsewhere. Each folder is
named after the agent-exec process (run-<pid>-...) and removed once that process is gone: when the run ends
(agent-exec's watcher runs `agent-stage --prune`) or at the next run's staging. The MCP config can hold the
run's Paperclip key, so it should not outlive the run. Anything older than a day is removed regardless.
"""
import grp
import os
import pwd
import re
import shutil
import stat
import subprocess
import tempfile
import time

STAGE_DIR = "/srv/studio/data/agent-runs"
# Where the Paperclip server makes run scratch folders (its os.tmpdir()). Not tempfile.gettempdir(): inside a run
# TMPDIR is the scratch folder itself.
SCRATCH_ROOT = "/tmp"
KEEP_SECONDS = 24 * 3600
GRACE_SECONDS = 60  # a folder is never removed in the minute after it was made, while its run is starting
RUN_DIR = re.compile(r"^run-(\d+)-")
FILE_FLAGS = ("--append-system-prompt-file", "--mcp-config")
DIR_FLAGS = ("--add-dir",)


class StageError(Exception):
    pass


def _check_parent(parent, group_gid):
    os.makedirs(parent, mode=0o750, exist_ok=True)
    st = os.lstat(parent)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid():
        raise StageError(f"{parent} must be a directory owned by the running user")
    if group_gid is not None and st.st_gid != group_gid:
        os.chown(parent, -1, group_gid)
    os.chmod(parent, 0o2750)


def _alive(pid):
    return os.path.exists(f"/proc/{pid}")


def prune(parent, now=time.time, alive=_alive):
    """Remove run folders whose agent-exec process is gone, and anything older than a day."""
    try:
        names = os.listdir(parent)
    except OSError:
        return
    for name in names:
        p = os.path.join(parent, name)
        try:
            age = now() - os.lstat(p).st_mtime
            m = RUN_DIR.match(name)
            if age > KEEP_SECONDS or (m and age > GRACE_SECONDS and not alive(int(m.group(1)))):
                shutil.rmtree(p) if os.path.isdir(p) and not os.path.islink(p) else os.remove(p)
        except OSError:
            pass


def _readable_tree(root):
    for d, dirs, files in os.walk(root):
        os.chmod(d, 0o750)
        for f in files:
            os.chmod(os.path.join(d, f), 0o640)


def share_scratch(path, group, tmp_root=None):
    """Let the agent group use Paperclip's per-run scratch folder (TMPDIR, TEMP, TMP), which Paperclip creates
    as mode 0700 under /tmp and removes after the run. Only that folder: it must be a real directory directly
    under the temp root, named paperclip-run-*, and owned by the running user."""
    if not path:
        return
    root = os.path.realpath(tmp_root or SCRATCH_ROOT)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise StageError(f"run scratch folder {path} does not exist") from None
    if (os.path.dirname(os.path.abspath(path)) != root or not os.path.basename(path).startswith("paperclip-run-")
            or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.geteuid()):
        raise StageError(f"{path} is not this run's Paperclip scratch folder")
    try:
        gid = grp.getgrnam(group).gr_gid
    except KeyError:
        raise StageError(f"group {group} does not exist") from None
    os.chown(path, -1, gid)
    os.chmod(path, 0o2770)
    # Default ACL: everything the agent creates inside stays removable by the running user, so Paperclip's own
    # clean-up after the run works (without it the agent's subfolders are left behind in /tmp).
    me = pwd.getpwuid(os.geteuid()).pw_name
    r = subprocess.run(["setfacl", "-d", "-m", f"u:{me}:rwx,g:{group}:rwx,m:rwx", path], capture_output=True, text=True)
    if r.returncode:
        raise StageError(f"cannot set the default ACL on {path}: {r.stderr.strip()[:200]}")


def stage(args, parent=STAGE_DIR, group=None, now=time.time, owner_pid=None):
    """Return args with the Paperclip-provided file and folder paths replaced by copies the agent can read.
    `group` (a name) is the agent user's group, which gets read access; None leaves the group alone."""
    if not any(a in FILE_FLAGS + DIR_FLAGS for a in args):
        return list(args)
    try:
        group_gid = grp.getgrnam(group).gr_gid if group else None
    except KeyError:
        raise StageError(f"group {group} does not exist") from None
    _check_parent(parent, group_gid)
    prune(parent, now)
    # agent-stage runs as a child of agent-exec, whose process (later sudo) lasts as long as the run.
    run_dir = tempfile.mkdtemp(prefix=f"run-{owner_pid or os.getppid()}-", dir=parent)
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in FILE_FLAGS + DIR_FLAGS and i + 1 < len(args):
            src = args[i + 1]
            dst = os.path.join(run_dir, f"{len(out)}-{os.path.basename(src.rstrip('/')) or 'x'}")
            try:
                if a in DIR_FLAGS:
                    shutil.copytree(src, dst, symlinks=False, ignore_dangling_symlinks=True)
                else:
                    shutil.copyfile(src, dst)
            except OSError as e:
                raise StageError(f"cannot stage {a} {src}: {e.strerror or e}") from None
            out += [a, dst]
            i += 2
            continue
        out.append(a)
        i += 1
    _readable_tree(run_dir)  # the parent is setgid, so everything in it already has the agent group
    return out
