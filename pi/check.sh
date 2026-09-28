#!/usr/bin/env bash
set -euo pipefail

mode=${1:?usage: check.sh timers|capture|sync-failure}
if [[ $mode == timers ]]; then
    systemctl is-active --quiet foxcam-record.timer foxcam-sync.timer || {
        echo 'FAIL timers: Fox Watch timers are missing or inactive'
        exit 1
    }
fi
set -a
source /etc/foxcam.env
set +a

case "$mode" in
timers)
    systemctl is-enabled --quiet systemd-time-wait-sync.service
    for property in Wants After; do
        dependencies=$(systemctl show foxcam-record.service -p "$property" --value)
        [[ " $dependencies " == *' systemd-time-wait-sync.service '* ]]
    done
    test "$(systemctl show foxcam-record.service -p RestartUSec --value)" = 10s
    test "$(systemctl show foxcam-record.service -p User --value)" = rob
    test "$(systemctl show foxcam-record.service -p KillMode --value)" = control-group
    expression="*-*-* $START_TIME:00 $TZ"
    systemctl cat foxcam-record.timer | grep -Fx "OnCalendar=$expression" >/dev/null
    systemctl cat foxcam-record.timer | grep -Fx 'OnBootSec=30s' >/dev/null
    systemctl cat foxcam-sync.timer | grep -Fx 'OnCalendar=*:0/15' >/dev/null
    calendar=$(systemd-analyze calendar --base-time='2026-10-24 00:00:00 Europe/London' --iterations=3 "$expression")
    [[ $calendar == *'2026-10-24'* && $calendar == *'2026-10-25'* && $calendar == *'BST'* && $calendar == *'GMT'* ]]
    early=$(date -u -d '2026-10-25 01:30:00+01:00' +%Y-%m-%dT%H-%M-%SZ)
    late=$(date -u -d '2026-10-25 01:30:00+00:00' +%Y-%m-%dT%H-%M-%SZ)
    test "$early" != "$late"
    echo "PASS timers: record=$expression + boot 30s; sync=*:0/15; restart=10s; User=rob; KillMode=control-group; time-wait-sync enabled and ordered; BST/GMT transition and unique UTC names verified"
    ;;
capture|sync-failure)
    test "$EUID" = 0 || { echo 'Run this check with sudo'; exit 1; }
    work=$(mktemp -d)
    chown rob:rob "$work"
    child=''
    restore_service=0
    restore_timer=0
    cleanup() {
        if [[ -n $child ]]; then
            kill -TERM -- "-$child" 2>/dev/null || true
            wait "$child" 2>/dev/null || true
        fi
        rm -rf -- "$work"
        if (( restore_timer )); then systemctl start foxcam-record.timer; fi
        if (( restore_service )); then systemctl start foxcam-record.service; fi
    }
    trap cleanup EXIT
    trap 'exit 143' TERM
    trap 'exit 130' INT
    if [[ $mode == sync-failure ]]; then
        printf 'recent recording\n' > "$work/recent.mp4"
        printf 'old recording\n' > "$work/old.mp4"
        touch -d '8 days ago' "$work/old.mp4"
        # An empty test identity is not a transfer key; SSH must fail at localhost port 1.
        touch "$work/empty-identity"
        chown rob:rob "$work/"*
        before=$(sha256sum "$work/recent.mp4")
        status=0
        runuser -u rob -- env RECORDINGS_DIR="$work" VPS_HOST=rob@127.0.0.1 SSH_PORT=1 \
            SSH_KEY="$work/empty-identity" /opt/foxcam-pi/sync.sh > "$work/sync.log" 2>&1 || status=$?
        test "$status" -ne 0
        grep -F 'Connection refused' "$work/sync.log" >/dev/null
        test "$before" = "$(sha256sum "$work/recent.mp4")"
        test ! -e "$work/old.mp4"
        mkdir "$work/empty-recordings"
        chown rob:rob "$work/empty-recordings"
        touch -d '8 days ago' "$work/empty-recordings"
        runuser -u rob -- env RECORDINGS_DIR="$work/empty-recordings" VPS_HOST=rob@127.0.0.1 SSH_PORT=1 \
            SSH_KEY="$work/empty-identity" /opt/foxcam-pi/sync.sh > "$work/empty-sync.log" 2>&1 || true
        test -d "$work/empty-recordings"
        echo "PASS sync-failure: rsync exit=$status; localhost:1 refused; recent checksum unchanged; eight-day-old recording deleted; old empty RECORDINGS_DIR preserved"
        exit 0
    fi
    systemctl is-active --quiet foxcam-record.service && restore_service=1
    systemctl is-active --quiet foxcam-record.timer && restore_timer=1
    systemctl stop foxcam-record.timer foxcam-record.service
    echo 'capture: recording one five-minute indoor segment as rob'
    runuser -u rob -- env RECORDINGS_DIR="$work" /opt/foxcam-pi/record.sh --once > "$work/capture.log" 2>&1 || {
        cat "$work/capture.log"; exit 1;
    }
    shopt -s nullglob
    clips=("$work/"*.mp4)
    test "${#clips[@]}" = 1
    format=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of csv=p=0 "${clips[0]}")
    test "$format" = h264,1280,720,10/1
    duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "${clips[0]}")
    awk -v duration="$duration" 'BEGIN { exit !(duration >= 295 && duration <= 305) }'
    keyframes=$(ffprobe -v error -select_streams v:0 -show_packets -show_entries packet=pts_time,flags -of csv=p=0 "${clips[0]}" |
        awk -F, '/K/ { if (n && ($1-last < 0.89 || $1-last > 1.11)) bad=1; last=$1; n++ } END { if (bad || n<290) exit 1; print n }')
    # A complete decode also catches a corrupt remux.
    ffmpeg -v error -i "${clips[0]}" -f null -
    before=$(sha256sum "${clips[0]}")
    setsid runuser -u rob -- env RECORDINGS_DIR="$work" /opt/foxcam-pi/record.sh --once > "$work/interrupt.log" 2>&1 &
    child=$!
    sleep 4
    kill -TERM -- "-$child"
    status=0
    wait "$child" || status=$?
    child=''
    test "$status" -ne 0
    clips=("$work/"*.mp4)
    test "${#clips[@]}" = 1
    test "$before" = "$(sha256sum "${clips[0]}")"
    mkdir "$work/boundary"
    chown rob:rob "$work/boundary"
    boundary_start=$(date +%H:%M)
    boundary_stop=$(date -d "@$(( $(date +%s) + 65 ))" +%H:%M)
    runuser -u rob -- env RECORDINGS_DIR="$work/boundary" START_TIME="$boundary_start" STOP_TIME="$boundary_stop" \
        timeout 90 /opt/foxcam-pi/record.sh > "$work/boundary.log" 2>&1 || { cat "$work/boundary.log"; exit 1; }
    boundary_clips=("$work/boundary/"*.mp4)
    test "${#boundary_clips[@]}" = 1
    echo "PASS capture: $format; duration=${duration}s; $keyframes one-second keyframes; full decode OK; interrupted capture preserved exactly one final MP4; STOP_TIME exit=0"
    ;;
*) echo 'usage: check.sh timers|capture|sync-failure' >&2; exit 2 ;;
esac
