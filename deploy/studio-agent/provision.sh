#!/usr/bin/env bash
# Host setup for confined agents (Milestone 2 step 4). Prints what it would do; `--apply` does it.
# Run as root:  sudo deploy/studio-agent/provision.sh [--apply]
# Idempotent. Changes no Paperclip agent config: switching an agent's adapterConfig.command to
# /srv/studio/bin/agent-exec is a separate, per-agent step.
set -euo pipefail
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
run() { if [ $APPLY = 1 ]; then "$@"; else printf 'would: %s\n' "$*"; fi; }
[ $APPLY = 0 ] || [ "$(id -u)" = 0 ] || { echo "run --apply as root" >&2; exit 1; }
HERE="$(cd "$(dirname "$(realpath "${BASH_SOURCE[0]}")")" && pwd)"

# 1. Users and the shared group. studio-agent is not in docker and has no sudo of its own.
getent group studio >/dev/null || run groupadd --system studio
id studio-agent >/dev/null 2>&1 || run useradd --system --create-home --home-dir /home/studio-agent \
  --shell /usr/sbin/nologin --gid studio studio-agent
run usermod -aG studio paperclip
run chmod 0750 /home/studio-agent

# 2. Shared, group-writable work areas (setgid keeps new files in the group).
for d in /srv/studio/work /srv/studio/locks; do
  run chgrp -R studio "$d"; run chmod -R g+rwX "$d"; run find "$d" -type d -exec chmod g+s {} +
done

# 3. Git trusts the shared worktrees for studio-agent (they are owned by paperclip).
run install -o root -g studio -m 0644 "$HERE/gitconfig" /home/studio-agent/.gitconfig

# 4. The one sudo rule: paperclip may run the CLI as studio-agent, nothing else.
run install -o root -g root -m 0440 "$HERE/sudoers" /etc/sudoers.d/studio-agent
run visudo -cf /etc/sudoers.d/studio-agent

# 5. Not done here: restricting the embedded database port to the paperclip user. The rule is in
#    studio-db.nft; loading it, and keeping it across reboots, is Benjamin's decision (see the playbook).

echo "then, as studio-agent, install the Claude CLI at /home/studio-agent/.local/bin/claude"
