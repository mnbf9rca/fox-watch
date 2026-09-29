from unittest.mock import Mock

import numpy as np
import pytest

from foxcam import media


@pytest.mark.parametrize("detected, boxes, minimum, survives", [
    (True, [[0, 100, 100, 100, 100], [2, 100, 100, 100, 100]], 40, False),
    (True, [[0, 100, 100, 100, 100], [2, 139, 100, 100, 100]], 40, False),
    (True, [[0, 100, 100, 100, 100], [2, 124, 132, 100, 100]], 40, True),
    (True, [[0, 100, 100, 100, 100], [2, 100, 100, 180, 100]], 40, True),
    (True, [[0, 100, 100, 100, 100]], 40, False),
    (True, [[0, 100, 100, 100, 100]], 0, True),
    (False, [[0, 100, 100, 100, 100], [2, 140, 100, 100, 100]], 40, True),
    (False, [[0, 100, 100, 100, 100], [2, 139, 100, 100, 100]], 40, False),
    (False, [], 40, False),
])
def test_track_filters_static_detections_and_fallback(tmp_path, monkeypatch, detected, boxes, minimum, survives):
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    video = Mock(read=Mock(side_effect=[(True, image)] * 3 + [(False, None)]))
    monkeypatch.setattr(media.cv2, "VideoCapture", lambda path: video)
    monkeypatch.setattr(media, "detect", lambda image: [])
    monkeypatch.setattr(media, "link", lambda detections: [{"id": 0, "class": "vehicle", "boxes": boxes}] if detected else [])
    fallback = Mock(return_value=boxes)
    monkeypatch.setattr(media, "_blob_boxes", fallback)
    monkeypatch.setattr(media, "_frame", lambda *args: image.copy())
    result = media.track(tmp_path / "clip.mp4", 100, 80, min_track_move=minimum)
    assert bool(result["tracks"]) == survives
    assert result["track"] == (boxes if survives else [])
    if detected:
        fallback.assert_not_called()  # Never turn discarded parked cars into blob tracks.
    else:
        fallback.assert_called_once()
