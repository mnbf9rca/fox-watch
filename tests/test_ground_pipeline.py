import json

import cv2
import numpy as np
import pytest

from foxcam import media, pipeline


CALIBRATION = {"image_size": [1920, 1080],
               "homography": [[.001, 0, 0], [0, .001, 0], [0, 0, 1]]}


def test_config_loads_ground_calibration(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELS", "nous/a")
    monkeypatch.setenv("PRIMARY_MODEL", "nous/a")
    monkeypatch.delenv("GROUND_CALIBRATION", raising=False)
    assert pipeline.load_config()["GROUND_CALIBRATION"] is None
    path = tmp_path / "ground.json"
    path.write_text(json.dumps(CALIBRATION))
    monkeypatch.setenv("GROUND_CALIBRATION", str(path))
    assert pipeline.load_config()["GROUND_CALIBRATION"] == CALIBRATION


def test_track_stores_one_bottom_centre_ground_point_per_box(tmp_path, monkeypatch):
    clip = tmp_path / "track.mp4"
    writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 10, (192, 108))
    assert writer.isOpened()
    for _ in range(10):
        writer.write(np.zeros((108, 192, 3), np.uint8))
    writer.release()
    found = iter([[("cat", .9, 10 + frame * 10, 40, 20, 20)] for frame in range(5)])
    monkeypatch.setattr(media, "detect", lambda image: next(found))
    row = media.track(clip, 25, 12, ground_calibration=CALIBRATION)
    assert len(row["tracks"]) == 1
    item = row["tracks"][0]
    assert len(item["ground_track"]) == len(item["boxes"])
    for point, (frame, x, y, w, h) in zip(item["ground_track"], item["boxes"]):
        assert point == pytest.approx([frame, (x + w / 2) * .01, (y + h) * .01])
