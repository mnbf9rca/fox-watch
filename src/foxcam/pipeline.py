from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import shutil
import time as clock
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import cv2

from foxcam.classify import classify
from foxcam.detect import VEHICLES
from foxcam.events import clip_name, night_for
from foxcam.media import annotate, cut, duration, scan, track
from foxcam.site import build_site, render_night


BASE_URLS = dict(nous="https://inference-api.nousresearch.com/v1",
                 deepinfra="https://api.deepinfra.com/v1/openai", together="https://api.together.ai/v1")


def load_config() -> dict:
    config = {"DATA_DIR": Path(os.environ.get("DATA_DIR", "/data/foxcam")),
              "MODELS": os.environ.get("MODELS", "").split(","),
              "PRIMARY_MODEL": os.environ.get("PRIMARY_MODEL", ""),
              "TZ": ZoneInfo(os.environ.get("TZ", "Europe/London"))}
    for name, default in dict(GAP_SECONDS=3, PAD_SECONDS=2, MIN_BLOB_AREA=100,
                              EDGE_MARGIN=80, MIN_FREE_GB=10).items():
        config[name] = float(os.environ.get(name, default))
        if not math.isfinite(config[name]) or config[name] < 0:
            raise ValueError(f"{name} must be finite and nonnegative")
    config["RETAIN_NIGHTS"] = int(os.environ.get("RETAIN_NIGHTS", "180"))
    if config["RETAIN_NIGHTS"] < 0:
        raise ValueError("RETAIN_NIGHTS must be nonnegative")
    config["WORKERS"] = int(os.environ.get("WORKERS", "4"))
    if config["WORKERS"] < 1:
        raise ValueError("WORKERS must be at least 1")
    for name, default in (("START_TIME", "19:00"), ("STOP_TIME", "07:00")):
        config[name] = time.fromisoformat(os.environ.get(name, default))
        if config[name].tzinfo is not None:
            raise ValueError(f"{name} must be a local time")
    if config["START_TIME"] == config["STOP_TIME"]:
        raise ValueError("START_TIME and STOP_TIME must differ")
    for provider, default in BASE_URLS.items():
        name = provider.upper() + "_BASE_URL"
        config[name] = os.environ.get(name, default)
        url = urlsplit(config[name])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError(f"{name} must be an HTTPS base URL without credentials, query or fragment")
    for model in config["MODELS"]:
        provider, separator, model_id = model.partition("/")
        if provider not in BASE_URLS or not separator or not model_id:
            raise ValueError("MODELS must contain provider/model-id entries")
    if config["PRIMARY_MODEL"] not in config["MODELS"]:
        raise ValueError("PRIMARY_MODEL must appear in MODELS")
    return config


def _save(path, row):
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(row, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_sidecar(path: Path, primary_model: str) -> dict:
    row = json.loads(path.read_text())
    # Reuse the renderer's schema/path checks before following any media references.
    render_night(path.parent.name, [row], primary_model)
    if row["clip"] != path.stem + ".mp4" or row["frames"] != [f"{path.stem}.f{i}.jpg" for i in range(4)]:
        raise ValueError("Sidecar media names do not match its basename")
    return row


UNCLASSIFIED = {"label": "unclassified", "confidence": 0.0}


def _init_worker():
    cv2.setNumThreads(1)


def _ingest(source: Path, captured: datetime, start: float, end: float, directory: Path, config: dict) -> None:
    """Cut one event and write its sidecar; safe to rerun."""
    directory.mkdir(parents=True, exist_ok=True)
    clip = directory / clip_name(captured + timedelta(seconds=start))
    sidecar = clip.with_suffix(".json")
    length = cut(source, start, end, clip, config["PAD_SECONDS"])
    if sidecar.exists():
        read_sidecar(sidecar, config["PRIMARY_MODEL"])
        return
    padded = captured + timedelta(seconds=max(0, start - config["PAD_SECONDS"]))
    row = dict(clip=clip.name, night=directory.name, start_utc=padded.isoformat().replace("+00:00", "Z"),
               duration_s=length, labels={}, annotation_label=None,
               **track(clip, config["MIN_BLOB_AREA"], config["EDGE_MARGIN"]))
    _save(sidecar, row)


def _finish(sidecar: Path, config: dict, cutoff: date) -> None:
    """Classify every track, refresh the annotation, expire completed raw clips."""
    primary_model = config["PRIMARY_MODEL"]
    row = read_sidecar(sidecar, primary_model)
    clip = sidecar.parent / row["clip"]
    annotated = sidecar.with_suffix(".annotated.mp4")
    if "tracks" not in row:
        row["tracks"] = []
        if clip.exists():
            row.update(track(clip, config["MIN_BLOB_AREA"], config["EDGE_MARGIN"]))
    images = {item["id"]: [sidecar.with_name(f"{sidecar.stem}.t{item['id']}{suffix}.jpg") for suffix in ("", ".crop")]
              for item in row["tracks"]}
    frames = [sidecar.parent / name for name in row["frames"]] + [path for pair in images.values() for path in pair]
    if not all(path.is_file() for path in frames):
        track(clip, config["MIN_BLOB_AREA"], config["EDGE_MARGIN"])
    primary = max(row["tracks"], key=lambda item: len(item["boxes"]), default=None)
    if primary:
        primary["labels"] = row["labels"]  # the top-level labels are the primary track's; edits there win
    for item in row["tracks"]:
        for model in config["MODELS"]:
            if item["labels"].get(model, UNCLASSIFIED)["label"] != "unclassified":
                continue
            if item["class"] == "person" or item["class"] in VEHICLES:
                item["labels"][model] = {"label": "person" if item["class"] == "person" else "vehicle", "confidence": 1.0}
            else:
                label, confidence, description = classify(model, images[item["id"]])
                item["labels"][model] = dict(label=label, confidence=confidence)
                if model == primary_model:
                    item["description"] = description
            _save(sidecar, row)
    desired = [[item["labels"].get(primary_model, UNCLASSIFIED)["label"],
                item["labels"].get(primary_model, UNCLASSIFIED)["confidence"]] for item in row["tracks"]]
    if not annotated.exists() or row.get("annotation_label") != desired:
        if clip.exists():
            headline = row["labels"].get(primary_model, UNCLASSIFIED)
            temporary = annotated.with_name("." + annotated.stem + ".refresh.mp4")
            temporary.unlink(missing_ok=True)
            annotate(clip, temporary, row["track"], headline["label"], headline["confidence"])
            os.replace(temporary, annotated)
        elif not annotated.exists():
            raise FileNotFoundError(f"Missing raw and annotated clip: {clip}")
        # Expired raw: preserve the existing video and acknowledge the desired labels.
        row["annotation_label"] = desired
        _save(sidecar, row)
    if (date.fromisoformat(row["night"]) < cutoff
            and all(item["labels"].get(model, UNCLASSIFIED)["label"] != "unclassified"
                    for item in row["tracks"] for model in config["MODELS"])):
        clip.unlink(missing_ok=True)


def run(data_dir: Path, night: str | None = None) -> None:
    config = load_config()
    if night is not None and date.fromisoformat(night).isoformat() != night:
        raise ValueError("--night must be YYYY-MM-DD")
    for provider in {model.split("/", 1)[0] for model in config["MODELS"]}:
        if not os.environ.get(provider.upper() + "_API_KEY", "").strip():
            raise ValueError(f"Missing {provider.upper()}_API_KEY")
        name = provider.upper() + "_BASE_URL"
        os.environ.setdefault(name, config[name])
    if shutil.disk_usage(data_dir).free / 1024**3 < config["MIN_FREE_GB"]:
        raise RuntimeError("Free space is below MIN_FREE_GB")
    started = clock.monotonic()
    incoming, nights = data_dir / "incoming", data_dir / "nights"
    incoming.mkdir(parents=True, exist_ok=True)
    selected = night or night_for(datetime.now(timezone.utc), config["START_TIME"], config["TZ"])
    (nights / selected).mkdir(parents=True, exist_ok=True)
    failures, minutes = 0, 0.0
    with ProcessPoolExecutor(config["WORKERS"], initializer=_init_worker) as pool:
        scans = {source: pool.submit(scan, source, config["MIN_BLOB_AREA"], config["GAP_SECONDS"])
                 for source in sorted(incoming.glob("*.mp4"))}
        jobs = {}
        for source, scanned in scans.items():
            try:
                captured = datetime.strptime(source.name, "%Y-%m-%dT%H-%M-%SZ.mp4").replace(tzinfo=timezone.utc)
                events = scanned.result()
                minutes += duration(source) / 60
            except Exception as exc:
                logging.error("Input %s: %s: %s", source.name, type(exc).__name__, exc)
                failures += 1
                continue
            if not events:
                empty_night = night_for(captured, config["START_TIME"], config["TZ"])
                if night is None or night == empty_night:
                    (nights / empty_night).mkdir(parents=True, exist_ok=True)
                    source.unlink()
                continue
            complete, futures = True, []
            # ponytail: visits split at recording boundaries; merge across files if field footage needs it.
            for _, start, end in events:
                event_night = night_for(captured + timedelta(seconds=start), config["START_TIME"], config["TZ"])
                if night is not None and event_night != night:
                    complete = False
                    continue
                futures.append(pool.submit(_ingest, source, captured, start, end, nights / event_night, config))
            jobs[source] = (complete, futures)
        for source, (complete, futures) in jobs.items():
            for future in futures:
                try:
                    future.result()
                except Exception as exc:
                    logging.error("Input %s: %s: %s", source.name, type(exc).__name__, exc)
                    failures += 1
                    complete = False
            if complete:
                source.unlink()
        cutoff = datetime.now(config["TZ"]).date() - timedelta(days=config["RETAIN_NIGHTS"])
        sidecars = [path for path in sorted(nights.glob("*/*.json")) if night is None or path.parent.name == night]
        for sidecar, future in [(path, pool.submit(_finish, path, config, cutoff)) for path in sidecars]:
            try:
                future.result()
            except Exception as exc:
                logging.error("Sidecar %s: %s: %s", sidecar, type(exc).__name__, exc)
                failures += 1
    build_site(data_dir, config["PRIMARY_MODEL"])
    if minutes:
        elapsed = clock.monotonic() - started
        logging.info("processed %.2f clip minutes in %.1f s (%.1f s per clip minute)", minutes, elapsed, elapsed / minutes)
    if failures:
        raise RuntimeError(f"{failures} local input/output errors; independent work continued")
