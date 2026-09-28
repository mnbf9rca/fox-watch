#!/usr/bin/env bash
set -euo pipefail

# Run on the VPS only, after creating the hostname-wide email-only Access policy.
[[ $EUID == 0 ]] || { echo 'Run as root on the VPS' >&2; exit 1; }
[[ ${1:-} == --access-ready && $# == 1 ]] || {
    echo 'First configure Access for all of foxwatch.cynexia.com with only your email allowed, then run: bash /opt/foxcam/vps/publish.sh --access-ready' >&2
    exit 1
}
bash /opt/foxcam/vps/check.sh serving
umask 077
install -d -m 700 /etc/cloudflared
# Refuse to replace a service belonging to another tunnel.
unit=$(systemctl show cloudflared.service -p FragmentPath --value)
if [[ -n $unit ]]; then
    command=$(systemctl show cloudflared.service -p ExecStart --value)
    [[ $command == *'--config /etc/cloudflared/config.yml tunnel run'* ]] || {
        echo 'Existing cloudflared service has a different command; left untouched' >&2; exit 1;
    }
fi
temporary_config=''
cleanup() {
    [[ -z $temporary_config ]] || rm -f -- "$temporary_config"
}
trap cleanup EXIT

export TUNNEL_ORIGIN_CERT=/root/.cloudflared/cert.pem
[[ -s $TUNNEL_ORIGIN_CERT ]] || {
    echo 'Run cloudflared tunnel login on this VPS, authorize cynexia.com in your browser, then rerun this command' >&2
    exit 1
}
chmod 600 "$TUNNEL_ORIGIN_CERT"

tunnel_id=$(cloudflared tunnel list --output json --name foxwatch | python3 -c '
import json, sys
from uuid import UUID
rows = [r for r in (json.load(sys.stdin) or []) if r["name"] == "foxwatch"]
if len(rows) > 1:
    raise SystemExit("Multiple foxwatch tunnels; resolve the duplicate names first")
if rows:
    print(UUID(rows[0]["id"]))
')
if [[ -z $tunnel_id ]]; then
    cloudflared tunnel create --credentials-file /etc/cloudflared/foxwatch.json foxwatch
fi
# Existing tunnels must keep their existing secret; never silently rotate or replace it.
tunnel_id=$(python3 - "$tunnel_id" <<'PY'
import json
from pathlib import Path
import sys
from uuid import UUID

path = Path('/etc/cloudflared/foxwatch.json')
if not path.is_file():
    raise SystemExit('Restore existing foxwatch tunnel credentials to /etc/cloudflared/foxwatch.json before rerunning')
row = json.loads(path.read_text())
tunnel_id = str(UUID(row['TunnelID']))
if sys.argv[1] and tunnel_id != sys.argv[1]:
    raise SystemExit('Existing tunnel and local credentials disagree; nothing replaced')
if not row.get('AccountTag') or not row.get('TunnelSecret'):
    raise SystemExit('Incomplete tunnel credentials')
print(tunnel_id)
PY
)
chmod 600 /etc/cloudflared/foxwatch.json
if [[ -e /etc/cloudflared/config.yml ]]; then
    if ! grep -Fxq "tunnel: $tunnel_id" /etc/cloudflared/config.yml ||
       ! grep -Fxq 'credentials-file: /etc/cloudflared/foxwatch.json' /etc/cloudflared/config.yml; then
        echo 'Existing cloudflared config belongs to another tunnel or credentials; left untouched' >&2
        exit 1
    fi
fi
temporary_config=$(mktemp /etc/cloudflared/.config.XXXXXX)
cat > "$temporary_config" <<CONFIG
tunnel: $tunnel_id
credentials-file: /etc/cloudflared/foxwatch.json
ingress:
  - hostname: foxwatch.cynexia.com
    service: http://127.0.0.1:8080
  - service: http_status:404
CONFIG
cloudflared tunnel --config "$temporary_config" ingress validate
mv -f -- "$temporary_config" /etc/cloudflared/config.yml
if [[ -z $unit ]]; then cloudflared --config /etc/cloudflared/config.yml service install; fi
systemctl enable cloudflared
systemctl restart cloudflared
# The CLI reuses an identical DNS route and refuses conflicting records (no --overwrite-dns).
cloudflared tunnel route dns "$tunnel_id" foxwatch.cynexia.com
echo 'Published foxwatch tunnel and DNS; verify Access blocks unauthenticated page and direct media requests'
