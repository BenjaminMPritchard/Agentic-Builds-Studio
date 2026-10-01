#!/usr/bin/env bash
# One-off host step (Benjamin, with sudo) for the agents' shared package cache. Run from the activated runtime:
#
#   sudo bash /srv/studio/company/deploy/agent-cache-setup.sh
#
# Makes /srv/studio/data/agent-cache, owned by studio-agent (the only user that runs agent CLIs). bin/agent-exec
# points uv, npm and pip there when the folder exists, and adds it to Codex's writable roots, so packages are
# downloaded once instead of on every run. Safe to run again; remove the folder to go back to per-run caches.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo" >&2; exit 1; }
CACHE=/srv/studio/data/agent-cache
install -d -o studio-agent -g studio -m 2770 "$CACHE" "$CACHE/uv" "$CACHE/npm" "$CACHE/pip"
sudo -u studio-agent -H sh -c "touch '$CACHE/uv/.ok' && rm '$CACHE/uv/.ok'" && echo "ok: studio-agent can write $CACHE"
