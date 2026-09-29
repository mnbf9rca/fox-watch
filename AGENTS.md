# fox-cam agent notes

Fox Watch: a Raspberry Pi records the garden overnight, a VPS classifies what moved, a private page shows the results. Design: `docs/superpowers/specs/2026-09-28-fox-cam-design.md`. Plan: `docs/superpowers/plans/2026-09-28-fox-cam.md`. Operator runbook: `README.md`.

## Hosts

- Pi: `rob@192.168.17.145`, hostname `fox-watch`, passwordless sudo. Recorder files under `/opt/foxcam-pi`, config `/etc/foxcam.env`, recordings `/home/rob/foxcam-recordings`.
- VPS: `root@62.238.55.235` (Hetzner). Code `/opt/foxcam`, data `/data/foxcam` on the 50 GB volume, config `/etc/foxcam.env` (mode 600, holds API keys), tunnel credentials `/etc/cloudflared`. Only SSH is public; Caddy listens on `127.0.0.1:8080` behind a Cloudflare tunnel.
- Site: https://foxwatch.cynexia.com, Cloudflare Access app `foxwatch` with the same two reusable policies as `watch.cynexia.com`.

## Deploy

- Pi: `bash pi/install.sh` from the Mac. Checks: `ssh rob@192.168.17.145 'sudo bash /opt/foxcam-pi/check.sh timers|capture|sync-failure'`.
- VPS code: `bash vps/install.sh --provision`. Serving files: `bash vps/install.sh --serving`. Config or key change: edit `vps/foxcam.env.example` then `bash vps/install.sh --secrets`. Cron: `bash vps/install.sh --enable-cron`. Checks: `ssh root@62.238.55.235 'bash /opt/foxcam/vps/check.sh storage|pipeline|serving'`.
- Deploying code that changes `vps/foxcam.cron` or `vps/foxcam.env.example` needs `--provision` (ships code, downloads the pinned detector model) and then `--secrets` (rewrites `/etc/foxcam.env`); `--enable-cron` only installs the cron file already under `/opt/foxcam`. Pause the cron during a deploy (`mv /etc/cron.d/foxcam /root/foxcam.cron.off`, deploy, move back) so a run never starts on half-updated code.
- To re-track existing clips after a detector or filter change, delete the `tracks` key from their sidecars; the next run re-tracks any sidecar without `tracks` whose raw clip still exists and discards its old clip-level labels.
- Tunnel and DNS: `ssh root@62.238.55.235 'bash /opt/foxcam/vps/publish.sh --access-ready'`, rerunnable, needs a prior `cloudflared tunnel login` on the VPS.

## Secrets

- Never export secret values into a shell. `.envrc` exports only the 1Password service account token; run anything that needs a key as `op run --env-file=.env.tpl -- <command>`.
- Live checks that need keys: `op run --env-file=.env.tpl -- .venv/bin/python tests/check_classifiers.py` and `... tests/check_pipeline.py --live`.
- Codex tool commands do not see direnv variables or the token. Codex 0.158 runs tool commands through a shared app-server daemon started once per machine from whichever shell launched Codex first, and commands inherit that daemon's environment, not the TUI's. Do not restart the daemon from this repo's shell: every Codex session on the machine would then hold this project's vault token. Have a Claude session that loaded `.envrc` run the secret-bearing commands and relay non-secret output. Codex's own `*TOKEN*` name filter is off by default and is not the cause.

## Gotchas

- Detection runs in a 4-process pool with one OpenCV thread each (`WORKERS`); OpenCV alone would otherwise use every core per process. Watch `processed ... clip minutes` in `/data/foxcam/logs/*.log`; seconds per clip minute must stay below 60 or the 5 minute cron falls behind. Python buffers that log until the run exits.
- COCO detector classes outside person, the five vehicle classes and seven animal classes are dropped; tracks are kept only when their centroid-bounds diagonal is at least `MIN_TRACK_MOVE_RATIO` (default 0.75) times the mean `max(width, height)` of their boxes, with a 20 pixel absolute floor. `DETECT_CONFIDENCE` defaults to 0.5 and small or dim animals sit near it.

- Together.ai's serverless vision models reject requests with more than one image, and its Qwen3-VL models need a paid dedicated endpoint. Together stays configured but out of `MODELS`.
- Python's default urllib User-Agent is blocked by Together's Cloudflare front (HTTP 403 error 1010); `classify.py` sends its own.
- A capture before the local `START_TIME` belongs to the previous evening's night, so a 16:36 UTC test clip appears under the day before.
- `rpicam-vid` holds the camera; stop `foxcam-record.service` before taking a still with `rpicam-still`, then start it again if inside the recording window. The timer only fires at `START_TIME`, so a service that died mid-window must be started by hand.
- The Pi currently runs `ALWAYS_ON=1` with automatic exposure (`SHUTTER_US=0`, `GAIN=0`) for the street view; the night pages still split at `START_TIME`.
- Running motion thresholds (`MIN_BLOB_AREA`, `EDGE_MARGIN`) and camera settings (`SHUTTER_US`, `GAIN`, `AWB_GAINS`) are indoor starting values, not garden-calibrated.
