#!/usr/bin/env bash
set -euo pipefail

: "${RECORDINGS_DIR:?}" "${VPS_HOST:?}" "${SSH_KEY:?}"
status=0
if [[ ! -r $SSH_KEY ]]; then
    echo 'Transfer key not installed; skipping SSH until Task 8' >&2
    status=1
else
    # Task 8 restricts this key to rrsync's /data/foxcam/incoming root.
    rsync -a --remove-source-files --exclude='.*' --include='*.mp4' --exclude='*' \
        -e "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -p ${SSH_PORT:-22} -i '$SSH_KEY'" \
        "$RECORDINGS_DIR/" "$VPS_HOST:./" || status=$?
fi
find "$RECORDINGS_DIR" -mindepth 1 -mtime +7 -delete
exit "$status"
