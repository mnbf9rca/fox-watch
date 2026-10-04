#!/usr/bin/env bash
set -euo pipefail

mode=${1:?usage: check.sh timers|capture|sync-failure|remux}
# Also runnable off-Pi: replay a short H.264 capture and inject remux failures.
if [[ $mode == remux ]]; then
    python3 - "$(dirname "$0")/record.sh" <<'PY'
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

recorder = Path(sys.argv[1]).resolve()
with TemporaryDirectory() as temporary:
    work = Path(temporary)
    fixture = work / "capture.h264"
    ffmpeg = shutil.which("ffmpeg")
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=size=64x64:rate=10",
                    "-t", "5", "-c:v", "libx264", "-f", "h264", str(fixture)], check=True)
    commands = work / "bin"
    commands.mkdir()
    for name, body in {
        "rpicam-vid": 'for last; do :; done\ncp "$CHECK_FIXTURE" "$last"',
        "ffmpeg": '''for last; do :; done
case "$CHECK_REMUX" in
empty) : > "$last" ;;
invalid) printf 'not an MP4' > "$last" ;;
zero) exec "$CHECK_FFMPEG" -v error -f lavfi -i color=size=64x64 -t 0 -c:v libx264 "$last" ;;
interrupt) echo ready > "$CHECK_READY"; exec "$CHECK_FFMPEG" -re "$@" ;;
valid) exec "$CHECK_FFMPEG" "$@" ;;
esac''',
    }.items():
        command = commands / name
        command.write_text("#!/usr/bin/env bash\nset -eu\n" + body + "\n")
        command.chmod(0o755)
    for case in ("empty", "invalid", "zero", "interrupt", "valid"):
        recordings = work / case
        recordings.mkdir()
        ready = work / "ready"
        env = os.environ | dict(PATH=str(commands) + os.pathsep + os.environ["PATH"],
            START_TIME="19:00", STOP_TIME="07:00", TZ="Europe/London", SHUTTER_US="0", GAIN="0",
            RECORDINGS_DIR=str(recordings), CHECK_FIXTURE=str(fixture), CHECK_FFMPEG=ffmpeg,
            CHECK_REMUX=case, CHECK_READY=str(ready))
        with subprocess.Popen(["bash", str(recorder), "--once"], env=env, start_new_session=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            try:
                if case == "interrupt":
                    deadline = time.monotonic() + 5
                    while not ready.exists() and time.monotonic() < deadline:
                        time.sleep(.01)
                    assert ready.exists(), "remux did not start"
                    time.sleep(.1)  # Real ffmpeg is pacing a five-second remux with -re.
                    os.killpg(process.pid, signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=10)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        if case == "valid":
            assert process.returncode == 0, stderr
            clip, = recordings.iterdir()
            duration = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "csv=p=0", str(clip)], text=True)
            assert not clip.name.startswith(".") and float(duration) > 0
        else:
            assert not list(recordings.iterdir()), f"{case}: published invalid MP4 or leaked hidden files"
            assert process.returncode != 0, f"{case}: recorder reported success"
            if case != "interrupt":
                assert "Discarding" in stderr, stderr
        print(f"PASS remux: {case}")
PY
    exit 0
fi
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
    systemctl cat foxcam-record.timer | grep -Fx 'OnActiveSec=30s' >/dev/null
    systemctl cat foxcam-sync.timer | grep -Fx 'OnCalendar=*:0/5' >/dev/null
    calendar=$(systemd-analyze calendar --base-time='2026-10-24 00:00:00 Europe/London' --iterations=3 "$expression")
    [[ $calendar == *'2026-10-24'* && $calendar == *'2026-10-25'* && $calendar == *'BST'* && $calendar == *'GMT'* ]]
    early=$(date -u -d '2026-10-25 01:30:00+01:00' +%Y-%m-%dT%H-%M-%SZ)
    late=$(date -u -d '2026-10-25 01:30:00+00:00' +%Y-%m-%dT%H-%M-%SZ)
    test "$early" != "$late"
    echo "PASS timers: record=$expression + boot 30s + activation 30s; sync=*:0/5; restart=10s; User=rob; KillMode=control-group; time-wait-sync enabled and ordered; BST/GMT transition and unique UTC names verified"
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
    bash "$(dirname "$0")/check.sh" remux
    echo 'capture: recording one five-minute indoor segment as rob'
    runuser -u rob -- env RECORDINGS_DIR="$work" /opt/foxcam-pi/record.sh --once > "$work/capture.log" 2>&1 || {
        cat "$work/capture.log"; exit 1;
    }
    shopt -s nullglob
    clips=("$work/"*.mp4)
    test "${#clips[@]}" = 1
    format=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of csv=p=0 "${clips[0]}")
    test "$format" = "h264,${WIDTH:-1280},${HEIGHT:-720},10/1"
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
        ALWAYS_ON=0 timeout 90 /opt/foxcam-pi/record.sh > "$work/boundary.log" 2>&1 || { cat "$work/boundary.log"; exit 1; }
    boundary_clips=("$work/boundary/"*.mp4)
    test "${#boundary_clips[@]}" = 1
    echo "PASS capture: $format; duration=${duration}s; $keyframes one-second keyframes; full decode OK; interrupted capture preserved exactly one final MP4; STOP_TIME exit=0"
    ;;
*) echo 'usage: check.sh timers|capture|sync-failure|remux' >&2; exit 2 ;;
esac
