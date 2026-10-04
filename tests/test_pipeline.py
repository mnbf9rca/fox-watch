from datetime import date
import json
from unittest.mock import Mock

import pytest

from foxcam import pipeline


def test_sidecar_loader_repairs_day_from_folder(tmp_path, caplog):
    directory = tmp_path / "nights/2026-09-29"
    directory.mkdir(parents=True)
    sidecar = directory / "23-30-00.json"
    row = dict(clip="23-30-00.mp4", night="2026-09-28", start_utc="2026-09-28T23:30:00Z",
               duration_s=1, labels={}, track=[], tracks=[], entry_edge="unknown", exit_edge="unknown",
               frames=[f"23-30-00.f{i}.jpg" for i in range(4)])
    sidecar.write_text(json.dumps(row))
    loaded = pipeline.read_sidecar(sidecar, "nous/a")
    assert loaded == row | {"night": directory.name}
    assert str(sidecar) in caplog.text and "2026-09-28" in caplog.text and "2026-09-29" in caplog.text
    assert json.loads(sidecar.read_text()) == loaded
    # Repair must not bypass the existing media-reference validation.
    row["frames"][0] = "../outside.jpg"
    sidecar.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        pipeline.read_sidecar(sidecar, "nous/a")
    assert json.loads(sidecar.read_text()) == row


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
        row.update(annotation_label=[], annotation_version=4)
    sidecar.write_text(json.dumps(row))
    for filename in [row["clip"], *frames, "20-00-00.t0.jpg", "20-00-00.t0.crop.jpg", "20-00-00.annotated.mp4"]:
        (directory / filename).touch()
    retrack = Mock(return_value=tracking)
    monkeypatch.setattr(pipeline, "track", retrack)
    hosted = Mock(return_value=("dog", .9, "a moving dog"))
    monkeypatch.setattr(pipeline, "classify", hosted)
    monkeypatch.setattr(pipeline, "annotate", lambda clip, target, *args: target.write_bytes(b"video"))
    config = dict(PRIMARY_MODEL="nous/a", MODELS=["nous/a"], MIN_BLOB_AREA=100, EDGE_MARGIN=80, MIN_TRACK_MOVE_RATIO=1.2,
                  GROUND_CALIBRATION={"image_size": [1920, 1080], "homography": [[.001, 0, 0], [0, .001, 0], [0, 0, 1]]})
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
        retrack.assert_called_once_with(directory / row["clip"], 100, 80, 1.2,
                                        ground_calibration=config["GROUND_CALIBRATION"])


@pytest.mark.parametrize("raw_exists", [True, False])
def test_bottom_centre_annotation_upgrade_is_once_only_and_preserves_expired_video(tmp_path, monkeypatch, raw_exists):
    directory = tmp_path / "2026-09-29"
    directory.mkdir()
    sidecar = directory / "20-00-00.json"
    clip, annotated = sidecar.with_suffix(".mp4"), sidecar.with_suffix(".annotated.mp4")
    frames = [f"20-00-00.f{i}.jpg" for i in range(4)]
    answer = {"label": "person", "confidence": 1.0}
    boxes = [[0, 100, 70, 40, 100], [2, 260, 70, 40, 100]]
    item = dict(id=0, **{"class": "person"}, boxes=boxes, labels={"nous/a": answer},
                description="", entry_edge="left", exit_edge="right")
    row = dict(clip=clip.name, night=directory.name, start_utc="2026-09-29T20:00:00Z",
               duration_s=1, labels={"nous/a": answer}, tracks=[item], track=boxes,
               frames=frames, entry_edge="left", exit_edge="right",
               annotation_label=[["person", 1.0]], annotation_version=3)
    sidecar.write_text(json.dumps(row))
    annotated.write_bytes(b"old video")
    if raw_exists:
        clip.touch()
    for name in [*frames, "20-00-00.t0.jpg", "20-00-00.t0.crop.jpg"]:
        (directory / name).touch()
    render = Mock(side_effect=lambda clip, target, *args: target.write_bytes(b"new video"))
    monkeypatch.setattr(pipeline, "annotate", render)
    config = dict(PRIMARY_MODEL="nous/a", MODELS=["nous/a"])
    pipeline._finish(sidecar, config, date(2026, 1, 1))
    assert annotated.read_bytes() == (b"new video" if raw_exists else b"old video")
    assert json.loads(sidecar.read_text())["annotation_version"] == 4
    pipeline._finish(sidecar, config, date(2026, 1, 1))
    assert render.call_count == int(raw_exists)
