#!/usr/bin/env bash
set -euo pipefail

mountpoint -q /data || { echo 'FAIL: /data is not a mount point' >&2; exit 1; }
case "${1:-}" in
preflight)
    if [[ -e /data/foxcam || -L /data/foxcam ]]; then
        [[ -d /data/foxcam && ! -L /data/foxcam ]] || { echo 'FAIL: unsafe /data/foxcam' >&2; exit 1; }
    else
        shopt -s nullglob dotglob
        for entry in /data/*; do
            case "$entry" in
                /data/lost+found|/data/mt-data|/data/tmp) ;;
                *) echo "FAIL: unexpected data-volume entry: $entry" >&2; exit 1 ;;
            esac
        done
    fi
    echo 'PASS preflight: /data mounted; initialization paths accepted'
    ;;
storage)
    test -f /etc/foxcam.env || { echo 'FAIL storage: /etc/foxcam.env is missing'; exit 1; }
    test "$(stat -c %a /etc/foxcam.env)" = 600
    for dir in incoming nights site logs; do test -d "/data/foxcam/$dir"; done
    nonmount=$(mktemp -d)
    if mountpoint -q "$nonmount"; then rmdir "$nonmount"; exit 1; fi
    rmdir "$nonmount"
    /opt/foxcam/.venv/bin/python -c 'import foxcam, cv2, numpy'
    command -v ffmpeg ffprobe rsync >/dev/null
    test "$(command -v rrsync)" = /usr/bin/rrsync
    systemctl is-active --quiet cron
    expected='0 * * * * root /usr/bin/flock -n /run/lock/foxcam.lock /opt/foxcam/vps/run.sh'
    test "$(cat /opt/foxcam/vps/foxcam.cron)" = "$expected"
    cron_state=disabled
    if [[ -e /etc/cron.d/foxcam ]]; then
        cmp /opt/foxcam/vps/foxcam.cron /etc/cron.d/foxcam
        cron_state=enabled
    fi
    secrets=pending
    if (set -a; source /etc/foxcam.env; set +a; /opt/foxcam/.venv/bin/python - <<'PY'
import os
from foxcam.pipeline import load_config
config = load_config()
raise SystemExit(not all(os.environ.get(model.split('/')[0].upper() + '_API_KEY', '').strip()
                        for model in config['MODELS']))
PY
    ); then secrets=ready; fi
    free=$(/opt/foxcam/.venv/bin/python - <<'PY'
import shutil
free = shutil.disk_usage('/data').free / 1024**3
assert free > 10, free
print(f'{free:.2f}')
PY
    )
    echo "PASS storage: /data mounted; non-mount guard rejected; directories=4; env=600; package/tools/cron=OK; secrets=$secrets; hourly_cron=$cron_state; free=${free}GiB"
    ;;
pipeline)
    /opt/foxcam/.venv/bin/python /opt/foxcam/tests/check_pipeline.py
    # Exercise the same lock path as cron without invoking the real-data job.
    exec 9>/run/lock/foxcam.lock
    flock -n 9
    if flock -n /run/lock/foxcam.lock true; then echo 'FAIL: overlapping lock acquired'; exit 1; fi
    flock -u 9
    flock -n /run/lock/foxcam.lock true
    echo 'PASS pipeline: synthetic recovery/retention/space checks; overlapping invocation refused'
    ;;
*) echo 'usage: check.sh preflight|storage|pipeline' >&2; exit 2 ;;
esac
