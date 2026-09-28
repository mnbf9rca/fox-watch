#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")" && pwd)
host=${PI_HOST:-rob@192.168.17.145}
ssh_options=(-o BatchMode=yes -o ConnectTimeout=10)
# Validate the committed nonsecret config before copying anything.
source "$root/foxcam.env"
for value in "$START_TIME" "$STOP_TIME"; do
    [[ $value =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || { echo 'Times must be HH:MM' >&2; exit 1; }
done
[[ $START_TIME != "$STOP_TIME" && $TZ == Europe/London ]] || { echo 'Use distinct times and TZ=Europe/London' >&2; exit 1; }
stage=$(ssh "${ssh_options[@]}" "$host" 'sudo -n true && mktemp -d')
trap 'ssh "${ssh_options[@]}" "$host" "rm -rf -- $stage"' EXIT
scp "${ssh_options[@]}" "$root/record.sh" "$root/sync.sh" "$root/check.sh" "$root/foxcam.env" \
    "$root/foxcam-record.service" "$root/foxcam-record.timer" "$root/foxcam-sync.service" "$root/foxcam-sync.timer" "$host:$stage/"
ssh "${ssh_options[@]}" "$host" bash -s -- "$stage" <<'REMOTE'
set -euo pipefail
stage=$1
source "$stage/foxcam.env"
sudo -n install -d -o root -g root -m 755 /opt/foxcam-pi /etc/systemd/system/foxcam-record.timer.d
sudo -n install -o root -g root -m 755 "$stage/record.sh" "$stage/sync.sh" "$stage/check.sh" /opt/foxcam-pi/
sudo -n install -o root -g root -m 644 "$stage/foxcam.env" /etc/foxcam.env
sudo -n install -o root -g root -m 644 "$stage/"*.service "$stage/"*.timer /etc/systemd/system/
printf '[Timer]\nOnCalendar=\nOnCalendar=*-*-* %s:00 %s\n' "$START_TIME" "$TZ" |
    sudo -n tee /etc/systemd/system/foxcam-record.timer.d/schedule.conf >/dev/null
sudo -n install -d -o rob -g rob -m 755 "$RECORDINGS_DIR"
sudo -n systemctl daemon-reload
sudo -n systemctl enable --now systemd-time-wait-sync.service
sudo -n systemctl enable --now foxcam-record.timer foxcam-sync.timer
echo 'Installed Pi scripts/config and enabled both timers'
REMOTE
