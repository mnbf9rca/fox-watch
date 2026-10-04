#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
host=${PI_HOST:-rob@10.0.2.138}
ssh_options=(-o BatchMode=yes -o ConnectTimeout=10)
stage=$(ssh "${ssh_options[@]}" "$host" 'sudo -n true && mktemp -d')
trap 'ssh "${ssh_options[@]}" "$host" "rm -rf -- $stage"' EXIT
scp "${ssh_options[@]}" "$root/record.sh" "$root/sync.sh" "$root/check.sh" "$root/foxcam.env" \
    "$root/foxcam-record.service" "$root/foxcam-record.timer" "$root/foxcam-sync.service" "$root/foxcam-sync.timer" "$host:$stage/"
ssh "${ssh_options[@]}" "$host" bash -s -- "$stage" <<'REMOTE'
set -euo pipefail
stage=$1
# Preserve local tuning and derive the timer from the configuration actually in use.
config="$stage/foxcam.env"
if [[ -e /etc/foxcam.env ]]; then config=/etc/foxcam.env; fi
source "$config"
for value in "$START_TIME" "$STOP_TIME"; do
    [[ $value =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || { echo 'Times must be HH:MM' >&2; exit 1; }
done
[[ $START_TIME != "$STOP_TIME" && $TZ == Europe/London ]] || { echo 'Use distinct times and TZ=Europe/London' >&2; exit 1; }
sudo -n install -d -o root -g root -m 755 /opt/foxcam-pi /etc/systemd/system/foxcam-record.timer.d
sudo -n install -o root -g root -m 755 "$stage/record.sh" "$stage/sync.sh" "$stage/check.sh" /opt/foxcam-pi/
if [[ ! -e /etc/foxcam.env ]]; then
    sudo -n install -o root -g root -m 644 "$stage/foxcam.env" /etc/foxcam.env
fi
sudo -n install -o root -g root -m 644 "$stage/"*.service "$stage/"*.timer /etc/systemd/system/
printf '[Timer]\nOnCalendar=\nOnCalendar=*-*-* %s:00 %s\n' "$START_TIME" "$TZ" |
    sudo -n tee /etc/systemd/system/foxcam-record.timer.d/schedule.conf >/dev/null
sudo -n install -d -o rob -g rob -m 755 "$RECORDINGS_DIR"
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now systemd-time-wait-sync.service
sudo -n systemctl enable --now foxcam-record.timer foxcam-sync.timer
sudo -n systemctl enable foxcam-record.service
echo 'Installed Pi scripts/config and enabled both timers'
REMOTE
