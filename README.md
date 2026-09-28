# Fox Watch

Offline garden-camera processing for Python 3.12+: scan motion, cut visits, track edges, classify four frames, annotate H.264 clips, and generate static night pages. Requires `ffmpeg` and `ffprobe` on the path. Pi recording and VPS provisioning are installed with the scripts below; hourly processing remains disabled until secrets are confirmed, and private web publishing is a later plan task.

## Local setup and checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python tests/check_video.py
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

Outputs live in `nights/YYYY-MM-DD/`: raw and annotated clips, `.f0.jpg` through `.f3.jpg`, and JSON sidecars. `site/index.html` lists all nights; individual pages link to media under `/nights/`. A web server must map `/` to `site/` and `/nights/` to `nights/`; opening HTML directly from disk does not resolve those absolute media URLs. `--night` restricts processing and retention, while the index still includes all nights. Empty selected/current nights also get pages.

Clip names use the source UTC timestamp plus the unpadded motion offset. Sidecar timestamps record the requested padded start; duration is probed from the actual cut. Stream copying rounds boundaries to keyframes, so padding and timestamps are approximate at that granularity. Visits split at recording boundaries; cross-file merging is deferred. Nights use the local evening date, `START_TIME`, and `TZ`, including DST; clip names stay in UTC.

## Recovery, retention, and tuning

Existing cuts, frames, and sidecars are reused. Missing or unclassified model labels are retried; successful labels are retained. `annotation_label` records the last rendered primary label/confidence, so changing that answer refreshes the annotation once. Outputs use same-directory temporary files and atomic replacement. Source recordings are deleted once every event's cut and sidecar exist; raw event clips then carry recovery if classification or annotation has not finished. No-motion recordings are deleted after creating their night directory. Local file errors preserve available recovery media, allow independent inputs to continue, and return a nonzero exit status. Provider failures remain `unclassified` and do not fail the run.

`MIN_FREE_GB` is checked on the data directory itself before processing; a missing data directory fails without creating anything. Completed raw event clips expire when their night is older than `RETAIN_NIGHTS`; all configured model labels, frames, and the current annotation must be complete first. Annotated clips, frames, and sidecars are retained. If the primary answer changes after raw expiration, the retained annotated clip stays unchanged and `annotation_label` records the desired answer so later runs move on; the site/sidecar answer may therefore be newer than the burned-in caption. To rerun a successful classifier, remove just that model's answer from the sidecar's `labels` object; change `PRIMARY_MODEL` only to an entry in `MODELS`. Adding a model triggers classification from the retained frames. Removing a model preserves its historical answers.

The initial values in `vps/foxcam.env.example` are tuning defaults: `MIN_BLOB_AREA=100` at 320-pixel scan width, `EDGE_MARGIN=80` at full resolution, `GAP_SECONDS=3`, `PAD_SECONDS=2`, `START_TIME=19:00`, `STOP_TIME=07:00`, `TZ=Europe/London`, `RETAIN_NIGHTS=180`, and `MIN_FREE_GB=10`. Time settings also drive the later Pi recorder. Tune motion area against noise and animal size, gap against fragmented visits, padding against missed approach/departure, and edge margin against the installed camera view. Edge arrows are schematic, not calibrated ground positions.

The selected models and their observed fixture answers are documented in `tests/fixtures/SOURCES.md`. Together is excluded because its tested serverless option rejects multiple images and its VL alternatives require dedicated endpoints. Its URL and vault reference remain for a future compatible offering. Hosted fixture results do not establish outdoor infrared accuracy: after installation, walk across the patch, inspect the annotated clip and entry/exit edges, then hand-check roughly 200 retained frames before choosing the primary model. Pi/VPS deployment and Cloudflare Access must be verified before serving real footage.

## Pi recorder

From the Mac, `bash pi/install.sh` installs root-owned scripts in `/opt/foxcam-pi`, the nonsecret `pi/foxcam.env` as `/etc/foxcam.env`, and the record/sync systemd units on `rob@192.168.17.145`. It uses key-only SSH and passwordless sudo. Edit the committed Pi config and reinstall to change the schedule or exposure. `START_TIME` and `STOP_TIME` must be distinct HH:MM values; the installer writes the actual start time and `Europe/London` timezone into the record timer drop-in. The recorder starts on its evening timer or after boot, waits for the enabled `systemd-time-wait-sync.service` before starting, exits successfully outside the recording window, and stops itself at the local stop boundary. Systemd restarts failures after ten seconds and terminates the process group when stopping the service.

Recordings are 1280×720 H.264 at 10 fps, with `--inline --intra 10` for a keyframe every second. The indoor defaults are `SHUTTER_US=20000`, `GAIN=4`, and fixed `AWB_GAINS=1.0,1.0` (a monochrome IR starting value); calibrate them with the installed 850 nm IR flood. Fixed white-balance gains prevent automatic white-balance hunting from appearing as whole-frame motion. Each segment captures at most 300 seconds, or the remaining time before `STOP_TIME`. The raw H.264 and remux output stay hidden until ffmpeg finishes; a final rename publishes a UTC timestamp MP4 under `/home/rob/foxcam-recordings`. Interruption never publishes the partial segment, and existing capture names are never overwritten. There is a short capture gap while each segment remuxes; continuous recording is not claimed.

Sync runs every fifteen minutes, selects only visible MP4s, removes sources only after rsync succeeds, and deletes recordings older than seven days even when transfer fails. `vps/install.sh --provision` creates `/home/rob/.ssh/foxcam_ed25519` on the Pi and restricts its VPS receiver to `/data/foxcam/incoming`; `sync.sh` uses destination `VPS_HOST:./` inside that namespace. The VPS host key is pinned through the Mac's existing authenticated SSH connection and sync enforces strict host checking. Missing keys fail locally before SSH. The Pi installer neither creates nor replaces the transfer key and can be rerun after VPS setup.

```sh
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh timers'
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh capture'
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh sync-failure'
```

The capture check temporarily stops and later restores the recorder/timer, records five minutes as `rob` in a temporary directory, checks codec/size/rate and keyframe spacing, decodes the whole segment, interrupts a second capture, and tests a short scheduled stop boundary. Move something in front of the indoor camera during the five-minute recording; the check verifies recording mechanics, not animal detection. The sync-failure check uses only localhost port 1 and an empty test identity, verifying refusal, an unchanged recent recording, and eight-day cleanup. The timer check covers the October 2026 BST/GMT transition and distinct UTC names during the repeated local hour.

## VPS provisioning and activation

Run from the Mac with key-authenticated SSH to the Pi and `root@62.238.55.235`:

```sh
bash vps/install.sh --check
bash vps/install.sh --provision
ssh -o BatchMode=yes root@62.238.55.235 'bash /opt/foxcam/vps/check.sh storage && bash /opt/foxcam/vps/check.sh pipeline'
```

`--check` is read-only. Provisioning requires `/data` to be mounted. Only on the first install, it removes the approved `/data/mt-data`, `/data/tmp`, and obsolete `agent` account/home, preserving `lost+found` and rejecting unexpected top-level entries. Once `/data/foxcam` exists, destructive initialization is skipped. Provisioning preserves recordings and existing secrets, installs ffmpeg/venv/rsync/cron and the package under `/opt/foxcam`, and stages the hourly cron file there without activating it. It does not install public-facing web services or alter SSH/Fail2ban policy. The restricted Pi key permits only rsync uploads to the incoming directory; arbitrary SSH commands must fail.

The only mode that uses 1Password is the following separate operator step. Run it in the authenticated Mac shell, then relay its result:

```sh
bash vps/install.sh --secrets
```

It resolves the three vault references with `op read` inside a child process, quotes their values, and sends them over SSH stdin. No API keys enter arguments, logs, parent-shell exports, or local plaintext files. The VPS atomically replaces `/etc/foxcam.env` as root, mode 600. Before this step, that file contains only the nonsecret template; `check.sh storage` reports `secrets=pending` and `hourly_cron=disabled`. This is a provisioning result, not a claim that real-model processing is ready.

After the operator confirms secrets installation, process the queued real indoor segment and inspect its sidecar, annotation and site before enabling the hourly job:

```sh
ssh -o BatchMode=yes root@62.238.55.235 'flock -n /run/lock/foxcam.lock /opt/foxcam/vps/run.sh'
bash vps/install.sh --enable-cron
```

Activation checks that the required keys are present and reruns the synthetic pipeline/lock check before installing `/etc/cron.d/foxcam`. Its exact schedule is `0 * * * * root /usr/bin/flock -n /run/lock/foxcam.lock /opt/foxcam/vps/run.sh`. The wrapper checks `mountpoint -q /data` before reading config or creating logs; the pipeline additionally requires its data directory to exist and meet `MIN_FREE_GB`. Hourly logs are `/data/foxcam/logs/YYYY-MM-DDTHH-MM-SSZ.log`. Reprovisioning leaves cron activation unchanged. Caddy, cloudflared and Cloudflare Access remain Task 9; do not expose the generated site publicly before that protection is verified.

Provisioning verified on 2026-09-28: approved cleanup freed `/data` from 8.3G available (`df -h`) to 46.40 GiB; a second install preserved the night sentinel checksum. Storage, synthetic pipeline and overlap-lock checks passed. The restricted Pi key rejected `id` and transferred indoor `2026-09-28T16-36-33Z.mp4` (299.7 seconds, 125307516 bytes); SHA-256 `58bc584ea4d7420d6346a4c92bb72741c4a5393020a4796c1daf36445c94fc9f` matched before sync removed the Pi source. The segment awaits processing in `/data/foxcam/incoming`, with 46.28 GiB free. Secrets installation, real-model processing and hourly activation remain pending the operator step above.
