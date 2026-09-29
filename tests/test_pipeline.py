from datetime import date
import json
from unittest.mock import Mock

import pytest

from foxcam import pipeline


@pytest.mark.parametrize("minimum", ["0.75", "1.2", "-1", "nan", "inf"])
def test_minimum_track_move_config(monkeypatch, minimum):
    monkeypatch.setenv("MODELS", "nous/a")
    monkeypatch.setenv("PRIMARY_MODEL", "nous/a")
    monkeypatch.delenv("MIN_TRACK_MOVE_RATIO", raising=False)
    assert pipeline.load_config()["MIN_TRACK_MOVE_RATIO"] == .75
    monkeypatch.setenv("MIN_TRACK_MOVE_RATIO", minimum)
    if minimum in ("0.75", "1.2"):
        assert pipeline.load_config()["MIN_TRACK_MOVE_RATIO"] == float(minimum)
    else:
        with pytest.raises(ValueError, match="MIN_TRACK_MOVE_RATIO"):
            pipeline.load_config()


@pytest.mark.parametrize("legacy, name", [(True, "vehicle"), (True, "dog"), (True, None), (False, None)])
def test_finish_retracks_without_old_labels_and_labels_empty_clips(tmp_path, monkeypatch, legacy, name):
    directory = tmp_path / "2026-09-29"
    directory.mkdir()
    sidecar = directory / "20-00-00.json"
    frames = [f"20-00-00.f{i}.jpg" for i in range(4)]
    boxes = [[0, 0, 0, 100, 100], [2, 50, 0, 100, 100]] if name else []
    tracks = [dict(id=0, **{"class": name}, boxes=boxes, labels={}, description="",
                   entry_edge="left", exit_edge="far")] if name else []
    tracking = dict(tracks=tracks, track=boxes, frames=frames, entry_edge="left", exit_edge="far")
    row = dict(clip="20-00-00.mp4", night=directory.name, start_utc="2026-09-29T20:00:00Z",
               duration_s=1, labels={"nous/a": {"label": "other", "confidence": .8}}, **tracking)
    if legacy:
        del row["tracks"]
    else:
        row.update(annotation_label=[], annotation_version=2)
    sidecar.write_text(json.dumps(row))
    for filename in [row["clip"], *frames, "20-00-00.t0.jpg", "20-00-00.t0.crop.jpg", "20-00-00.annotated.mp4"]:
        (directory / filename).touch()
    retrack = Mock(return_value=tracking)
    monkeypatch.setattr(pipeline, "track", retrack)
    hosted = Mock(return_value=("dog", .9, "a moving dog"))
    monkeypatch.setattr(pipeline, "classify", hosted)
    monkeypatch.setattr(pipeline, "annotate", lambda clip, target, *args: target.write_bytes(b"video"))
    config = dict(PRIMARY_MODEL="nous/a", MODELS=["nous/a"], MIN_BLOB_AREA=100, EDGE_MARGIN=80, MIN_TRACK_MOVE_RATIO=1.2)
    pipeline._finish(sidecar, config, date(2026, 1, 1))
    saved = json.loads(sidecar.read_text())
    assert saved["labels"]["nous/a"]["label"] == (name or "none")
    if name:
        assert saved["tracks"][0]["labels"] == saved["labels"]
    if name == "dog":
        hosted.assert_called_once()
    else:
        hosted.assert_not_called()
    if legacy:
        retrack.assert_called_once_with(directory / row["clip"], 100, 80, 1.2)
