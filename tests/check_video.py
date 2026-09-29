"""Exercise real video tools; pass a directory to retain the generated media."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import cv2

import os
os.environ.setdefault("MODEL_DIR", str(Path(__file__).resolve().parents[1] / "models"))

from make_video import make_video
from foxcam.media import annotate, cut, scan, track


def check_video(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "moving.mp4"
    blank = directory / "blank.mp4"
    target = directory / "cut.mp4"
    truncated = directory / "truncated.mp4"
    animal = directory / "animal.mp4"
    make_video(source)
    events = scan(source, min_blob_area=100)
    assert len(events) == 1, events
    assert events[0][0] == source
    assert 7.8 <= events[0][1] <= 8.2, events
    assert 14.8 <= events[0][2] <= 15.2, events
    duration = cut(*events[0], target, pad_seconds=2)
    assert target.is_file() and source.is_file()
    assert 10 <= duration <= 12, duration
    assert events[0][2] + 2 < 20
    stream = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
         "-of", "json", str(target)], text=True,
    ))["streams"][0]
    assert stream["codec_name"] == "h264"
    make_video(blank, moving=False)
    assert scan(blank, min_blob_area=100) == []
    truncated.write_bytes(source.read_bytes()[:100])
    try:
        scan(truncated, min_blob_area=100)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated input accepted")
    assert truncated.exists()
    result = track(target, min_blob_area=100, edge_margin=80)
    assert (result["entry_edge"], result["exit_edge"]) == ("left", "far"), result
    assert len(result["frames"]) == 4
    assert all(cv2.imread(str(target.parent / name)) is not None for name in result["frames"])
    annotated = target.with_name("annotated.mp4")
    annotate(target, annotated, result["track"], "fox", 0.9)
    output_stream = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
         "-of", "json", str(annotated)], text=True,
    ))["streams"][0]
    assert output_stream["codec_name"] == "h264"
    assert (output_stream["width"], output_stream["height"]) == (1280, 720)
    assert output_stream["nb_frames"] == stream["nb_frames"]
    empty = track(blank, min_blob_area=100, edge_margin=80)
    assert empty["track"] == [] and empty["entry_edge"] == empty["exit_edge"] == "unknown"
    assert [t["class"] for t in result["tracks"]] == ["unknown"]
    assert result["tracks"][0]["boxes"] == result["track"]
    assert all((target.parent / f"cut.t0{suffix}.jpg").is_file() for suffix in ("", ".crop"))
    fox = cv2.imread(str(Path(__file__).with_name("fixtures") / "fox.jpg"))
    sprite = cv2.resize(fox[700:1500, 1000:2100], (240, 174))
    make_video(animal, sprite=sprite)
    animal_result = track(animal, min_blob_area=100, edge_margin=150)
    classes = [t["class"] for t in animal_result["tracks"]]
    assert classes and "unknown" not in classes, classes
    assert len(animal_result["tracks"][0]["boxes"]) >= 20, animal_result["tracks"]
    assert (animal_result["entry_edge"], animal_result["exit_edge"]) == ("left", "far"), animal_result
    crop = cv2.imread(str(animal.with_name("animal.t0.crop.jpg")))
    assert crop is not None and crop.shape[0] < 720
    print(f"PASS: moving/static/truncated scan; H.264 cut {duration:.1f}s; "
          f"left → far track; four JPEGs; annotated 1280x720 H.264 ({output_stream['nb_frames']} frames); "
          f"sprite tracks {classes} with {len(animal_result['tracks'][0]['boxes'])} boxes")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_video(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            check_video(Path(directory))
