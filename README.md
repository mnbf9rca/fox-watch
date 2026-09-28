# Fox Watch

Offline garden-camera processing for Python 3.12+: scan motion, cut visits, track edges, classify four frames, annotate H.264 clips, and generate static night pages. Requires `ffmpeg` and `ffprobe` on the path. Pi recording is installed with the scripts below; VPS provisioning, pipeline scheduling, and private web publishing are later plan tasks.

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

`compare` needs configuration but no secrets and makes no network calls. It prints agreement counts against `PRIMARY_MODEL`, excluding missing or unclassified answers; an empty denominator is `n/a`. `run` requires keys only for providers in `MODELS`. Its default data directory is `/data/foxcam`. Use one process at a time; VPS scheduling will provide `flock` in Task 8.

Outputs live in `nights/YYYY-MM-DD/`: raw and annotated clips, `.f0.jpg` through `.f3.jpg`, and JSON sidecars. `site/index.html` lists all nights; individual pages link to media under `/nights/`. A web server must map `/` to `site/` and `/nights/` to `nights/`; opening HTML directly from disk does not resolve those absolute media URLs. `--night` restricts processing and retention, while the index still includes all nights. Empty selected/current nights also get pages.

Clip names use the source UTC timestamp plus the unpadded motion offset. Sidecar timestamps record the requested padded start; duration is probed from the actual cut. Stream copying rounds boundaries to keyframes, so padding and timestamps are approximate at that granularity. Visits split at recording boundaries; cross-file merging is deferred. Nights use the local evening date, `START_TIME`, and `TZ`, including DST; clip names stay in UTC.

## Recovery, retention, and tuning

Existing cuts, frames, and sidecars are reused. Missing or unclassified model labels are retried; successful labels are retained. `annotation_label` records the last rendered primary label/confidence, so changing that answer refreshes the annotation once. Outputs use same-directory temporary files and atomic replacement. Source recordings are deleted once every event's cut and sidecar exist; raw event clips then carry recovery if classification or annotation has not finished. No-motion recordings are deleted after creating their night directory. Local file errors preserve available recovery media, allow independent inputs to continue, and return a nonzero exit status. Provider failures remain `unclassified` and do not fail the run.

`MIN_FREE_GB` is checked before processing. Completed raw event clips expire when their night is older than `RETAIN_NIGHTS`; all configured model labels, frames, and the current annotation must be complete first. Annotated clips, frames, and sidecars are retained. If the primary answer changes after raw expiration, the retained annotated clip is re-encoded to replace its caption; this adds one lossy generation. To rerun a successful classifier, remove just that model's answer from the sidecar's `labels` object; change `PRIMARY_MODEL` only to an entry in `MODELS`. Adding a model triggers classification from the retained frames. Removing a model preserves its historical answers.

The initial values in `vps/foxcam.env.example` are tuning defaults: `MIN_BLOB_AREA=100` at 320-pixel scan width, `EDGE_MARGIN=80` at full resolution, `GAP_SECONDS=3`, `PAD_SECONDS=2`, `START_TIME=19:00`, `STOP_TIME=07:00`, `TZ=Europe/London`, `RETAIN_NIGHTS=180`, and `MIN_FREE_GB=10`. Time settings also drive the later Pi recorder. Tune motion area against noise and animal size, gap against fragmented visits, padding against missed approach/departure, and edge margin against the installed camera view. Edge arrows are schematic, not calibrated ground positions.

The selected models and their observed fixture answers are documented in `tests/fixtures/SOURCES.md`. Together is excluded because its tested serverless option rejects multiple images and its VL alternatives require dedicated endpoints. Its URL and vault reference remain for a future compatible offering. Hosted fixture results do not establish outdoor infrared accuracy: after installation, walk across the patch, inspect the annotated clip and entry/exit edges, then hand-check roughly 200 retained frames before choosing the primary model. Pi/VPS deployment and Cloudflare Access must be verified before serving real footage.

## Pi recorder

From the Mac, `bash pi/install.sh` installs root-owned scripts in `/opt/foxcam-pi`, the nonsecret `pi/foxcam.env` as `/etc/foxcam.env`, and the record/sync systemd units on `rob@192.168.17.145`. It uses key-only SSH and passwordless sudo. Edit the committed Pi config and reinstall to change the schedule or exposure. `START_TIME` and `STOP_TIME` must be distinct HH:MM values; the installer writes the actual start time and `Europe/London` timezone into the record timer drop-in. The recorder starts on its evening timer or after boot, exits successfully outside the recording window, and stops itself at the local stop boundary. Systemd restarts failures after ten seconds and terminates the process group when stopping the service.

Recordings are 1280×720 H.264 at 10 fps, with `--inline --intra 10` for a keyframe every second. The indoor defaults are `SHUTTER_US=20000` and `GAIN=4`; calibrate them with the installed IR flood. Each segment captures at most 300 seconds, or the remaining time before `STOP_TIME`. The raw H.264 and remux output stay hidden until ffmpeg finishes; a final rename publishes a UTC timestamp MP4 under `/home/rob/foxcam-recordings`. Interruption never publishes the partial segment, and existing capture names are never overwritten. There is a short capture gap while each segment remuxes; continuous recording is not claimed.

Sync runs every fifteen minutes, selects only visible MP4s, removes sources only after rsync succeeds, and deletes recordings older than seven days even when transfer fails. The future transfer-key path `/home/rob/.ssh/foxcam_ed25519` is only a placeholder in Task 7. Missing keys cause a local failure before SSH, so no VPS connection occurs yet. Task 8 creates that dedicated key and restricts its receiver to `/data/foxcam/incoming`; `sync.sh` uses destination `VPS_HOST:./` inside that restricted namespace. No VPS key is generated or installed by these Pi scripts. The Task 7 installer refuses an already-present transfer key to prevent unexpected VPS traffic; that safeguard must be revisited when enabling transfer in Task 8.

```sh
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh timers'
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh capture'
ssh -o BatchMode=yes rob@192.168.17.145 'sudo -n /opt/foxcam-pi/check.sh sync-failure'
```

The capture check temporarily stops and later restores the recorder/timer, records five minutes as `rob` in a temporary directory, checks codec/size/rate and keyframe spacing, decodes the whole segment, interrupts a second capture, and tests a short scheduled stop boundary. Move something in front of the indoor camera during the five-minute recording; the check verifies recording mechanics, not animal detection. The sync-failure check uses only localhost port 1 and an empty test identity, verifying refusal, an unchanged recent recording, and eight-day cleanup. The timer check covers the October 2026 BST/GMT transition and distinct UTC names during the repeated local hour.
