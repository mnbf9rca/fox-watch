# fox-cam design

Date: 2026-09-28. Status: approved for planning.

## Purpose

Find out which animals visit an 8 by 8 metre patch of the garden overnight, and which edge of the patch each one entered and left through. Output is a browsable web page per night with an annotated clip per visit, a species label, entry and exit edges, and a top-down map of the patch with one arrow per visit.

This is a proof of concept. Accuracy is measured by watching the annotated clips. If it works, hardware may move to a Raspberry Pi 5, AI HAT 2, and Camera Module 3 NoIR, at which point motion detection can move onto the Pi with the same VPS code.

## Hardware and placement

- Raspberry Pi 4 Model B, 8 GB, Raspberry Pi OS Lite 64 bit (Debian 13 Trixie), hostname `fox-watch`, reachable at `rob@192.168.17.145` on the garden Wi-Fi. Passwordless sudo, Wi-Fi power saving off, `rpicam-apps`, `rsync` and `ffmpeg` installed.
- Camera Module 2 NoIR (imx219), mounted on the fence at the middle of one side of the patch, 2 to 3 metres up, looking across the patch. The view on the ground is a trapezoid roughly 1.5 metres wide at the fence and 9 metres wide at the far edge.
- IR flood: 96 LED 850 nm array with built-in dusk sensor, 12 V. Mount offset from the lens, or higher and aimed at the far half, so the near field does not blow out.
- VPS: Hetzner, Ubuntu 26.04, 4 CPUs, 8 GB, `root@62.238.55.235`. 50 GB data volume mounted at `/data`. Only SSH is exposed publicly. The volume's previous contents (`mt-data`, `tmp`) and the leftover `agent` user are deleted during install; the user has approved this.

## Architecture

Approach C: the Pi is a dumb recorder. All detection, tracking, classification and presentation run on the VPS. Reason: motion thresholds decide what is kept, and tuning them against full nights of real footage on a Mac is safer than tuning blind on the Pi.

```
Pi: rpicam-vid (dusk to dawn, 5 min files) -> rsync every 15 min -> VPS /data/foxcam/incoming
VPS hourly cron under flock: scan -> cut -> track -> classify -> annotate -> site
Caddy (localhost) -> cloudflared tunnel -> Cloudflare Access -> browser
```

## Pi recorder

Files: `pi/record.sh`, `pi/foxcam-record.service`, `pi/foxcam-record.timer`, `pi/foxcam-sync.service`, `pi/foxcam-sync.timer`, `pi/foxcam.env`, `pi/install.sh`.

- `record.sh` runs `rpicam-vid` at 1280x720, 10 frames per second, H.264, segmented into 5 minute files named by UTC timestamp, for example `2026-09-28T19-05-00Z.mp4`. It writes to a temporary name and renames on segment close so rsync only sees complete files. Exposure and gain are fixed values from `foxcam.env`, set once by eye against the flood; auto exposure is off so the background subtractor sees a stable image.
- The record timer starts the service at `START_TIME` and stops it at `STOP_TIME` (fixed local times in `foxcam.env`). Sunset tables are out of scope.
- The sync timer runs every 15 minutes: `rsync --remove-source-files` from the recordings folder to `VPS_HOST:/data/foxcam/incoming/`. A file is deleted from the Pi only after the VPS confirms it.
- A daily job deletes recordings older than 7 days as the safety valve against a full SD card when the VPS is unreachable.
- systemd restarts the recorder 10 seconds after a crash.
- `install.sh` runs from the Mac over SSH: copies the files, installs the units, enables the timers.

## VPS pipeline

One Python package `foxcam` in `/opt/foxcam`, deployed by rsync from the repo. Dependencies: `opencv-python-headless`, `numpy`, `google-genai`, Python 3.14 standard library otherwise. `ffmpeg` on the path.

All data under `/data/foxcam`:

- `incoming/` raw 5 minute files from the Pi.
- `nights/YYYY-MM-DD/` per night: `HH-MM-SS.mp4` raw clip, `HH-MM-SS.annotated.mp4`, `HH-MM-SS.f0.jpg` to `.f3.jpg` frames, `HH-MM-SS.json` sidecar.
- `site/` generated HTML.
- `logs/` one log file per run.

Steps, each a function taking paths in and writing files out, each idempotent (skips work whose output exists):

1. **scan** Reads each incoming file with OpenCV, downscales to 320 wide, runs `BackgroundSubtractorMOG2`. A frame is motion when the largest contour exceeds `MIN_BLOB_AREA`. Consecutive motion frames with gaps up to `GAP_SECONDS` (default 3) form one event. Output: list of (file, start, end).
2. **cut** For each event, `ffmpeg -ss -to -c copy` with `PAD_SECONDS` (default 2) each side, into the night folder. A night runs from the evening start time to the morning stop time and is named by the evening's date. Once every event in a source file is cut, the source file is deleted.
3. **track** Runs the same subtractor over the clip at full resolution and records the largest blob's bounding box and centroid per frame. Entry edge is the frame edge nearest the first centroid; exit edge the same for the last. Mapping: top of frame is `far`, bottom is `fence`, `left` and `right` as seen. A centroid further than `EDGE_MARGIN` pixels from every edge gives `unknown`. Saves 3 evenly spaced frames plus the largest-blob frame as JPEGs.
4. **classify** The model choice is not settled, so the step runs every model listed in `MODELS` and records each answer. Hosted models go through OpenRouter, one client and one API key for Gemini, Qwen, GPT and others; a model is named by its OpenRouter id. Each model gets the 4 JPEGs in one request with a prompt asking for exactly one label from `fox, hedgehog, cat, badger, rat, mouse, bird, deer, other, none` and a confidence 0 to 1, as JSON. Signature: `classify(model: str, frames: list[Path]) -> tuple[str, float]`. `PRIMARY_MODEL` names the one that drives the annotation and site; the others show alongside it on the night page so disagreements are visible. SpeciesNet, run locally, can be added later as another entry in `MODELS` behind the same signature. A failed call records `unclassified` for that model and the next run retries it. `python -m foxcam compare` prints per-model agreement over all sidecars so a winner can be picked once footage exists.
5. **annotate** Writes the annotated clip: bounding box per frame, label and confidence top left, track drawn as a growing polyline. OpenCV renders frames, ffmpeg encodes H.264 so browsers play it.
6. **site** Reads sidecars only. `site/index.html` lists nights newest first with per-species counts. `site/YYYY-MM-DD.html` is a static grid: thumbnail (largest-blob frame), species, confidence, time, entry and exit edges, linking to the annotated clip. Each night page includes an inline SVG top-down map of the patch with one arrow per visit from entry edge to exit edge, coloured by species. A night with zero events still gets a page saying so.

Sidecar JSON fields: `clip`, `night`, `start_utc`, `duration_s`, `entry_edge`, `exit_edge`, `labels` (map of model id to `{label, confidence}`), `track` (list of `[frame, x, y, w, h]`), `frames` (list of JPEG names).

Config: one `/etc/foxcam.env` holding `OPENROUTER_API_KEY`, `MODELS` (comma separated OpenRouter ids), `PRIMARY_MODEL`, `DATA_DIR`, `MIN_BLOB_AREA`, `GAP_SECONDS`, `PAD_SECONDS`, `EDGE_MARGIN`, `RETAIN_NIGHTS` (default 180), `MIN_FREE_GB` (default 10). Same file is read when running on the Mac with `DATA_DIR` pointing at a local folder.

Entry point: `python -m foxcam run [--night YYYY-MM-DD] [--data DIR]`. Cron runs it hourly under `flock -n` so overlapping runs are impossible and a slow run simply delays the next; it processes whatever is in `incoming` and updates the current night's page incrementally. It refuses to start if the data volume has under `MIN_FREE_GB` free and logs why. After processing it deletes raw clips older than `RETAIN_NIGHTS`; annotated clips, frames and sidecars are kept.

## Serving

- Caddy serves `/data/foxcam/site` and `/data/foxcam/nights` on `127.0.0.1:8080` only.
- `cloudflared` runs a named tunnel to that port. The site is called Fox Watch; the hostname is `foxwatch` under a domain the user will name, set in the install config. Cloudflare Access policy restricts it to the user's email.
- Public firewall exposure stays SSH only. Fail2ban stays as found.
- `vps/install.sh` runs from the Mac over SSH: wipes `/data`, creates the layout, installs ffmpeg, Caddy, cloudflared and the Python package, writes the cron entry.

## Classifier choice and fallback

Research on 2026-09-28 found no published infrared benchmark for any hosted vision model, so the choice stays open and the pipeline runs several models side by side. The initial `MODELS` list is Gemini 2.5 Flash-Lite, Qwen3-VL-32B and GPT-4o-mini (low detail), all via OpenRouter, together well under $3 a month at 30 clips a night. Gemini 2.5 Flash-Lite is the initial `PRIMARY_MODEL` because it is the only one with a published camera-trap accuracy figure. SpeciesNet (Google, Apache 2.0, includes MegaDetector, trained on infrared trail-camera frames, country filter for Great Britain) is the fallback, runnable on the VPS CPU at this volume. Every frame and label is kept so that once roughly 200 frames have been hand-checked, both can be measured on the same set.

## Storage budget

Per night at 30 events: raw 5 minute files 4 to 7 GB (deleted after cutting), raw clips 100 to 150 MB, annotated clips 100 to 200 MB, frames and sidecars about 20 MB. With 15 GB headroom for unprocessed raw files, the 50 GB volume holds roughly 100 nights. Compression and longer retention are deferred until the pipeline works.

## Testing and the hardware gap

The camera and flood are not installed yet, so real footage is days away. Everything is built and exercised now without it: a fixture generator makes a short synthetic 1280x720 video with a grey blob moving from the left edge to the top edge on a static noisy background, which drives scan, cut, track, annotate and site deterministically. The classifier step is exercised with a handful of public infrared camera-trap stills of a fox and a hedgehog checked into `tests/fixtures`. The Pi recorder is tested indoors now by pointing the camera at anything and waving at it. The first real end-to-end test is a clip of the user walking across the patch once the camera is up.

Kept minimal by request. The pipeline runs on the Mac against a folder of video. One small test module covers the pure logic: event merging, edge assignment, classifier JSON parsing, and site generation from fixture sidecars. ffmpeg and the classifier are exercised by running them, not mocked.

## Out of scope for the proof of concept

Sunset-based scheduling, ground-plane calibration, real-time alerts, on-Pi detection, video compression, multiple cameras, any database.
