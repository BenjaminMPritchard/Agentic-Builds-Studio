"""Stage the files Paperclip gives the Claude CLI where the confined agent user can read them.

The claude_local adapter writes the agent's instructions, its prompt bundle (skills, as symlinks into
Paperclip's home) and any MCP config under Paperclip's home, then passes their paths as
--append-system-prompt-file, --add-dir and --mcp-config. The CLI runs as studio-agent, which cannot read
Paperclip's home, so agent-exec (still running as paperclip) copies them into a per-run folder and rewrites
those arguments. Symlinks are copied as their targets.

The per-run folders live under a parent that only paperclip can write (/srv/studio/data/agent-runs, group
studio, mode 2750), so an agent cannot plant links there to make paperclip write elsewhere. Folders older
than a day are removed when a run starts.
"""
import grp
import os
import shutil
import stat
import tempfile
import time

STAGE_DIR = "/srv/studio/data/agent-runs"
KEEP_SECONDS = 24 * 3600
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


def prune(parent, now=time.time):
    try:
        names = os.listdir(parent)
    except FileNotFoundError:
        return
    for name in names:
        p = os.path.join(parent, name)
        try:
            if os.lstat(p).st_mtime < now() - KEEP_SECONDS:
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
    root = os.path.realpath(tmp_root or tempfile.gettempdir())
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


def stage(args, parent=STAGE_DIR, group=None, now=time.time):
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
    run_dir = tempfile.mkdtemp(prefix="run-", dir=parent)
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
