#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
host=${VPS_HOST:-root@62.238.55.235}
pi=${PI_HOST:-rob@192.168.17.145}
ssh_options=(-o BatchMode=yes -o ConnectTimeout=10)
mode=${1:---provision}

install_serving() {
    rsync -a -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' "$root/vps/" "$host:/opt/foxcam/vps/"
    ssh "${ssh_options[@]}" "$host" 'bash -s' <<'REMOTE'
set -euo pipefail
mountpoint -q /data
test -d /data/foxcam/site && test -d /data/foxcam/nights
# Official signed repositories: caddyserver.com/docs/install and pkg.cloudflare.com.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl gnupg acl debian-keyring debian-archive-keyring apt-transport-https
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key |
    gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg -o /usr/share/keyrings/cloudflare-main.gpg
echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/cloudflared.list
chmod 644 /usr/share/keyrings/{caddy-stable-archive-keyring,cloudflare-main}.gpg /etc/apt/sources.list.d/{caddy-stable,cloudflared}.list
# Ubuntu Pro's ESM priority otherwise selects Ubuntu's Caddy over the official repo.
printf 'Package: caddy\nPin: origin dl.cloudsmith.io\nPin-Priority: 1001\n' > /etc/apt/preferences.d/foxcam-caddy
# Put the loopback-only config in place before the package can auto-start Caddy.
install -d -m 755 /etc/caddy
install -m 644 /opt/foxcam/vps/Caddyfile /etc/caddy/Caddyfile
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get -o Dpkg::Options::=--force-confold install -y caddy cloudflared
setfacl -m u:caddy:--x /data /data/foxcam
setfacl -m u:caddy:--- /data/foxcam/incoming /data/foxcam/logs
setfacl -R -m u:caddy:r-X /data/foxcam/site /data/foxcam/nights
find /data/foxcam/site /data/foxcam/nights -type d -exec setfacl -m d:u:caddy:r-x {} +
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
systemctl enable caddy
# Admin API is disabled, so activate validated files with a restart, not API reload.
systemctl restart caddy
echo 'Installed loopback Caddy and cloudflared package; tunnel enrollment and cron unchanged'
REMOTE
}

case "$mode" in
--serving)
    install_serving
    exit
    ;;
--check)
    exec ssh "${ssh_options[@]}" "$host" 'bash -s -- preflight' < "$root/vps/check.sh"
    ;;
--secrets)
    # Only this explicit mode invokes op. Values stay in this child and SSH stdin.
    python3 - "$root" "$host" <<'PY'
from pathlib import Path
import shlex
import subprocess
import sys

root, host = Path(sys.argv[1]), sys.argv[2]
content = (root / 'vps/foxcam.env.example').read_text().rstrip() + '\n'
for name, reference in (
    ('NOUS_API_KEY', 'op://foxwatch/nous/secret'),
    ('DEEPINFRA_API_KEY', 'op://foxwatch/deepinfra/api-key'),
    ('TOGETHER_API_KEY', 'op://foxwatch/together/api-key'),
):
    result = subprocess.run(['op', 'read', reference], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(f'Could not resolve {reference}; nothing written')
    value = result.stdout.rstrip('\n')
    if not value or any(c in value for c in '\r\n\0'):
        raise SystemExit(f'Invalid single-line secret for {name}; nothing written')
    content += f'{name}={shlex.quote(value)}\n'
command = '''set -eu
mountpoint -q /data
test -d /data/foxcam
umask 077
temporary=$(mktemp /etc/.foxcam.env.XXXXXX)
trap 'rm -f -- "$temporary"' EXIT
cat > "$temporary"
chmod 600 "$temporary"
chown root:root "$temporary"
mv -f -- "$temporary" /etc/foxcam.env
'''
result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', host, command],
                        input=content, capture_output=True, text=True)
if result.returncode:
    raise SystemExit(f'Secrets write failed (SSH exit {result.returncode}); inspect VPS file state')
print('Installed /etc/foxcam.env atomically, root:root mode 600; cron unchanged')
PY
    ssh "${ssh_options[@]}" "$host" 'bash /opt/foxcam/vps/check.sh storage'
    exit
    ;;
--enable-cron)
    # Run only after the operator confirms secrets installation.
    ssh "${ssh_options[@]}" "$host" 'bash -s' <<'REMOTE'
set -euo pipefail
mountpoint -q /data
test "$(stat -c %a /etc/foxcam.env)" = 600
set -a
source /etc/foxcam.env
set +a
/opt/foxcam/.venv/bin/python - <<'PY'
import os
from foxcam.pipeline import load_config
for model in load_config()['MODELS']:
    key = model.split('/')[0].upper() + '_API_KEY'
    if not os.environ.get(key, '').strip():
        raise SystemExit(f'Missing {key}; cron stays disabled')
PY
bash /opt/foxcam/vps/check.sh pipeline
install -o root -g root -m 644 /opt/foxcam/vps/foxcam.cron /etc/cron.d/foxcam
echo 'Enabled hourly Fox Watch cron'
REMOTE
    exit
    ;;
--provision) ;;
*) echo 'usage: install.sh [--check|--provision|--secrets|--enable-cron|--serving]' >&2; exit 2 ;;
esac

# The read-only preflight rejects unexpected entries before any deletion.
ssh "${ssh_options[@]}" "$host" 'bash -s -- preflight' < "$root/vps/check.sh"
ssh "${ssh_options[@]}" "$host" 'bash -s' <<'REMOTE'
set -euo pipefail
mountpoint -q /data
df -h /data
if [[ ! -e /data/foxcam ]]; then
    if id agent >/dev/null 2>&1; then
        uid=$(id -u agent)
        test "$uid" -ge 1000
        test "$(getent passwd agent | cut -d: -f6)" = /home/agent
        loginctl disable-linger agent
        loginctl terminate-user agent || true
        pkill -KILL -u "$uid" || test "$?" = 1
        crontab -u agent -r 2>/dev/null || true
        userdel --remove agent
    fi
    rm -rf --one-file-system -- /data/mt-data /data/tmp
    test ! -e /data/mt-data && test ! -e /data/tmp
    chown root:root /data
fi
install -d -o root -g root -m 755 /data/foxcam/{incoming,nights,site,logs} /opt/foxcam
if ! dpkg-query -W -f='${Status}\n' ffmpeg python3-venv rsync cron 2>/dev/null |
    awk '$0 != "install ok installed" { bad=1 } END { exit bad || NR != 4 }'; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg python3-venv rsync cron
fi
test "$(command -v rrsync)" = /usr/bin/rrsync
python3 -m venv /opt/foxcam/.venv
systemctl enable --now cron
df -h /data
REMOTE
rsync -a --exclude='__pycache__' --exclude='*.pyc' -e 'ssh -o BatchMode=yes -o ConnectTimeout=10' \
    "$root/src" "$root/tests" "$root/vps" "$root/pyproject.toml" "$host:/opt/foxcam/"
ssh "${ssh_options[@]}" "$host" 'bash -s' <<'REMOTE'
set -euo pipefail
/opt/foxcam/.venv/bin/python -m pip install /opt/foxcam
chown -R root:root /opt/foxcam/src /opt/foxcam/tests /opt/foxcam/vps
chmod 755 /opt/foxcam/vps/*.sh
if [[ ! -e /etc/foxcam.env ]]; then
    install -o root -g root -m 600 /opt/foxcam/vps/foxcam.env.example /etc/foxcam.env
fi
# Cron is staged under /opt only; neither provisioning nor secrets enables the job.
bash /opt/foxcam/vps/check.sh storage
REMOTE

# Host-key material comes through the Mac's existing authenticated VPS connection.
server_key=$(ssh "${ssh_options[@]}" "$host" 'cat /etc/ssh/ssh_host_ed25519_key.pub')
printf '%s %s\n' "${host#*@}" "$server_key" | ssh "${ssh_options[@]}" "$pi" '
set -eu
umask 077
mkdir -p /home/rob/.ssh
chmod 700 /home/rob/.ssh
IFS= read -r host_key
touch /home/rob/.ssh/known_hosts
grep -Fxq -- "$host_key" /home/rob/.ssh/known_hosts || printf "\n%s\n" "$host_key" >> /home/rob/.ssh/known_hosts
chmod 600 /home/rob/.ssh/known_hosts
if test ! -e /home/rob/.ssh/foxcam_ed25519; then
    ssh-keygen -q -t ed25519 -N "" -C foxcam-transfer -f /home/rob/.ssh/foxcam_ed25519
fi
'
public_key=$(ssh "${ssh_options[@]}" "$pi" 'cat /home/rob/.ssh/foxcam_ed25519.pub')
printf '%s\n' "$public_key" | ssh "${ssh_options[@]}" "$host" '
set -eu
test "$(command -v rrsync)" = /usr/bin/rrsync
umask 077
mkdir -p /root/.ssh
chmod 700 /root/.ssh
IFS= read -r public_key
case "$public_key" in "ssh-ed25519 "*) ;; *) exit 1;; esac
entry="restrict,command=\"/usr/bin/rrsync -wo /data/foxcam/incoming\" $public_key"
touch /root/.ssh/authorized_keys
grep -Fxq -- "$entry" /root/.ssh/authorized_keys || printf "\n%s\n" "$entry" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
'
# Apply strict host checking to the existing Pi sync script without changing its config.
scp "${ssh_options[@]}" "$root/pi/sync.sh" "$pi:/home/rob/foxcam-sync.install"
ssh "${ssh_options[@]}" "$pi" 'sudo -n install -o root -g root -m 755 /home/rob/foxcam-sync.install /opt/foxcam-pi/sync.sh && rm /home/rob/foxcam-sync.install'
echo 'Provisioned VPS and restricted Pi transfer; secrets step and hourly cron activation remain separate'
install_serving
