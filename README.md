# Fox Watch

Offline garden-camera processing for Python 3.12+: scan motion, cut visits, track edges, classify four frames, annotate H.264 clips, and generate static night pages. Requires `ffmpeg` and `ffprobe` on the path. Pi recording, VPS provisioning, scheduling, and private web publishing are later plan tasks.

## Local setup and checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/python tests/check_video.py
.venv/bin/python tests/check_pipeline.py
```

The default pipeline check needs no secrets and never calls a hosted provider: it uses a dummy credential and a refused localhost connection. It exercises the real CLI and video tools, interrupted-work recovery, classification retries, annotation changes, empty nights, input isolation, low-space refusal, retention, and comparison. `tests/check_transport.py` separately checks a truncated localhost HTTPS response and requires `openssl`.

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
