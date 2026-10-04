# Fox Watch

Offline garden-camera processing for Python 3.12+: scan motion, cut visits, track each detected object, classify animal tracks, annotate H.264 clips, and generate static day pages. Requires `ffmpeg` and `ffprobe` on the path. Pi recording, VPS processing, and loopback serving are installed with the scripts below; private publication requires the separate Cloudflare Access and tunnel steps.

## Local setup and checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
MODEL_DIR=models .venv/bin/python tests/check_video.py
.venv/bin/python tests/check_pipeline.py
```

The default pipeline check needs no secrets and never calls a hosted provider: it uses a dummy credential and a refused localhost connection. It exercises the real CLI and video tools, interrupted-work recovery, classification retries, annotation changes, empty nights, input isolation, low-space refusal, retention, and comparison.

Run hosted checks only in the shell where 1Password is authenticated. API keys are injected into the child process by `op run`; never export or print them. The live pipeline check loads nonsecret defaults from `vps/foxcam.env.example`, lets the existing environment override them, sends generated synthetic frames, and requires valid model answers plus a playable primary annotation. Synthetic frames are a connectivity check, not a species-accuracy test.

```sh
op run --env-file=.env.tpl -- .venv/bin/python tests/check_classifiers.py
op run --env-file=.env.tpl -- .venv/bin/python tests/check_classifiers.py --failure
op run --env-file=.env.tpl -- .venv/bin/python tests/check_pipeline.py --live
```

## Process recordings

Put completed MP4 files in `data/incoming/`, with UTC names such as `2026-09-28T19-05-00Z.mp4`. Copy only completed recordings. Load the committed nonsecret template inside the child shell:

```sh
op run --env-file=.env.tpl -- sh -c 'set -a; . ./vps/foxcam.env.example; exec .venv/bin/python -m foxcam run --data ./data'
op run --env-file=.env.tpl -- sh -c 'set -a; . ./vps/foxcam.env.example; exec .venv/bin/python -m foxcam run --data ./data --night 2026-09-28'
(set -a; . ./vps/foxcam.env.example; .venv/bin/python -m foxcam compare --data ./data)
```

`compare` needs configuration but no secrets and makes no network calls. It prints agreement counts against `PRIMARY_MODEL`, excluding missing or unclassified answers; an empty denominator is `n/a`. `run` requires keys only for providers in `MODELS`. Its default data directory is `/data/foxcam`. Use one process at a time; the VPS cron entry and manual command below use `/run/lock/foxcam.lock`.

Outputs live in `nights/YYYY-MM-DD/`: raw and annotated clips, `.f0.jpg` through `.f3.jpg`, and JSON sidecars. Each track also keeps `.t{id}.jpg` (its largest-box frame with the box drawn) and `.t{id}.crop.jpg` (the full-resolution crop). Sidecars contain `tracks`: objects with `id`, `class`, per-model `labels`, `description`, `entry_edge`, `exit_edge`, and `boxes` (`[frame, x, y, w, h]`). The longest track mirrors its edges, labels and boxes into the legacy top-level fields. Annotated clips show each track in its own colour with its primary label, confidence and path; boxes hold between detections from the first through the last detection. Day pages show an arrow and details per track; checked label filters show counts of visits and hide cards by their primary label using CSS only. `site/index.html` lists all local calendar days; individual pages link to media under `/nights/`. A web server must map `/` to `site/` and `/nights/` to `nights/`; opening HTML directly from disk does not resolve those absolute media URLs. `--night` restricts processing and retention, while the index still includes all days. Empty selected/current days also get pages.

Clip names use the source UTC timestamp plus the unpadded motion offset. Sidecar timestamps record the requested padded start; duration is probed from the actual cut. Stream copying rounds boundaries to keyframes, so padding and timestamps are approximate at that granularity. Visits split at recording boundaries; cross-file merging is deferred. Pages use the local calendar date in `TZ`, including DST; `START_TIME` no longer defines a date boundary. Page times are local with the zone abbreviation; annotated video timestamps use UTC. Clip names and `start_utc` stay in UTC, and the `nights/` directory, `night` field and `--night` option keep their compatibility names. The daytime checkbox still uses `STOP_TIME` to `START_TIME`.

To move existing visits into local calendar-day folders and rebuild the site, run this with processing stopped (no provider keys are needed):

```sh
(set -a; . ./vps/foxcam.env.example; .venv/bin/python -m foxcam refile --data ./data)
```

`refile` moves raw and annotated clips, all saved frames (including track crops), and sidecars using `os.replace`, updates each `night` field, and prints the sidecar count. It checks all destinations before moving and refuses existing targets. A completed rerun moves zero sidecars. Moves are atomic per file, not a transaction across the whole bundle; retain a backup when migrating valuable recordings.

## Recovery, retention, and tuning

Existing cuts, frames, and sidecars are reused. Missing or unclassified model labels are retried; successful labels are retained. `annotation_label` records a list of primary `[label, confidence]` answers, one per track, so changing any answer refreshes the annotation once. `annotation_version=3` adds a bottom-left UTC timestamp to every frame, computed from `start_utc` plus frame index / fps, and upgrades older annotations once when raw media is available; expired raw clips keep their existing video. Outputs use same-directory temporary files and atomic replacement. Source recordings are deleted once every event's cut and sidecar exist; raw event clips then carry recovery if classification or annotation has not finished. No-motion recordings are deleted after creating their night directory. Local file errors preserve available recovery media, allow independent inputs to continue, and return a nonzero exit status. Provider failures remain `unclassified` and do not fail the run.

`MIN_FREE_GB` is checked on the data directory itself before processing; a missing data directory fails without creating anything. Completed raw event clips expire when their local day is older than `RETAIN_NIGHTS`; all configured model labels for every track, frames, and the current annotation must be complete first. Annotated clips, frames, and sidecars are retained. If the primary answer changes after raw expiration, the retained annotated clip stays unchanged and `annotation_label` records the desired answer so later runs move on; the site/sidecar answer may therefore be newer than the burned-in caption. To rerun a successful classifier, remove just that model's answer from the sidecar's `labels` object; change `PRIMARY_MODEL` only to an entry in `MODELS`. Adding a model triggers classification from the retained frames. Removing a model preserves its historical answers.

The initial values in `vps/foxcam.env.example` are tuning defaults: `MIN_BLOB_AREA=25` at 640-pixel scan width (a 25×12 cm body at 9 m spans about 90 px² before silhouette/contour losses), `EDGE_MARGIN=120` at full resolution, `GAP_SECONDS=3`, `PAD_SECONDS=2`, `START_TIME=19:00`, `STOP_TIME=07:00`, `TZ=Europe/London`, `RETAIN_NIGHTS=180`, and `MIN_FREE_GB=10`. Time settings also drive the later Pi recorder. Tune motion area against noise and animal size, gap against fragmented visits, padding against missed approach/departure, and edge margin against the installed camera view. Edge arrows are schematic, not calibrated ground positions.

`MODEL_DIR` defaults to `/opt/foxcam/models`; local checks use the ignored `models/` directory. Provisioning downloads YOLOX-S once and verifies its pinned SHA-256 before installation. Detection runs every second frame through OpenCV, with no extra dependency; person and vehicle tracks bypass hosted models, while other tracks send the drawn frame and crop. `WORKERS=4` runs the pipeline in a process pool with one OpenCV thread per worker. Each run with incoming clips logs `INFO: processed M clip minutes in S s (R s per clip minute)`; the pipeline check also prints `R/60`, the real-time ratio, which should stay below 1 on average to avoid backlog.

The selected models and their observed fixture answers are documented in `tests/fixtures/SOURCES.md`. Together is excluded because its tested serverless option rejects multiple images and its VL alternatives require dedicated endpoints. Its URL and vault reference remain for a future compatible offering. Hosted fixture results do not establish outdoor infrared accuracy: after installation, walk across the patch, inspect the annotated clip and entry/exit edges, then hand-check roughly 200 retained frames before choosing the primary model. Pi/VPS deployment and Cloudflare Access must be verified before serving real footage.

## Pi recorder

From the Mac, `bash pi/install.sh` installs root-owned scripts in `/opt/foxcam-pi`, the nonsecret `pi/foxcam.env` as `/etc/foxcam.env` only when missing, and the record/sync systemd units on `rob@10.0.2.138`. It uses key-only SSH and passwordless sudo. Reinstalls preserve the live Pi configuration and leave an active recorder running. Edit `/etc/foxcam.env` on the Pi to change tuning or schedules; reinstall to regenerate the timer from that live configuration, and restart the recorder when ready to apply changed exposure values. `START_TIME` and `STOP_TIME` must be distinct HH:MM values; the installer writes the actual start time and `Europe/London` timezone into the record timer drop-in. The recorder starts on its evening timer, 30 seconds after boot, or 30 seconds after the timer itself activates (including when clock sync delays activation), waits for the enabled `systemd-time-wait-sync.service` before starting, exits successfully outside the recording window, and stops itself at the local stop boundary. With `ALWAYS_ON=1` in `/etc/foxcam.env` it ignores the window and records around the clock; set `SHUTTER_US=0` and `GAIN=0` for automatic exposure so daytime is not blown out. Systemd restarts failures after ten seconds and terminates the process group when stopping the service.

Recordings are 1280×720 H.264 at 10 fps, with `--inline --intra 10` for a keyframe every second. The indoor defaults are `SHUTTER_US=20000`, `GAIN=4`, and fixed `AWB_GAINS=1.0,1.0` (a monochrome IR starting value); calibrate them with the installed 850 nm IR flood. Fixed white-balance gains prevent automatic white-balance hunting from appearing as whole-frame motion. Each segment captures at most 300 seconds, or the remaining time before `STOP_TIME`. The raw H.264 and remux output stay hidden until ffmpeg finishes; a final rename publishes a UTC timestamp MP4 under `/home/rob/foxcam-recordings`. Interruption never publishes the partial segment, and existing capture names are never overwritten. There is a short capture gap while each segment remuxes; continuous recording is not claimed.

Sync runs every fifteen minutes, selects only visible MP4s, removes sources only after rsync succeeds, and deletes recordings older than seven days even when transfer fails. `vps/install.sh --provision` creates `/home/rob/.ssh/foxcam_ed25519` on the Pi and restricts its VPS receiver to `/data/foxcam/incoming`; `sync.sh` uses destination `VPS_HOST:./` inside that namespace. The VPS host key is pinned through the Mac's existing authenticated SSH connection and sync enforces strict host checking. Missing keys fail locally before SSH. The Pi installer neither creates nor replaces the transfer key and can be rerun after VPS setup.

```sh
ssh -o BatchMode=yes rob@10.0.2.138 'sudo -n /opt/foxcam-pi/check.sh timers'
ssh -o BatchMode=yes rob@10.0.2.138 'sudo -n /opt/foxcam-pi/check.sh capture'
ssh -o BatchMode=yes rob@10.0.2.138 'sudo -n /opt/foxcam-pi/check.sh sync-failure'
```

The capture check temporarily stops and later restores the recorder/timer, records five minutes as `rob` in a temporary directory, checks codec/size/rate and keyframe spacing, decodes the whole segment, interrupts a second capture, and tests a short scheduled stop boundary. Move something in front of the indoor camera during the five-minute recording; the check verifies recording mechanics, not animal detection. The sync-failure check uses only localhost port 1 and an empty test identity, verifying refusal, an unchanged recent recording, and eight-day cleanup. The timer check covers the October 2026 BST/GMT transition and distinct UTC names during the repeated local hour.

## VPS provisioning and activation

Run from the Mac with key-authenticated SSH to the Pi and `root@62.238.55.235`:

```sh
bash vps/install.sh --check
bash vps/install.sh --provision
ssh -o BatchMode=yes root@62.238.55.235 'bash /opt/foxcam/vps/check.sh storage && bash /opt/foxcam/vps/check.sh pipeline'
```

`--check` is read-only. Provisioning requires `/data` to be mounted. Only on the first install, it removes the approved `/data/mt-data`, `/data/tmp`, and obsolete `agent` account/home, preserving `lost+found` and rejecting unexpected top-level entries. Once `/data/foxcam` exists, destructive initialization is skipped. Provisioning preserves recordings and existing secrets, installs ffmpeg/venv/rsync/cron and the package under `/opt/foxcam`, and stages the cron file there without activating it. It does not install public-facing web services or alter SSH/Fail2ban policy. The restricted Pi key permits only rsync uploads to the incoming directory; arbitrary SSH commands must fail.

The only mode that uses 1Password is the following separate operator step. Run it in the authenticated Mac shell, then relay its result:

```sh
bash vps/install.sh --secrets
```

It resolves the three vault references with `op read` inside a child process, quotes their values, and sends them over SSH stdin. No API keys enter arguments, logs, parent-shell exports, or local plaintext files. The VPS atomically replaces `/etc/foxcam.env` as root, mode 600. Before this step, that file contains only the nonsecret template; `check.sh storage` reports `secrets=pending` and `cron=disabled`. This is a provisioning result, not a claim that real-model processing is ready.

After the operator confirms secrets installation, process the queued real indoor segment and inspect its sidecar, annotation and site before enabling the cron job:

```sh
ssh -o BatchMode=yes root@62.238.55.235 'flock -n /run/lock/foxcam.lock /opt/foxcam/vps/run.sh'
bash vps/install.sh --enable-cron
```

Activation checks that the required keys are present and reruns the synthetic pipeline/lock check before installing `/etc/cron.d/foxcam`. Its exact schedule is `*/5 * * * * root /usr/bin/flock -n /run/lock/foxcam.lock /opt/foxcam/vps/run.sh`. The wrapper checks `mountpoint -q /data` before reading config or creating logs; the pipeline additionally requires its data directory to exist and meet `MIN_FREE_GB`. Run logs are `/data/foxcam/logs/YYYY-MM-DDTHH-MM-SSZ.log`. Reprovisioning leaves cron activation unchanged. Caddy and cloudflared package installation does not enroll a tunnel; complete the Access steps below before publication.

Provisioning verified on 2026-09-28: approved cleanup freed `/data` from 8.3G available (`df -h`) to 46.40 GiB; a second install preserved the night sentinel checksum. Storage, synthetic pipeline and overlap-lock checks passed. The restricted Pi key rejected `id` and transferred indoor `2026-09-28T16-36-33Z.mp4` (299.7 seconds, 125307516 bytes); SHA-256 `58bc584ea4d7420d6346a4c92bb72741c4a5393020a4796c1daf36445c94fc9f` matched before sync removed the Pi source. At that checkpoint the segment awaited processing, secrets were pending and cron was disabled. The operator subsequently installed secrets and ran the pipeline; generated indoor night pages/media are now present and cron is installed. Task 9 leaves that processing configuration unchanged.

## Local serving and private publication

Deploy serving files and packages without touching the Python environment, Pi, provider secrets or cron:

```sh
bash vps/install.sh --serving
ssh -o BatchMode=yes root@62.238.55.235 'bash /opt/foxcam/vps/check.sh serving'
```

Later `--provision` deploys also install these serving files; neither mode runs `publish.sh`. Packages come from the signed [Caddy repository](https://caddyserver.com/docs/install#debian-ubuntu-raspbian) and [Cloudflare repository](https://pkg.cloudflare.com/). Caddy is pinned to its official repository because Ubuntu Pro's ESM priority otherwise selects Ubuntu's build. The package's first start uses the committed Caddyfile, so its default public listener is never used.

Caddy binds only `127.0.0.1:8080`, accepts the tunnel's `foxwatch.cynexia.com` Host header, serves `/data/foxcam/site` at `/` and strips `/nights/` before serving `/data/foxcam/nights`. Directory browsing and the Caddy admin API are off. Configuration is validated before restart. Caddy serves only the configured site and nights roots using existing file modes; `/etc/foxcam.env` remains root-only. No inbound firewall rules or Fail2ban settings are changed. The serving check compares a real JPEG and annotated MP4 with their on-disk bytes; it verifies local service only, not Access protection.

Complete these account-dependent steps in this order:

1. In [Cloudflare Zero Trust → Access controls → Applications](https://one.dash.cloudflare.com/), create or reuse a self-hosted application named **Fox Watch**, with public hostname **foxwatch.cynexia.com**, no path restriction (all paths, including `/nights/*`). Add one **Allow** policy with **Include → Emails → your actual email address**. Choose your identity provider or email one-time PIN. Do not add Everyone, Bypass, or a separate public-media policy; remove conflicting more-specific applications. Save the application before routing the tunnel. Follow [Cloudflare's self-hosted application instructions](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/).
2. From the Mac, start login on the VPS and open its printed link in your browser; select **cynexia.com** and authorize. The certificate is saved on the VPS, not the Mac:

```sh
ssh -t root@62.238.55.235 'umask 077; cloudflared tunnel login'
```

3. After confirming the saved email-only Access policy covers the entire hostname, publish from the VPS:

```sh
ssh -o BatchMode=yes root@62.238.55.235 'bash /opt/foxcam/vps/publish.sh --access-ready'
ssh -o BatchMode=yes root@62.238.55.235 'systemctl is-active cloudflared && cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate'
```

`--access-ready` is the operator's assertion that the policy exists; the script does not create or inspect Access policies. It creates/reuses the locally managed `foxwatch` tunnel, keeps `/etc/cloudflared/foxwatch.json` and `config.yml` root-only, installs its systemd service, and creates/reuses the DNS route. Ingress sends only `foxwatch.cynexia.com` to `http://127.0.0.1:8080`, with a final `http_status:404`. Reruns preserve credentials and refuse conflicting DNS records or an unrelated cloudflared service. If the tunnel already exists but its local credentials were lost, restore those credentials before rerunning; the script never rotates them silently.

4. From the Mac, verify unauthenticated requests return an Access login redirect or denial, never page/media bytes. Do not use `-L`, cookies, or service credentials. Test the actual JPEG/MP4 URLs printed by `check.sh serving`, then open the page in a private browser window and sign in using the allowed email; check labels, arrows, images and H.264 playback:

```sh
curl -sS -o /dev/null -D - https://foxwatch.cynexia.com/
curl -sS -o /dev/null -D - https://foxwatch.cynexia.com/nights/2026-09-27/16-37-04.f0.jpg
curl -sS -o /dev/null -D - https://foxwatch.cynexia.com/nights/2026-09-27/16-37-04.annotated.mp4
```

A 200/206 response without authentication is a failed privacy check; stop `cloudflared` until the policy is corrected. A missing page, tunnel error or DNS failure is not proof that Access works. Tunnel enrolment, DNS, Access and authenticated browser playback remain unverified until these manual steps succeed. Installing cloudflared alone creates no tunnel.

## Outdoor acceptance and choosing a model

After mounting the camera 2–3 metres high at the fence and offsetting the 850 nm flood from the lens, adjust `SHUTTER_US`, `GAIN`, and fixed `AWB_GAINS` in the Pi’s `/etc/foxcam.env` against the actual night view. Keep the near field from clipping, retain detail at the far edge, and keep automatic exposure/white balance off. Reinstall with `bash pi/install.sh`; inspect the first real clips and tune `MIN_BLOB_AREA`, `GAP_SECONDS`, `PAD_SECONDS`, and `EDGE_MARGIN` as needed. Make VPS config changes in `vps/foxcam.env.example` and ship them with `bash vps/install.sh --secrets`, which regenerates `/etc/foxcam.env` from the template plus the vault keys; ship code changes with `bash vps/install.sh --provision` or serving-only changes with `bash vps/install.sh --serving`.

Walk across the garden patch after dark, allow recording/sync/processing to finish, and inspect the annotated clip, species label, entry/exit edges, and map arrows in the protected page. Synthetic and indoor checks prove mechanics, not outdoor infrared accuracy. Hand-check roughly 200 retained animal frames, then compare model agreement and inspect disagreements before changing `PRIMARY_MODEL`:

```sh
ssh -o BatchMode=yes root@62.238.55.235 'bash -c "set -a; source /etc/foxcam.env; set +a; exec /opt/foxcam/.venv/bin/python -m foxcam compare --data /data/foxcam"'
```

Agreement is against the chosen primary, not ground truth. The garden walkthrough and manual animal labels remain hardware acceptance work; no outdoor accuracy is claimed from today's software checks.

Local serving verified on 2026-09-28 with official Caddy 2.11.4 and cloudflared 2026.9.3: Fox Watch page and the two indoor media URLs above passed; both media responses matched disk bytes. Only loopback 8080 was added, directory browsing is off, Caddy serves only its configured roots, and SSH/Fail2ban remain active. Serving-only reinstall passed. No tunnel configuration/service was created and `publish.sh` was not run; Access and browser checks remain manual.
