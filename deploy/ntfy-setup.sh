#!/usr/bin/env bash
# One-off host step (Benjamin): a private ntfy server for the Studio's notices (lib/notify.py), reachable only
# over the tailnet. Run as yourself (it uses sudo where needed), from the activated runtime:
#
#   bash /srv/studio/company/deploy/ntfy-setup.sh
#
# 1. Runs ntfy in Docker, bound to 127.0.0.1:2586, restarted with the machine. Nobody can read or post without
#    logging in (deny-all), so tailnet guests can't see notices.
# 2. Serves it over the tailnet at https://bp-desktop.tailbedd63.ts.net:8444.
# 3. Makes your ntfy login (asks you for a password) and a posting token for the Studio, saved for paperclip in
#    /etc/studio/ntfy-token and /etc/studio/notify.json.
# 4. Sends a test notice as paperclip (held until 07:00 if run during quiet hours, 22:00-07:00).
# iPhone: instant delivery needs Apple's push service, which ntfy reaches through ntfy.sh. Only a message id goes
# that way; the text stays on this machine (upstream-base-url). Android works without it. Safe to run again.
set -euo pipefail
HOST=bp-desktop.tailbedd63.ts.net
PORT=8444
TOPIC=studio
URL="https://$HOST:$PORT"

if ! docker inspect studio-ntfy >/dev/null 2>&1; then
  docker run -d --name studio-ntfy --restart unless-stopped -p 127.0.0.1:2586:80 \
    -v studio-ntfy-cache:/var/cache/ntfy -v studio-ntfy-lib:/var/lib/ntfy \
    -e NTFY_BASE_URL="$URL" -e NTFY_BEHIND_PROXY=true \
    -e NTFY_CACHE_FILE=/var/cache/ntfy/cache.db -e NTFY_AUTH_FILE=/var/lib/ntfy/user.db \
    -e NTFY_AUTH_DEFAULT_ACCESS=deny-all -e NTFY_UPSTREAM_BASE_URL=https://ntfy.sh \
    binwiederhier/ntfy serve >/dev/null
  sleep 3
fi
echo "ok: ntfy running"

tailscale serve --bg --https="$PORT" http://127.0.0.1:2586 >/dev/null 2>&1 \
  || sudo tailscale serve --bg --https="$PORT" http://127.0.0.1:2586 >/dev/null
echo "ok: $URL (tailnet only)"

if ! docker exec studio-ntfy ntfy user list 2>&1 | grep -q '^user benjamin'; then
  echo "Choose a password for your ntfy login (you type it into the phone app once):"
  docker exec -it studio-ntfy ntfy user add benjamin
fi
docker exec studio-ntfy ntfy access benjamin "$TOPIC" rw >/dev/null

if ! sudo test -s /etc/studio/ntfy-token; then
  TOKEN="$(docker exec studio-ntfy ntfy token add --label studio-notify benjamin 2>&1 | grep -o 'tk_[A-Za-z0-9]*')"
  [ -n "$TOKEN" ] || { echo "could not make a token" >&2; exit 1; }
  printf '%s\n' "$TOKEN" | sudo install -D -o paperclip -g paperclip -m 0400 /dev/stdin /etc/studio/ntfy-token
fi
printf '{"ntfy_url": "%s/%s", "token_file": "/etc/studio/ntfy-token"}\n' "$URL" "$TOPIC" \
  | sudo install -o paperclip -g paperclip -m 0444 /dev/stdin /etc/studio/notify.json
echo "ok: /etc/studio/notify.json"

cd /tmp && sudo -u paperclip env PYTHONPATH=/srv/studio/company STUDIO_DATA=/srv/studio/data python3 -c '
import time
from lib import notify
print("test notice:", notify.send("/srv/studio/data", "Test from the Studio: notices reach your phone.", time.time()))'
echo
echo "Phone: install the ntfy app, add server $URL, log in as benjamin, subscribe to topic '$TOPIC'."
