from datetime import date, datetime, time, timedelta, timezone
import json
import logging
import math
import os
from pathlib import Path
import shutil
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from foxcam.classify import classify
from foxcam.events import clip_name, night_for
from foxcam.media import annotate, cut, scan, track
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


def run(data_dir: Path, night: str | None = None) -> None:
    config = load_config()
    if night is not None and date.fromisoformat(night).isoformat() != night:
        raise ValueError("--night must be YYYY-MM-DD")
    for provider in {model.split("/", 1)[0] for model in config["MODELS"]}:
        if not os.environ.get(provider.upper() + "_API_KEY", "").strip():
            raise ValueError(f"Missing {provider.upper()}_API_KEY")
        name = provider.upper() + "_BASE_URL"
        os.environ.setdefault(name, config[name])
    existing = data_dir.resolve()
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free / 1024**3 < config["MIN_FREE_GB"]:
        raise RuntimeError("Free space is below MIN_FREE_GB")
    incoming, nights = data_dir / "incoming", data_dir / "nights"
    incoming.mkdir(parents=True, exist_ok=True)
    selected = night or night_for(datetime.now(timezone.utc), config["START_TIME"], config["TZ"])
    (nights / selected).mkdir(parents=True, exist_ok=True)
    failures = 0
    for source in sorted(incoming.glob("*.mp4")):
        try:
            captured = datetime.strptime(source.name, "%Y-%m-%dT%H-%M-%SZ.mp4").replace(tzinfo=timezone.utc)
            events = scan(source, config["MIN_BLOB_AREA"], config["GAP_SECONDS"])
            if not events:
                empty_night = night_for(captured, config["START_TIME"], config["TZ"])
                if night is None or night == empty_night:
                    (nights / empty_night).mkdir(parents=True, exist_ok=True)
                    source.unlink()
                continue
            complete = True
            # ponytail: visits split at recording boundaries; merge across files if field footage needs it.
            for _, start, end in events:
                motion_start = captured + timedelta(seconds=start)
                event_night = night_for(motion_start, config["START_TIME"], config["TZ"])
                if night is not None and event_night != night:
                    complete = False
                    continue
                directory = nights / event_night
                directory.mkdir(parents=True, exist_ok=True)
                clip = directory / clip_name(motion_start)
                sidecar = clip.with_suffix(".json")
                duration = cut(source, start, end, clip, config["PAD_SECONDS"])
                if sidecar.exists():
                    read_sidecar(sidecar, config["PRIMARY_MODEL"])
                else:
                    padded = captured + timedelta(seconds=max(0, start - config["PAD_SECONDS"]))
                    row = dict(clip=clip.name, night=event_night,
                               start_utc=padded.isoformat().replace("+00:00", "Z"), duration_s=duration,
                               labels={}, annotation_label=None,
                               **track(clip, config["MIN_BLOB_AREA"], config["EDGE_MARGIN"]))
                    _save(sidecar, row)
            if complete:
                source.unlink()
        except Exception as exc:
            logging.error("Input %s: %s", source.name, type(exc).__name__)
            failures += 1
    cutoff = datetime.now(config["TZ"]).date() - timedelta(days=config["RETAIN_NIGHTS"])
    for sidecar in sorted(nights.glob("*/*.json")):
        if night is not None and sidecar.parent.name != night:
            continue
        try:
            row = read_sidecar(sidecar, config["PRIMARY_MODEL"])
            clip = sidecar.parent / row["clip"]
            frames = [sidecar.parent / name for name in row["frames"]]
            annotated = sidecar.with_suffix(".annotated.mp4")
            if not all(frame.is_file() for frame in frames):
                track(clip, config["MIN_BLOB_AREA"], config["EDGE_MARGIN"])
            for model in config["MODELS"]:
                if row["labels"].get(model, {}).get("label", "unclassified") == "unclassified":
                    label, confidence = classify(model, frames)
                    row["labels"][model] = dict(label=label, confidence=confidence)
                    _save(sidecar, row)
            primary = row["labels"][config["PRIMARY_MODEL"]]
            desired = [primary["label"], primary["confidence"]]
            if not annotated.exists() or row.get("annotation_label") != desired:
                temporary = annotated.with_name("." + annotated.stem + ".refresh.mp4")
                temporary.unlink(missing_ok=True)
                # Expired raw clips can still refresh their caption from the retained annotation.
                annotate(clip if clip.exists() else annotated, temporary, row["track"], *desired)
                os.replace(temporary, annotated)
                row["annotation_label"] = desired
                _save(sidecar, row)
            if (date.fromisoformat(row["night"]) < cutoff
                    and all(row["labels"][model]["label"] != "unclassified" for model in config["MODELS"])):
                clip.unlink(missing_ok=True)
        except Exception as exc:
            logging.error("Sidecar %s: %s", sidecar, type(exc).__name__)
            failures += 1
    build_site(data_dir, config["PRIMARY_MODEL"])
    if failures:
        raise RuntimeError(f"{failures} local input/output errors; independent work continued")
