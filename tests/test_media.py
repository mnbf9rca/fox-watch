from datetime import datetime

import pytest
import cv2
import numpy as np

from foxcam.media import _moved, _timestamp, scan
from foxcam.pipeline import load_config


@pytest.mark.parametrize("moving", [True, False])
def test_scan_calibrated_hedgehog_at_nine_metres(tmp_path, monkeypatch, moving):
    monkeypatch.setenv("MODELS", "nous/a")
    monkeypatch.setenv("PRIMARY_MODEL", "nous/a")
    monkeypatch.delenv("MIN_BLOB_AREA", raising=False)
    # At 1920 wide: 1478/9 px/m gives a 41x20 px body. Use an ellipse,
    # whose silhouette is smaller than the bounding rectangle, not a large blob.
    source = tmp_path / "hedgehog.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (1920, 1080))
    assert writer.isOpened()
    try:
        for frame in range(30):
            image = np.full((1080, 1920, 3), 30, dtype=np.uint8)
            if moving and 10 <= frame < 25:
                cv2.ellipse(image, (200 + 20 * (frame - 10), 700), (20, 9), 0, 0, 360, (180, 180, 180), -1)
            writer.write(image)
    finally:
        writer.release()
    events = scan(source, load_config()["MIN_BLOB_AREA"])
    assert bool(events) == moving, "calibrated small animal was discarded by motion screening"
    if moving:
        assert events[0][1] <= 1.1 and events[0][2] >= 2.4


def test_per_frame_utc_timestamp():
    start = datetime.fromisoformat("2026-09-30T12:34:56+00:00")
    assert _timestamp(start, 0, 10) == "2026-09-30 12:34:56 UTC"
    assert _timestamp(start, 15, 10) == "2026-09-30 12:34:57 UTC"
    assert _timestamp(datetime.fromisoformat("2026-09-30T23:59:59+00:00"), 15, 10) == "2026-10-01 00:00:00 UTC"
    assert _timestamp(datetime.fromisoformat("2026-09-30T13:34:56+01:00"), 0, 10) == "2026-09-30 12:34:56 UTC"
    with pytest.raises(ValueError, match="aware"):
        _timestamp(datetime(2026, 9, 30), 0, 10)


@pytest.mark.parametrize("width, height, span, expected", [
    (450, 200, 120, False),  # Parked car.
    (400, 200, 900, True),   # Passing car.
    (40, 100, 90, True),     # Person.
    (90, 60, 75, True),      # Dog.
    (60, 40, 15, False),     # Small jittering detection.
    (10, 10, 19, False),     # Absolute floor still applies to tiny boxes.
    (10, 10, 20, True),
    (100, 60, 75, True),     # Inclusive ratio boundary.
    (100, 60, 74, False),
])
def test_size_relative_movement(width, height, span, expected):
    boxes = [[0, 100, 100, width, height], [2, 100 + span, 100, width, height]]
    assert _moved(boxes, .75) == expected


def test_walk_then_pause_and_out_and_back():
    boxes = [[0, 100, 100, 40, 40], [2, 140, 100, 40, 40], [4, 140, 100, 40, 40]]
    assert _moved(boxes, .75)
    assert _moved(boxes + [[6, 100, 100, 40, 40]], .75)
    assert not _moved(boxes, 1.1)


def test_mean_size_and_centroid_bounds():
    # Mean max dimension is 60; centroids move 45 px, exactly .75 of the mean.
    boxes = [[0, 100, 100, 40, 20], [2, 125, 100, 80, 20]]
    assert _moved(boxes, .75)
    assert not _moved(boxes, .76)
    # Centroid bounds have diagonal 40, although neither axis spans 40.
    assert _moved([[0, 100, 100, 40, 40], [2, 124, 132, 40, 40]], 1)
    assert not _moved([[0, 100, 100, 40, 40]], .75)
    assert not _moved([], .75)
    assert not _moved([[0, 100, 100, 10, 10], [2, 115, 100, 10, 10]], 0)


def test_annotated_path_follows_box_bottom_centres(tmp_path):
    from foxcam.media import annotate

    clip, output = tmp_path / "raw.mp4", tmp_path / "annotated.mp4"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 10, (640, 360))
    assert writer.isOpened()
    for _ in range(4):
        writer.write(np.zeros((360, 640, 3), np.uint8))
    writer.release()
    boxes = [[0, 100, 70, 40, 100], [2, 260, 70, 40, 100]]
    annotate(clip, output, [dict(id=0, boxes=boxes)], ["person 100%"],
             datetime.fromisoformat("2026-09-30T12:34:56+00:00"))
    video = cv2.VideoCapture(str(output))
    try:
        for _ in range(3):
            ok, image = video.read()
            assert ok
        # Between boxes: the trail is at their feet (170), not waist (120).
        assert image[169:172, 195:205, 1].mean() > 100
        assert image[119:122, 195:205].max() < 30
        # The current box and its caption still draw in their original places.
        assert image[100, 260, 1] > 100
        assert image[40:65, 260:440].max() > 100
    finally:
        video.release()
