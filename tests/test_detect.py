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


@pytest.mark.parametrize("offset, count", [(50, 2), (49, 2), (46, 2), (45, 1)])
def test_link_requires_meaningful_overlap(offset, count):
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    assert len(link([(0, [dog(0)]), (2, [dog(offset)])])) == count


def test_link_keeps_10fps_mover_after_two_missed_detections():
    dog = lambda x: ("dog", 0.9, x, 0, 50, 50)
    frames = [(0, [dog(0)]), (2, [dog(15)]), (4, []), (6, []), (8, [dog(60)])]
    tracks = link(frames)
    assert len(tracks) == 1 and len(tracks[0]["boxes"]) == 3
    # Exactly 0.05 IoU is accepted too.
    assert len(link([(0, [("dog", .9, 0, 0, 21, 21)]),
                     (2, [("dog", .9, 19, 0, 21, 21)])])) == 1


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
