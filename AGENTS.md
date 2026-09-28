# fox-cam agent notes

Fox Watch: a Raspberry Pi records the garden overnight, a VPS classifies what moved, a private page shows the results. Design: `docs/superpowers/specs/2026-09-28-fox-cam-design.md`. Plan: `docs/superpowers/plans/2026-09-28-fox-cam.md`. Operator runbook: `README.md`.

## Hosts

- Pi: `rob@192.168.17.145`, hostname `fox-watch`, passwordless sudo. Recorder files under `/opt/foxcam-pi`, config `/etc/foxcam.env`, recordings `/home/rob/foxcam-recordings`.
- VPS: `root@62.238.55.235` (Hetzner). Code `/opt/foxcam`, data `/data/foxcam` on the 50 GB volume, config `/etc/foxcam.env` (mode 600, holds API keys), tunnel credentials `/etc/cloudflared`. Only SSH is public; Caddy listens on `127.0.0.1:8080` behind a Cloudflare tunnel.
- Site: https://foxwatch.cynexia.com, Cloudflare Access app `foxwatch` with the same two reusable policies as `watch.cynexia.com`.

## Deploy

- Pi: `bash pi/install.sh` from the Mac. Checks: `ssh rob@192.168.17.145 'sudo bash /opt/foxcam-pi/check.sh timers|capture|sync-failure'`.
- VPS code: `bash vps/install.sh --provision`. Serving files: `bash vps/install.sh --serving`. Config or key change: edit `vps/foxcam.env.example` then `bash vps/install.sh --secrets`. Cron: `bash vps/install.sh --enable-cron`. Checks: `ssh root@62.238.55.235 'bash /opt/foxcam/vps/check.sh storage|pipeline|serving'`.
- Tunnel and DNS: `ssh root@62.238.55.235 'bash /opt/foxcam/vps/publish.sh --access-ready'`, rerunnable, needs a prior `cloudflared tunnel login` on the VPS.

## Secrets

- Never export secret values into a shell. `.envrc` exports only the 1Password service account token; run anything that needs a key as `op run --env-file=.env.tpl -- <command>`.
- Live checks that need keys: `op run --env-file=.env.tpl -- .venv/bin/python tests/check_classifiers.py` and `... tests/check_pipeline.py --live`.
- Codex tool commands do not see direnv variables or the token. Codex 0.158 runs tool commands through a shared app-server daemon started once per machine from whichever shell launched Codex first, and commands inherit that daemon's environment, not the TUI's. Do not restart the daemon from this repo's shell: every Codex session on the machine would then hold this project's vault token. Have a Claude session that loaded `.envrc` run the secret-bearing commands and relay non-secret output. Codex's own `*TOKEN*` name filter is off by default and is not the cause.

## Gotchas

- Together.ai's serverless vision models reject requests with more than one image, and its Qwen3-VL models need a paid dedicated endpoint. Together stays configured but out of `MODELS`.
- Python's default urllib User-Agent is blocked by Together's Cloudflare front (HTTP 403 error 1010); `classify.py` sends its own.
- A capture before the local `START_TIME` belongs to the previous evening's night, so a 16:36 UTC test clip appears under the day before.
- `rpicam-vid` holds the camera; stop `foxcam-record.service` before taking a still with `rpicam-still`, then start it again if inside the recording window. The timer only fires at `START_TIME`, so a service that died mid-window must be started by hand.
- Running motion thresholds (`MIN_BLOB_AREA`, `EDGE_MARGIN`) and camera settings (`SHUTTER_US`, `GAIN`, `AWB_GAINS`) are indoor starting values, not garden-calibrated.
