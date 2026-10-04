from hashlib import sha256
from unittest.mock import Mock

import numpy as np
import pytest

from foxcam import detect as detector
from foxcam.detect import iou, link

def test_iou_and_linking():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1
    assert iou((0, 0, 10, 10), (20, 20, 10, 10)) == 0
    assert abs(iou((0, 0, 10, 10), (5, 0, 10, 10)) - 1 / 3) < 1e-9
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    person = ("person", 0.8, 200, 200, 60, 120)
    frames = [(0, [dog(0), person]), (2, [dog(6), person]), (4, [person]), (6, [dog(20)])]
    tracks = link(frames)
    assert [(t["id"], t["class"], len(t["boxes"])) for t in tracks] == [(0, "dog", 3), (1, "person", 3)]
    assert tracks[0]["boxes"][0] == [0, 0, 0, 50, 50] and tracks[0]["boxes"][-1] == [6, 20, 0, 50, 50]
    assert len(link([(0, [dog(0)]), (2, [("cat", 0.9, 0, 0, 50, 50)])])) == 2
    gap = [(0, [dog(0)])] + [(f, []) for f in range(2, 22, 2)] + [(22, [dog(0)])]
    assert len(link(gap)) == 2 and len(link(gap, max_misses=11)) == 1


@pytest.mark.parametrize("offset", [50, 49, 46, 45])
def test_link_distance_recovers_weak_or_missing_overlap(offset):
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    assert len(link([(0, [dog(0)]), (2, [dog(offset)])])) == 1


def test_link_keeps_10fps_mover_after_two_missed_detections():
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    frames = [(0, [dog(0)]), (2, [dog(15)]), (4, []), (6, []), (8, [dog(60)])]
    tracks = link(frames)
    assert len(tracks) == 1 and len(tracks[0]["boxes"]) == 3
    # Exactly 0.05 IoU is accepted too.
    assert len(link([(0, [("dog", .9, 0, 0, 21, 21)]),
                     (2, [("dog", .9, 19, 0, 21, 21)])])) == 1


def test_link_keeps_bird_moving_one_metre_between_processed_frames():
    # Calibration at 1920 wide: f=1478 px, depth=5 m, bird=0.12 m.
    # Its box rounds to 35 px; moving 1 m (5 m/s at 5 fps) jumps 296 px.
    tracks = link([(0, [("bird", .9, 100, 100, 35, 35)]),
                   (2, [("bird", .9, 396, 100, 35, 35)]),
                   (4, [("bird", .9, 692, 100, 35, 35)])])
    assert len(tracks) == 1
    assert tracks[0]["boxes"] == [[0, 100, 100, 35, 35],
                                  [2, 396, 100, 35, 35],
                                  [4, 692, 100, 35, 35]]


@pytest.mark.parametrize("x,y,count", [(315, 0, 1), (316, 0, 2), (250, 250, 2)])
def test_link_bird_distance_gate_rejects_large_displacements(x, y, count):
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35)]),
                   (2, [("bird", .9, x, y, 35, 35)])])
    assert len(tracks) == count


def test_link_bird_distance_chooses_nearest_unmatched_track():
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35), ("bird", .8, 500, 0, 35, 35)]),
                   (2, [("bird", .9, 296, 0, 35, 35)])])
    assert [t["boxes"] for t in tracks] == [[[0, 0, 0, 35, 35]],
                                          [[0, 500, 0, 35, 35], [2, 296, 0, 35, 35]]]


def test_link_all_iou_matches_precede_bird_distance_matches():
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35)]),
                   (2, [("bird", .9, 296, 0, 35, 35), ("bird", .8, 1, 0, 35, 35)])])
    assert [t["boxes"] for t in tracks] == [[[0, 0, 0, 35, 35], [2, 1, 0, 35, 35]],
                                          [[2, 296, 0, 35, 35]]]


def test_link_bird_distance_matches_each_track_at_most_once_per_frame():
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35)]),
                   (2, [("bird", .9, 100, 0, 35, 35), ("bird", .8, 200, 0, 35, 35)])])
    assert [t["boxes"] for t in tracks] == [[[0, 0, 0, 35, 35], [2, 100, 0, 35, 35]],
                                          [[2, 200, 0, 35, 35]]]


def test_link_does_not_rematch_newborn_birds_in_same_frame():
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35), ("bird", .8, 10, 0, 35, 35)])])
    assert [t["boxes"] for t in tracks] == [[[0, 0, 0, 35, 35]], [[0, 10, 0, 35, 35]]]


def test_link_bird_distance_respects_class_and_track_expiry():
    frames = [(0, [("bird", .9, 0, 0, 35, 35)]),
              (2, [("cat", .9, 296, 0, 35, 35)]), (4, []),
              (6, [("bird", .9, 296, 0, 35, 35)])]
    assert [(t["id"], t["class"], len(t["boxes"])) for t in link(frames, max_misses=2)] == [
        (0, "bird", 1), (1, "cat", 1), (2, "bird", 1)]
    assert [(t["id"], t["class"], len(t["boxes"])) for t in link(frames, max_misses=3)] == [
        (0, "bird", 2), (1, "cat", 1)]


@pytest.mark.parametrize("name", ["dog", "cat", "unknown"])
def test_link_distance_recovers_other_same_class_movers(name):
    tracks = link([(0, [(name, .9, 0, 0, 35, 35)]),
                   (2, [(name, .9, 296, 0, 35, 35)])])
    assert len(tracks) == 1 and len(tracks[0]["boxes"]) == 2


@pytest.mark.parametrize("size", [0, 350])
def test_link_distance_does_not_use_one_large_box_to_bridge_tracks(size):
    tracks = link([(0, [("bird", .9, 0, 0, 35, 35)]),
                   (2, [("bird", .9, 296, 0, size, size)])])
    assert len(tracks) == 2


def test_download_is_verified_before_install(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    monkeypatch.setattr(detector, "_net", None)
    monkeypatch.setattr(detector, "MODEL_SHA256", sha256(b"valid").hexdigest())
    read_net = Mock(return_value=object())
    monkeypatch.setattr(detector.cv2.dnn, "readNet", read_net)
    monkeypatch.setattr(detector.request, "urlretrieve", lambda url, path: path.write_bytes(b"bad"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        detector.load()
    assert not list(tmp_path.iterdir())
    read_net.assert_not_called()
    monkeypatch.setattr(detector.request, "urlretrieve", lambda url, path: path.write_bytes(b"valid"))
    assert detector.load() is read_net.return_value
    assert detector.model_path().read_bytes() == b"valid"
    assert list(tmp_path.iterdir()) == [detector.model_path()]


def test_nms_keeps_overlapping_different_classes(monkeypatch):
    raw = np.zeros((1, 8400, 85), dtype=np.float32)
    for index, name in enumerate(("person", "dog", "dog")):
        raw[0, index, :2] = (np.array([100, 100]) / 8 - detector._grids[index])
        raw[0, index, 2:4] = np.log(80 / 8)
        raw[0, index, 4] = 1
        raw[0, index, 5 + detector.CLASSES.index(name)] = .9 - index * .1
    monkeypatch.setattr(detector, "load", lambda: Mock(forward=lambda: raw))
    found = detector.detect(np.zeros((640, 640, 3), dtype=np.uint8))
    assert [item[0] for item in found] == ["person", "dog"]


def test_detector_allows_only_people_vehicles_and_animals(monkeypatch):
    raw = np.zeros((1, 8400, 85), dtype=np.float32)
    for index in range(len(detector.CLASSES)):
        raw[0, index, :2] = (np.array([10 + index * 6, 100]) / 8 - detector._grids[index])
        raw[0, index, 2:4] = np.log(4 / 8)
        raw[0, index, 4] = raw[0, index, 5 + index] = 1
    monkeypatch.setattr(detector, "load", lambda: Mock(forward=lambda: raw))
    found = detector.detect(np.zeros((640, 640, 3), dtype=np.uint8))
    assert [item[0] for item in found] == ["person", "vehicle", "vehicle", "vehicle", "vehicle", "vehicle",
                                          "bird", "cat", "dog", "horse", "sheep", "cow", "bear"]
