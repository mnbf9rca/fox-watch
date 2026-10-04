"""Exercise the real CLI/video pipeline; --live requires op run and provider secrets."""
import argparse
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

from make_video import make_video
from foxcam.events import night_for


MODEL = "deepinfra/__foxcam_nonexistent_model__"
SECONDARY = "deepinfra/saved-secondary"


def cli(data, env, *arguments, **overrides):
    return subprocess.run([sys.executable, "-m", "foxcam", *arguments, "--data", str(data)],
                          env=env | overrides, capture_output=True, text=True)


def passed(result):
    assert result.returncode == 0, result.stdout + result.stderr


def media_state(directory):
    return {str(p.relative_to(directory)): (sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in directory.rglob("*") if p.suffix in (".mp4", ".jpg")}


def playable(path):
    stream = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams", "-of", "json", str(path),
    ], text=True))["streams"][0]
    assert stream["codec_name"] == "h264" and int(stream["nb_frames"]) > 0


def check_refile(data, env):
    old = data / "nights/2026-09-28"
    target = data / "nights/2026-09-29"
    old.mkdir(parents=True)
    target.mkdir()
    names = []
    for stem, stamp in (("23-30-00", "2026-09-28T23:30:00Z"), ("05-30-00", "2026-09-29T05:30:00Z")):
        frames = [f"{stem}.f{i}.jpg" for i in range(4)]
        row = dict(clip=stem + ".mp4", night=old.name, start_utc=stamp, duration_s=1,
                   labels={env["PRIMARY_MODEL"]: {"label": "none", "confidence": 1.0}},
                   track=[], tracks=[], frames=frames, entry_edge="unknown", exit_edge="unknown")
        (old / (stem + ".json")).write_text(json.dumps(row))
        media = [row["clip"], stem + ".annotated.mp4", *frames, stem + ".t0.jpg", stem + ".t0.crop.jpg"]
        for name in media:
            (old / name).write_bytes(name.encode())
        names.extend(media)
    # A conflict on the second sidecar must leave both source bundles untouched.
    blocker = target / "23-30-00.annotated.mp4"
    blocker.write_bytes(b"do not overwrite")
    before = {str(p.relative_to(data)): p.read_bytes() for p in data.rglob("*") if p.is_file()}
    refused = cli(data, env, "refile")
    assert refused.returncode != 0 and "Refusing to overwrite" in refused.stderr, refused.stderr
    assert before == {str(p.relative_to(data)): p.read_bytes() for p in data.rglob("*") if p.is_file()}
    blocker.unlink()
    moved = cli(data, env, "refile")
    passed(moved)
    assert "Moved 2 sidecars" in moved.stdout, moved.stdout
    assert not list(old.iterdir())
    for name in names:
        assert (target / name).read_bytes() == name.encode()
    assert all(json.loads(p.read_text())["night"] == target.name for p in target.glob("*.json"))
    page = (data / "site/2026-09-29.html").read_text()
    assert "00:30 BST" in page and "06:30 BST" in page and "UTC" not in page
    assert "Days" in (data / "site/index.html").read_text()
    state = media_state(data)
    again = cli(data, env, "refile")
    passed(again)
    assert "Moved 0 sidecars" in again.stdout and media_state(data) == state
    print("PASS: refile two sidecars, all media, collision refusal, local days, and idempotence")


def check_calendar_boundary(data, env, fixture):
    incoming = data / "incoming"
    incoming.mkdir(parents=True)
    shutil.copyfile(fixture, incoming / "2026-09-28T22-59-53Z.mp4")
    passed(cli(data, env, "run"))
    sidecar, = (data / "nights").glob("*/*.json")
    row = json.loads(sidecar.read_text())
    assert row["start_utc"] == "2026-09-28T22:59:59Z"
    assert sidecar.parent.name == row["night"] == "2026-09-28"
    result = cli(data, env, "refile")
    passed(result)
    assert "Moved 0 sidecars" in result.stdout
    print("PASS: padded midnight capture stays in its local calendar day")


def check_rejected_inputs(data, env, fixture):
    incoming = data / "incoming"
    incoming.mkdir(parents=True)
    source = incoming / "2000-01-01T20-00-00Z.mp4"
    source.write_bytes(b"not a video")
    for attempt in range(1, 4):
        result = cli(data, env, "run")
        if attempt < 3:
            assert result.returncode != 0 and source.exists(), result.stderr
        else:
            assert not source.exists(), "undecodable input still present after three runs"
            passed(result)
            assert result.stderr.count("Rejected") == 1, result.stderr
    rejected = incoming / "rejected"
    original = rejected / source.name
    assert original.read_bytes() == b"not a video"
    os.utime(original, (0, 0))
    # A new top-level upload with the same basename must not touch the archive.
    # Successful decoding resets the count even if --night leaves the input queued.
    source.touch()
    for _ in range(2):
        assert cli(data, env, "run").returncode != 0
        assert source.exists()
    shutil.copyfile(fixture, source)
    passed(cli(data, env, "run", "--night", "2099-01-01"))
    assert source.exists() and original.read_bytes() == b"not a video"
    source.write_bytes(b"")
    for attempt in range(1, 4):
        result = cli(data, env, "run")
        if attempt < 3:
            assert result.returncode != 0 and source.exists(), "decode failure count was not reset"
        else:
            passed(result)
            assert not source.exists() and result.stderr.count("Rejected") == 1
    archived = media_state(rejected)
    assert len(archived) == 2 and original.read_bytes() == b"not a video", archived
    result = cli(data, env, "run", RETAIN_NIGHTS="0")
    passed(result)
    assert source.name not in result.stderr and "ERROR" not in result.stderr, result.stderr
    assert media_state(rejected) == archived, "rejected input was retried or expired"
    # Filename/configuration errors are not evidence of undecodable video.
    invalid_name = incoming / "invalid-name.mp4"
    shutil.copyfile(fixture, invalid_name)
    for _ in range(3):
        assert cli(data, env, "run").returncode != 0
        assert invalid_name.exists() and media_state(rejected) == archived
    print("PASS: reject after 3 decode failures, reset on success, preserve collisions, "
          "ignore rejected uploads/retention, and retain non-decode errors")


def check(data, live=False):
    env = os.environ.copy()
    root = Path(__file__).resolve().parents[1]
    env.setdefault("MODEL_DIR", str(root / "models"))
    for assignment in shlex.split((root / "vps/foxcam.env.example").read_text(), comments=True):
        key, value = assignment.split("=", 1)
        env.setdefault(key, value)
    env.update(MIN_FREE_GB="0", MIN_BLOB_AREA="100", EDGE_MARGIN="80", GAP_SECONDS="3",
               PAD_SECONDS="2", RETAIN_NIGHTS="180", START_TIME="19:00", STOP_TIME="07:00", TZ="Europe/London")
    if not live:
        for key in ("NOUS_API_KEY", "DEEPINFRA_API_KEY", "TOGETHER_API_KEY"):
            env.pop(key, None)
        env.update(MODELS=MODEL, PRIMARY_MODEL=MODEL, DEEPINFRA_BASE_URL="https://127.0.0.1:1",
                   DEEPINFRA_API_KEY="local-check-no-secret")
    if not live:
        check_refile(data / "refile-check", env)
    models = env["MODELS"].split(",")
    primary = env["PRIMARY_MODEL"]
    missing = data / "missing-data"
    assert cli(missing, env, "run").returncode != 0
    assert not missing.exists()
    incoming = data / "incoming"
    incoming.mkdir(parents=True)
    stamp = datetime.now(timezone.utc).replace(hour=20, minute=5, second=0, microsecond=0)
    night = night_for(stamp, time(19), ZoneInfo("Europe/London"))
    fixture = data / "fixture.mp4"
    make_video(fixture)
    if not live:
        check_rejected_inputs(data / "rejected-check", env, fixture)
        check_calendar_boundary(data / "boundary-check", env, fixture)
    source = incoming / stamp.strftime("%Y-%m-%dT%H-%M-%SZ.mp4")
    shutil.copyfile(fixture, source)
    completed_run = cli(data, env, "run")
    passed(completed_run)
    sidecars = list((data / "nights").glob("*/*.json"))
    assert len(sidecars) == 1, sidecars
    sidecar = sidecars[0]
    row = json.loads(sidecar.read_text())
    assert (row["entry_edge"], row["exit_edge"]) == ("left", "far")
    assert row["clip"] == "20-05-08.mp4"
    assert row["start_utc"] == (stamp + timedelta(seconds=6)).isoformat().replace("+00:00", "Z")
    assert 10 <= row["duration_s"] <= 12
    clip = sidecar.with_suffix(".mp4")
    annotated = sidecar.with_suffix(".annotated.mp4")
    frames = [sidecar.parent / name for name in row["frames"]]
    assert not source.exists()
    assert annotated.exists() and all(frame.exists() for frame in frames)
    playable(annotated)
    assert row["tracks"][0]["class"] == "unknown" and row["tracks"][0]["labels"] == row["labels"], row["tracks"]
    throughput = [line for line in completed_run.stderr.splitlines() if "per clip minute" in line]
    assert len(throughput) == 1, completed_run.stderr
    seconds_per_minute = float(throughput[0].rsplit("(", 1)[1].split()[0])
    print(f"{throughput[0]}; real-time ratio {seconds_per_minute / 60:.2f}")
    if live:
        for model in models:
            answer = row["labels"][model]
            assert answer["label"] != "unclassified", model
            print(f"{model}: {answer['label']}, confidence={answer['confidence']}")
        print(f"description: {row['tracks'][0]['description']!r}")
        assert row["annotation_label"] == [[row["labels"][primary]["label"], row["labels"][primary]["confidence"]]]
        print("PASS: live provider answers and playable primary H.264 annotation")
        return
    assert row["labels"][MODEL] == {"label": "unclassified", "confidence": 0.0}
    comparison = cli(data, env, "compare", DEEPINFRA_API_KEY="")
    passed(comparison)
    assert f"{MODEL}: 0/0 (n/a)" in comparison.stdout
    first_media = media_state(data / "nights")
    # Upgrade pre-timestamp annotations even when labels match.
    row["annotation_version"] = 2
    sidecar.write_text(json.dumps(row))
    passed(cli(data, env, "run"))
    assert json.loads(sidecar.read_text())["annotation_version"] == 3
    assert media_state(data / "nights") != first_media
    first_media = media_state(data / "nights")
    second_run = cli(data, env, "run")
    passed(second_run)
    assert MODEL in second_run.stderr and "URLError" in second_run.stderr
    assert media_state(data / "nights") == first_media
    # A cut survived, but its sidecar did not. Reuse the existing media.
    shutil.copyfile(fixture, source)
    sidecar.unlink()
    cut_state = (clip.read_bytes(), clip.stat().st_mtime_ns)
    passed(cli(data, env, "run"))
    assert not source.exists() and sidecar.exists()
    assert (clip.read_bytes(), clip.stat().st_mtime_ns) == cut_state
    # Resume from sidecars after deleting the source; retain successful comparisons.
    row = json.loads(sidecar.read_text())
    row["labels"][SECONDARY] = {"label": "cat", "confidence": 0.77}
    sidecar.write_text(json.dumps(row))
    env["MODELS"] += "," + SECONDARY
    annotated.unlink()
    frames[0].unlink()
    saved_frame_state = media_state(sidecar.parent)
    passed(cli(data, env, "run"))
    row = json.loads(sidecar.read_text())
    assert row["labels"][SECONDARY] == {"label": "cat", "confidence": 0.77}
    assert annotated.exists() and frames[0].exists()
    assert all(media_state(sidecar.parent)[name] == state for name, state in saved_frame_state.items())
    # A changed primary answer refreshes the annotation exactly once.
    old_annotation = (sha256(annotated.read_bytes()).hexdigest(), annotated.stat().st_mtime_ns)
    row["labels"][MODEL] = {"label": "fox", "confidence": 0.9}
    sidecar.write_text(json.dumps(row))
    passed(cli(data, env, "run"))
    changed_annotation = (sha256(annotated.read_bytes()).hexdigest(), annotated.stat().st_mtime_ns)
    assert changed_annotation != old_annotation
    assert json.loads(sidecar.read_text())["annotation_label"] == [["fox", 0.9]]
    passed(cli(data, env, "run"))
    assert (sha256(annotated.read_bytes()).hexdigest(), annotated.stat().st_mtime_ns) == changed_annotation
    # Configuration and space refusals must happen before input changes.
    shutil.copyfile(fixture, source)
    before = media_state(data)
    assert cli(data, env, "run", PAD_SECONDS="-1").returncode != 0
    assert source.exists() and media_state(data) == before
    free_gib = shutil.disk_usage(data).free / 1024**3
    assert cli(data, env, "run", MIN_FREE_GB=str(free_gib + 1)).returncode != 0
    assert source.exists() and media_state(data) == before
    source.unlink()
    # Broken input does not prevent independent valid input from completing.
    broken = incoming / stamp.replace(hour=21).strftime("%Y-%m-%dT%H-%M-%SZ.mp4")
    broken.write_bytes(b"not a video")
    valid = incoming / stamp.replace(hour=22).strftime("%Y-%m-%dT%H-%M-%SZ.mp4")
    shutil.copyfile(fixture, valid)
    result = cli(data, env, "run")
    assert result.returncode != 0 and broken.exists() and not valid.exists()
    assert f"Cannot decode video: {broken}" in result.stderr
    assert (sidecar.parent / "22-05-08.json").exists()
    broken.unlink()
    malformed = sidecar.parent / "malformed.json"
    malformed.write_text("{")
    result = cli(data, env, "run")
    assert result.returncode != 0 and "Expecting property name" in result.stderr
    malformed.unlink()
    # Empty recordings and explicit empty nights still publish pages.
    blank = incoming / stamp.replace(hour=23).strftime("%Y-%m-%dT%H-%M-%SZ.mp4")
    make_video(blank, moving=False)
    passed(cli(data, env, "run"))
    assert not blank.exists()
    empty_night = (stamp.date() + timedelta(days=2)).isoformat()
    shutil.copyfile(fixture, source)
    passed(cli(data, env, "run", "--night", empty_night))
    assert source.exists()
    assert "No visits recorded" in (data / "site" / f"{empty_night}.html").read_text()
    assert night in (data / "site/index.html").read_text()
    source.unlink()
    # Retain failed/incomplete raw clips, expire only completed old raw clips.
    old_night = (stamp.date() - timedelta(days=181)).isoformat()
    old_dir = data / "nights" / old_night
    old_dir.mkdir()
    old_row = json.loads(sidecar.read_text())
    old_row.update(night=old_night, start_utc=f"{old_night}T20:05:06Z")
    old_sidecar = old_dir / sidecar.name
    old_sidecar.write_text(json.dumps(old_row))
    for media in [clip, annotated, *frames]:
        shutil.copyfile(media, old_dir / media.name)
    old_clip = old_dir / clip.name
    passed(cli(data, env, "run", "--night", night))
    assert old_clip.exists()
    old_row["labels"][MODEL] = {"label": "unclassified", "confidence": 0}
    old_sidecar.write_text(json.dumps(old_row))
    passed(cli(data, env, "run"))
    assert old_clip.exists()
    old_row["labels"][MODEL] = {"label": "fox", "confidence": 0.9}
    old_row["annotation_label"] = [["fox", 0.9]]
    old_sidecar.write_text(json.dumps(old_row))
    # Force annotation repair before allowing expiration.
    (old_dir / annotated.name).unlink()
    passed(cli(data, env, "run"))
    assert not old_clip.exists()
    assert old_sidecar.exists() and (old_dir / annotated.name).exists()
    assert all((old_dir / frame.name).exists() for frame in frames)
    old_row = json.loads(old_sidecar.read_text())
    old_row["labels"][MODEL] = {"label": "bird", "confidence": 0.8}
    old_sidecar.write_text(json.dumps(old_row))
    archived_media = media_state(old_dir)
    passed(cli(data, env, "run"))
    assert media_state(old_dir) == archived_media
    assert json.loads(old_sidecar.read_text())["annotation_label"] == [["bird", 0.8]]
    assert not old_clip.exists()
    playable(old_dir / annotated.name)
    refreshed = media_state(old_dir)
    passed(cli(data, env, "run"))
    assert media_state(old_dir) == refreshed
    # Compare needs no provider secrets and makes no calls.
    for key in ("NOUS_API_KEY", "DEEPINFRA_API_KEY", "TOGETHER_API_KEY"):
        env.pop(key, None)
    result = cli(data, env, "compare")
    passed(result)
    assert f"{MODEL}: 2/2 (100.0%)" in result.stdout
    assert f"{SECONDARY}: 0/2 (0.0%)" in result.stdout
    assert cli(data, env, "run").returncode != 0
    print("PASS: offline pipeline, retries, partial outputs, annotation refresh, input isolation, "
          "empty nights, config/space guards, retention, and secret-free comparison")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    with TemporaryDirectory() as directory:
        check(Path(directory), live=args.live)
