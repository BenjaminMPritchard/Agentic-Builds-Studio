#!/usr/bin/env bash
# One-off host step (Benjamin, with sudo) for Codex agents. Run from the activated runtime:
#
#   sudo bash /srv/studio/company/deploy/codex-setup.sh
#
# 1. Installs the Codex CLI system-wide (root-owned), copied from Benjamin's installed version, so the usage
#    reader (paperclip) and the agents (studio-agent) run one known binary.
# 2. Installs /etc/codex/requirements.toml: Guard as the only hook, sub-agents off, no full-access sandbox.
# 3. Makes the Studio's Codex home (/srv/studio/data/codex-home): paperclip writes skills there; the ChatGPT
#    sign-in (auth.json) belongs to studio-agent, which is the only user that runs Codex (agents and the
#    usage reader alike), because Codex keeps auth.json owner-only and rewrites it on every token refresh.
# 4. Installs the sudo rule that lets paperclip start Codex as studio-agent.
# Then sign in once (ChatGPT, not an API key) as printed at the end. Safe to run again.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run it with sudo" >&2; exit 1; }
HERE="$(dirname "$(realpath "${BASH_SOURCE[0]}")")"
SRC="${CODEX_SOURCE:-$(sudo -u "${SUDO_USER:-benjamin}" -i sh -c 'readlink -f "$(command -v codex)"')}"
[ -x "$SRC" ] || { echo "no Codex binary found for ${SUDO_USER:-benjamin}; set CODEX_SOURCE=/path/to/codex" >&2; exit 1; }
install -o root -g root -m 0755 "$SRC" /usr/local/bin/codex
[ -x "$(dirname "$SRC")/codex-code-mode-host" ] && install -o root -g root -m 0755 "$(dirname "$SRC")/codex-code-mode-host" /usr/local/bin/codex-code-mode-host
install -D -o root -g root -m 0644 "$HERE/codex/requirements.toml" /etc/codex/requirements.toml

HOME_DIR=/srv/studio/data/codex-home
install -d -o paperclip -g studio -m 2770 "$HOME_DIR"
setfacl -R -m u:paperclip:rwX,g:studio:rwX "$HOME_DIR"
find "$HOME_DIR" -type d -exec setfacl -d -m u:paperclip:rwX,g:studio:rwX,m:rwX {} +

TMP="$(mktemp)"
cp "$HERE/studio-agent/sudoers" "$TMP"
visudo -cf "$TMP" >/dev/null
install -o root -g root -m 0440 "$TMP" /etc/sudoers.d/studio-agent
rm -f "$TMP"

# Checks
/usr/local/bin/codex --version
sudo -u studio-agent -H env CODEX_HOME="$HOME_DIR" /usr/local/bin/codex features list 2>/dev/null \
  | awk '$1=="multi_agent"||$1=="multi_agent_v2"||$1=="hooks"{print "  " $1 " " $NF}'
sudo -l -U paperclip | grep -q '/usr/local/bin/codex' && echo "ok: sudo rule for Codex"
echo "ok: now sign in once as studio-agent (ChatGPT device login; follow the link it prints):"
echo "  sudo -u studio-agent -H env CODEX_HOME=$HOME_DIR /usr/local/bin/codex login --device-auth"
