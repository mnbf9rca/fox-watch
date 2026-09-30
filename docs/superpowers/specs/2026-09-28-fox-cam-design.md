# fox-cam design

Date: 2026-09-28. Status: approved for planning.

## Purpose

Find out which animals visit an 8 by 8 metre patch of the garden overnight, and which edge of the patch each one entered and left through. Output is a browsable web page per local calendar day with an annotated clip per visit, a species label, entry and exit edges, and a top-down map of the patch with one arrow per visit.

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
VPS cron every 5 minutes under flock: scan -> cut -> track -> classify -> annotate -> site
Caddy (localhost) -> cloudflared tunnel -> Cloudflare Access -> browser
```

## Pi recorder

Files: `pi/record.sh`, `pi/foxcam-record.service`, `pi/foxcam-record.timer`, `pi/foxcam-sync.service`, `pi/foxcam-sync.timer`, `pi/foxcam.env`, `pi/install.sh`.

- `record.sh` runs `rpicam-vid` at 1280x720, 10 frames per second, H.264, segmented into 5 minute files named by UTC timestamp, for example `2026-09-28T19-05-00Z.mp4`. It writes to a temporary name and renames on segment close so rsync only sees complete files. Exposure and gain are fixed values from `foxcam.env`, set once by eye against the flood; auto exposure is off so the background subtractor sees a stable image.
- The record timer starts the service at `START_TIME` and stops it at `STOP_TIME` (fixed local times in `foxcam.env`). Sunset tables are out of scope.
- The sync timer runs every 5 minutes: `rsync --remove-source-files` from the recordings folder to `VPS_HOST:/data/foxcam/incoming/`. A file is deleted from the Pi only after the VPS confirms it.
- A daily job deletes recordings older than 7 days as the safety valve against a full SD card when the VPS is unreachable.
- systemd restarts the recorder 10 seconds after a crash.
- `install.sh` runs from the Mac over SSH: copies the files, installs the units, enables the timers.

## VPS pipeline

One Python package `foxcam` in `/opt/foxcam`, deployed by rsync from the repo. Dependencies: `opencv-python-headless`, `numpy`, `google-genai`, Python 3.14 standard library otherwise. `ffmpeg` on the path.

All data under `/data/foxcam`:

- `incoming/` raw 5 minute files from the Pi.
- `nights/YYYY-MM-DD/` per local calendar day (the directory name stays for compatibility): `HH-MM-SS.mp4` raw clip, `HH-MM-SS.annotated.mp4`, `HH-MM-SS.f0.jpg` to `.f3.jpg` frames, `HH-MM-SS.json` sidecar.
- `site/` generated HTML.
- `logs/` one log file per run.

Steps, each a function taking paths in and writing files out, each idempotent (skips work whose output exists):

1. **scan** Reads each incoming file with OpenCV, downscales to 320 wide, runs `BackgroundSubtractorMOG2`. A frame is motion when the largest contour exceeds `MIN_BLOB_AREA`. Consecutive motion frames with gaps up to `GAP_SECONDS` (default 3) form one event. Output: list of (file, start, end).
2. **cut** For each event, `ffmpeg -ss -to -c copy` with `PAD_SECONDS` (default 2) each side, into the local calendar-day folder in `TZ`. Days start at local midnight, independently of `START_TIME`; `night_for` keeps its name and returns the local capture date. Once every event in a source file is cut, the source file is deleted.
3. **track** Runs the same subtractor over the clip at full resolution and records the largest blob's bounding box and centroid per frame. Entry edge is the frame edge nearest the first centroid; exit edge the same for the last. Mapping: top of frame is `far`, bottom is `fence`, `left` and `right` as seen. A centroid further than `EDGE_MARGIN` pixels from every edge gives `unknown`. Saves 3 evenly spaced frames plus the largest-blob frame as JPEGs.
4. **classify** The model choice is not settled, so the step runs every model listed in `MODELS` and records each answer. Hosted models go through three providers the user already pays for: Nous (an OpenRouter reseller), DeepInfra and Together.ai. All three expose an OpenAI-compatible chat completions endpoint, so one client with a per-provider base URL and key covers them. A model is named `provider/model-id`, for example `deepinfra/Qwen/Qwen3-VL-32B-Instruct`. Each model gets the 4 JPEGs in one request with a prompt asking for exactly one label from `fox, hedgehog, cat, badger, rat, mouse, bird, deer, other, none` and a confidence 0 to 1, as JSON. Signature: `classify(model: str, frames: list[Path]) -> tuple[str, float]`. `PRIMARY_MODEL` names the one that drives the annotation and site; the others show alongside it on the day page so disagreements are visible. SpeciesNet, run locally, can be added later as another entry in `MODELS` behind the same signature. A failed call records `unclassified` for that model and the next run retries it. `python -m foxcam compare` prints per-model agreement over all sidecars so a winner can be picked once footage exists.
5. **annotate** Writes the annotated clip: bounding box per frame, label and confidence top left, track drawn as a growing polyline. OpenCV renders frames, ffmpeg encodes H.264 so browsers play it.
6. **site** Reads sidecars only. `site/index.html` lists local calendar days newest first with per-species counts. `site/YYYY-MM-DD.html` is a static grid: thumbnail (largest-blob frame), species, confidence, time, entry and exit edges, linking to the annotated clip. Each day page includes an inline SVG top-down map of the patch with one arrow per visit from entry edge to exit edge, coloured by species. A day with zero events still gets a page saying so.

All displayed page times use `TZ` with the zone abbreviation; the daytime filter still spans `STOP_TIME` to `START_TIME`. `python -m foxcam refile --data DIR` moves misfiled sidecars and their media to the date of `start_utc` in `TZ`, refuses existing destinations, updates the compatibility `night` field and rebuilds the site; rerunning after completion moves zero sidecars.

Sidecar JSON fields: `clip`, `night`, `start_utc`, `duration_s`, `entry_edge`, `exit_edge`, `labels` (map of model id to `{label, confidence}`), `track` (list of `[frame, x, y, w, h]`), `frames` (list of JPEG names).

Config: one `/etc/foxcam.env` holding `NOUS_API_KEY`, `DEEPINFRA_API_KEY`, `TOGETHER_API_KEY`, `MODELS` (comma separated `provider/model-id`), `PRIMARY_MODEL`, `DATA_DIR`, `MIN_BLOB_AREA`, `GAP_SECONDS`, `PAD_SECONDS`, `EDGE_MARGIN`, `RETAIN_NIGHTS` (default 180), `MIN_FREE_GB` (default 10). On the Mac, secrets are never exported into the shell: `.envrc` loads only a 1Password service account token, and commands run as `op run --env-file=.env.tpl -- ...` so keys exist only inside that child process. `.env.tpl` maps each variable to its vault reference: `op://foxwatch/nous/secret`, `op://foxwatch/deepinfra/api-key`, `op://foxwatch/together/api-key`. The VPS install script resolves the same references once with `op read` on the Mac and writes `/etc/foxcam.env` over SSH, mode 600.

Entry point: `python -m foxcam run [--night YYYY-MM-DD] [--data DIR]`. Cron runs it every 5 minutes under `flock -n` so overlapping runs are impossible and a slow run simply delays the next; it processes whatever is in `incoming` and updates the current day's page incrementally. It refuses to start if the data volume has under `MIN_FREE_GB` free and logs why. After processing it deletes raw clips older than `RETAIN_NIGHTS`; annotated clips, frames and sidecars are kept.

## Serving

- Caddy serves `/data/foxcam/site` and `/data/foxcam/nights` on `127.0.0.1:8080` only.
- `cloudflared` runs a named tunnel to that port. The site is called Fox Watch at `foxwatch.cynexia.com`. The DNS record and Access policy are created through the Cloudflare connector or the `cloudflared` CLI; the tunnel credentials file lives on the VPS only. Cloudflare Access policy restricts it to the user's email.
- Public firewall exposure stays SSH only. Fail2ban stays as found.
- `vps/install.sh` runs from the Mac over SSH: wipes `/data`, creates the layout, installs ffmpeg, Caddy, cloudflared and the Python package, writes the cron entry.

## Classifier choice and fallback

Research on 2026-09-28 found no published infrared benchmark for any hosted vision model, so the choice stays open and the pipeline runs several models side by side. The initial `MODELS` list is Gemini 2.5 Flash-Lite via Nous, Qwen3-VL-32B via DeepInfra, and one Llama or Qwen vision model via Together.ai, chosen from what each provider actually serves at build time. Gemini 2.5 Flash-Lite is the initial `PRIMARY_MODEL` because it is the only one with a published camera-trap accuracy figure. SpeciesNet (Google, Apache 2.0, includes MegaDetector, trained on infrared trail-camera frames, country filter for Great Britain) is the fallback, runnable on the VPS CPU at this volume. Every frame and label is kept so that once roughly 200 frames have been hand-checked, both can be measured on the same set.

## Storage budget

Per night at 30 events: raw 5 minute files 4 to 7 GB (deleted after cutting), raw clips 100 to 150 MB, annotated clips 100 to 200 MB, frames and sidecars about 20 MB. With 15 GB headroom for unprocessed raw files, the 50 GB volume holds roughly 100 nights. Compression and longer retention are deferred until the pipeline works.

## Testing and the hardware gap

The camera and flood are not installed yet, so real footage is days away. Everything is built and exercised now without it: a fixture generator makes a short synthetic 1280x720 video with a grey blob moving from the left edge to the top edge on a static noisy background, which drives scan, cut, track, annotate and site deterministically. The classifier step is exercised with a handful of public infrared camera-trap stills of a fox and a hedgehog checked into `tests/fixtures`. The Pi recorder is tested indoors now by pointing the camera at anything and waving at it. The first real end-to-end test is a clip of the user walking across the patch once the camera is up.

Kept minimal by request. The pipeline runs on the Mac against a folder of video. One small test module covers the pure logic: event merging, edge assignment, classifier JSON parsing, and site generation from fixture sidecars. ffmpeg and the classifier are exercised by running them, not mocked.

## Out of scope for the proof of concept

Sunset-based scheduling, ground-plane calibration, real-time alerts, on-Pi detection, video compression, multiple cameras, any database.

## Amendment 2026-09-29: per-object detection and tracking

Approved after the first day of street footage showed the largest-blob tracker merging a person and a dog into one box. The Pi and the scan, cut and site steps are unchanged in shape; the track and classify steps change as follows.

- **Detector.** On each cut clip, a COCO object detector (YOLOX from the OpenCV model zoo, Apache 2.0, pre-exported ONNX, run through `cv2.dnn`, no new Python dependency) runs on every second frame at 640 pixels. Its weights are downloaded once by the VPS installer into `/opt/foxcam/models` and by the Mac into a local models folder; the SHA-256 is pinned in the repo. The detector sits behind one function `detect(frame) -> list[(class, confidence, x, y, w, h)]` so MegaDetector can replace it later.
- **Tracker.** Detections are linked frame to frame by intersection over union within the same class; a track ends after ten consecutive misses. No Kalman filter, no re-identification. Each track carries its own boxes, entry edge and exit edge computed as today. Detector and fallback tracks are kept only when the diagonal of all centroid bounds is at least `MIN_TRACK_MOVE_RATIO` (default 0.75) times the mean `max(width, height)` of their boxes, with a 20 pixel absolute floor; this rejects parked-car jitter while retaining out-and-back visits. If a motion clip yields no detections, the existing largest-blob track is kept as a single fallback track with class `unknown`, so animals the detector does not know still get a box and a classifier call.
- **Classification per track.** Tracks whose detector class is person or a vehicle class are labelled `person` or `vehicle` directly and are never sent to a hosted model. Every other track is sent to each configured model with two images: the largest-box frame with that track's box drawn, and the box region cropped from that frame at full resolution. The prompt asks for a JSON object with `label` from `fox, hedgehog, cat, badger, rat, mouse, bird, deer, dog, person, vehicle, other, none` and a short free-text `description`. The wording no longer mentions infrared or a garden; it describes a fixed camera watching a patch of ground.
- **Sidecar.** Adds `tracks`: a list of `{id, class, labels, description, entry_edge, exit_edge, boxes}` where `labels` maps model id to `{label, confidence}` and `boxes` is `[[frame, x, y, w, h], ...]`. The existing top-level `entry_edge`, `exit_edge`, `labels` and `track` fields remain and mirror the primary track, which is the longest track, so the compare command and older pages keep working.
- **Annotation and map.** One box per track in its own colour with its label, each path drawn separately. Every annotated frame, including frames without tracks, shows a bottom-left timestamp formatted `YYYY-MM-DD HH:MM:SS UTC`, computed from `start_utc` plus frame index / fps. The map draws one arrow per track.
- **Page filter.** Each day page has a checkbox row, one per label with its count, that hides cards whose primary label is unticked. CSS only, no JavaScript.
- **Parallelism and throughput.** The VPS has 4 vCPUs. The pipeline processes clips in a process pool of `WORKERS` (default 4) with OpenCV limited to one thread per worker, so detection, cutting and annotation overlap across clips. Every run logs seconds of processing per minute of clip; the requirement is that this ratio stays below 1 on average so the five minute cron never accumulates a backlog. `check_pipeline.py` reports the measured ratio on the synthetic clip.
- **Not in scope.** Kalman filtering, re-identification, counting, blurring people, and detector fine-tuning.
