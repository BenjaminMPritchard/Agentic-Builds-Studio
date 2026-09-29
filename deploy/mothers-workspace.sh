#!/usr/bin/env bash
# One-off host step (Benjamin, with sudo): give the Mothers project a clone and worktree folder that both
# paperclip (which creates worktrees and runs worktree-setup) and studio-agent (which works in them) can write.
# Paperclip's default places them under /home/paperclip, which confined agents cannot enter.
#
#   sudo bash deploy/mothers-workspace.sh
#
# Then point the Paperclip project at it: python3 projects/mothers-carpentry/import.py --workspace --apply
# Safe to run again. Removes nothing; Paperclip's old managed clone is left where it is.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo" >&2; exit 1; }
REPO_URL=https://github.com/Agentic-Builds-Studio-Client-Pages/Mothers-Carpentry-Webpage.git
BASE=/srv/studio/projects/mothers
install -d -o paperclip -g studio -m 2770 /srv/studio/projects "$BASE" "$BASE/worktrees"

if [ ! -d "$BASE/repo/.git" ]; then
  # Paperclip's read-only checkout token, passed in the environment only (never on a command line).
  GIT_TOKEN="$(sed -n 's/^GH_TOKEN=//p' /etc/paperclip.env | head -1)"
  export GIT_TOKEN
  sudo --preserve-env=GIT_TOKEN -u paperclip -H git -c credential.helper= \
    -c 'credential.helper=!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$GIT_TOKEN"; }; f' \
    clone -q "$REPO_URL" "$BASE/repo"
  unset GIT_TOKEN
fi
sudo -u paperclip git -C "$BASE/repo" config core.sharedRepository group

# Group studio (paperclip and studio-agent) can write everything, now and in anything created later: with a
# default ACL the creating process's umask is ignored, so files git and npm create stay group-writable.
chgrp -R studio "$BASE"
find "$BASE" -type d -exec chmod g+s {} +
setfacl -R -m u:paperclip:rwX,g:studio:rwX "$BASE"
find "$BASE" -type d -exec setfacl -d -m u:paperclip:rwX,g:studio:rwX,m:rwX {} +

# Both users' git must trust folders the other one created.
for u in paperclip studio-agent; do
  sudo -u "$u" -H git config --global --get-all safe.directory 2>/dev/null | grep -qx '/srv/studio/projects/\*' \
    || sudo -u "$u" -H git config --global --add safe.directory '/srv/studio/projects/*'
done

# Checks
sudo -u studio-agent -H git -C "$BASE/repo" status --short --branch | head -1
sudo -u studio-agent touch "$BASE/worktrees/.write-test" && rm -f "$BASE/worktrees/.write-test" && echo "ok: studio-agent can write worktrees"
sudo -u studio-agent touch "$BASE/repo/.git/.write-test" && rm -f "$BASE/repo/.git/.write-test" && echo "ok: studio-agent can write the clone's .git"
sudo -u paperclip git -C "$BASE/repo" remote get-url origin
echo "ok: $BASE ready"
