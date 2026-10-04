from datetime import date
import json
from unittest.mock import Mock

import pytest

from foxcam import pipeline


MODELS = ["nous/secondary", "deepinfra/primary", "nous/other"]
PRIMARY = MODELS[1]


@pytest.mark.parametrize("kind,primary_succeeds", [
    ("unknown", True), ("unknown", False), ("cat", True), ("cat", False),
    ("person", True), ("vehicle", True),
])
def test_models_retries_and_retention_follow_detector_class(tmp_path, monkeypatch, kind, primary_succeeds):
    directory = tmp_path / "2026-09-29"
    directory.mkdir()
    sidecar = directory / "20-00-00.json"
    clip = sidecar.with_suffix(".mp4")
    frames = [f"20-00-00.f{i}.jpg" for i in range(4)]
    boxes = [[0, 100, 100, 40, 40], [2, 140, 100, 40, 40]]
    # A previously failed secondary must neither be retried for unknowns nor
    # keep their completed raw clip forever. Preserve historical answers.
    labels = {MODELS[0]: dict(pipeline.UNCLASSIFIED)}
    item = dict(id=0, **{"class": kind}, boxes=boxes, labels=labels,
                description="", entry_edge="left", exit_edge="right")
    row = dict(clip=clip.name, night=directory.name, start_utc="2026-09-29T20:00:00Z",
               duration_s=1, labels=labels, tracks=[item], track=boxes, frames=frames,
               entry_edge="left", exit_edge="right", annotation_label=[], annotation_version=4)
    sidecar.write_text(json.dumps(row))
    for name in [clip.name, *frames, "20-00-00.t0.jpg", "20-00-00.t0.crop.jpg"]:
        (directory / name).write_bytes(b"media")
    def answer(model, images):
        return ("unclassified", 0, "") if model == PRIMARY and not primary_succeeds else ("cat", .9, "a cat")
    hosted = Mock(side_effect=answer)
    monkeypatch.setattr(pipeline, "classify", hosted)
    monkeypatch.setattr(pipeline, "annotate", lambda clip, target, *args: target.write_bytes(b"annotated"))
    config = dict(PRIMARY_MODEL=PRIMARY, MODELS=MODELS)
    pipeline._finish(sidecar, config, date(2026, 10, 1))
    expected = [PRIMARY] if kind == "unknown" else MODELS if kind == "cat" else []
    assert [call.args[0] for call in hosted.call_args_list] == expected
    saved = json.loads(sidecar.read_text())
    assert clip.exists() == (not primary_succeeds)
    if kind == "unknown":
        assert saved["labels"][MODELS[0]] == pipeline.UNCLASSIFIED
        assert MODELS[2] not in saved["labels"]
    elif kind in {"person", "vehicle"}:
        assert all(saved["labels"][model] == {"label": kind, "confidence": 1.0} for model in MODELS)
    hosted.reset_mock()
    pipeline._finish(sidecar, config, date(2026, 10, 1))
    assert [call.args[0] for call in hosted.call_args_list] == ([] if primary_succeeds else [PRIMARY])
