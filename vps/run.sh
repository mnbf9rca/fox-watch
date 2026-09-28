#!/usr/bin/env bash
set -euo pipefail
mountpoint -q /data || exit 1

set -a
source /etc/foxcam.env
set +a
test -d "$DATA_DIR"
mkdir -p "$DATA_DIR/logs"
exec /opt/foxcam/.venv/bin/python -m foxcam run --data "$DATA_DIR" \
    > "$DATA_DIR/logs/$(date -u +%Y-%m-%dT%H-%M-%SZ).log" 2>&1
