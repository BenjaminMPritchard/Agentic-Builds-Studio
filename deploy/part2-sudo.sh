#!/usr/bin/env bash
# Guide Part 2.1, 2.2 (tools already present) and 2.5: the steps that need root. Idempotent.
# Run:  sudo bash deploy/part2-sudo.sh
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
OWNER="${SUDO_USER:?run via sudo}"

id paperclip >/dev/null 2>&1 || useradd -m -s /bin/bash paperclip
mkdir -p /srv/studio/{company,work,locks,data}  # bin/ and claude/ are symlinks made by bin/install
chown -R paperclip:paperclip /srv/studio
# Guide says chmod 750 on your home; yours is already 700 (stricter), so it is left alone.
getent group docker >/dev/null && usermod -aG docker paperclip

# Ollama pins for the Worker (separate drop-in; your existing ones are untouched).
install -d /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/studio.conf <<'CONF'
[Service]
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_KEEP_ALIVE=30m"
CONF
systemctl daemon-reload
systemctl restart ollama

# Let the paperclip user read the studio checkout without opening your home.
echo "done. paperclip: $(id paperclip)"; ls -ld /srv/studio
