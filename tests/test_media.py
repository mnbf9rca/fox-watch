from datetime import datetime

import pytest

from foxcam.media import _moved, _timestamp


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
