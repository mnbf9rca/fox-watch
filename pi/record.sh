#!/usr/bin/env bash
set -euo pipefail

: "${START_TIME:?}" "${STOP_TIME:?}" "${TZ:?}" "${SHUTTER_US:?}" "${GAIN:?}" "${AWB_GAINS:?}" "${RECORDINGS_DIR:?}"
export TZ
once=0
if [[ ${1:-} == --once && $# == 1 ]]; then once=1
elif (( $# )); then echo 'usage: record.sh [--once]' >&2; exit 2; fi

stop_epoch=0
if (( ! once )); then
    now=$(date +%H:%M)
    stop_day=today
    if [[ $START_TIME < $STOP_TIME ]]; then
        [[ $now < $START_TIME || $now == "$STOP_TIME" || $now > $STOP_TIME ]] && exit 0
    else
        [[ $now < $START_TIME && ( $now == "$STOP_TIME" || $now > $STOP_TIME ) ]] && exit 0
        if [[ $now == "$START_TIME" || $now > $START_TIME ]]; then stop_day=tomorrow; fi
    fi
    stop_epoch=$(date -d "$stop_day $STOP_TIME" +%s)
fi
mkdir -p "$RECORDINGS_DIR"
child=''
raw=''
mp4=''
cleanup() {
    trap '' TERM INT
    if [[ -n $child ]]; then
        kill -TERM "$child" 2>/dev/null || true
        wait "$child" 2>/dev/null || true
    fi
    [[ -z $raw ]] || rm -f -- "$raw"
    [[ -z $mp4 ]] || rm -f -- "$mp4"
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

while :; do
    seconds=300
    if (( ! once )); then
        remaining=$((stop_epoch - $(date +%s)))
        (( remaining > 0 )) || exit 0
        if (( remaining < seconds )); then seconds=$remaining; fi
    fi
    stamp=$(date -u +%Y-%m-%dT%H-%M-%SZ)
    final="$RECORDINGS_DIR/$stamp.mp4"
    [[ ! -e $final ]] || { echo "Capture already exists: $final" >&2; exit 1; }
    raw="$RECORDINGS_DIR/.$stamp.$$.h264"
    mp4="$RECORDINGS_DIR/.$stamp.$$.mp4"
    rpicam-vid --nopreview --width 1280 --height 720 --framerate 10 --codec h264 \
        --inline --intra 10 --timeout "$((seconds * 1000))" --shutter "$SHUTTER_US" --gain "$GAIN" \
        --awbgains "$AWB_GAINS" --output "$raw" &
    child=$!
    wait "$child"
    child=''
    ffmpeg -v error -y -fflags +genpts -r 10 -i "$raw" -c:v copy -an -movflags +faststart "$mp4" &
    child=$!
    wait "$child"
    child=''
    # No overwrite even if another invocation claimed this timestamp during capture.
    mv -n -- "$mp4" "$final"
    [[ ! -e $mp4 ]] || { echo "Capture already exists: $final" >&2; exit 1; }
    rm -f -- "$raw"
    raw=''
    mp4=''
    (( ! once )) || exit 0
    # ponytail: remux leaves a short capture gap; use a continuous segment muxer if that matters.
done
