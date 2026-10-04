from datetime import date
import json
from unittest.mock import Mock

import pytest

from foxcam import pipeline
from foxcam.site import render_night


def test_classify_defaults_on_and_validates_switch_and_models(monkeypatch):
    monkeypatch.setenv('MODELS', 'nous/test')
    monkeypatch.setenv('PRIMARY_MODEL', 'nous/test')
    monkeypatch.delenv('CLASSIFY', raising=False)
    assert pipeline.load_config()['CLASSIFY'] == 'on'
    monkeypatch.setenv('CLASSIFY', 'invalid')
    with pytest.raises(ValueError, match='CLASSIFY'):
        pipeline.load_config()
    monkeypatch.setenv('CLASSIFY', 'on')
    monkeypatch.setenv('MODELS', '')
    monkeypatch.setenv('PRIMARY_MODEL', '')
    with pytest.raises(ValueError, match='MODELS'):
        pipeline.load_config()
    monkeypatch.setenv('CLASSIFY', 'off')
    config = pipeline.load_config()
    assert config['CLASSIFY'] == 'off'
    assert config['MODELS'] == []


@pytest.mark.parametrize('legacy', [False, True])
def test_off_uses_detector_labels_preserves_answers_and_never_calls_hosted(tmp_path, monkeypatch, legacy):
    directory = tmp_path / '2026-09-29'
    directory.mkdir()
    sidecar = directory / '20-00-00.json'
    frames = [f'20-00-00.f{i}.jpg' for i in range(4)]
    historical = {'nous/saved': {'label': 'fox', 'confidence': .9},
                  'nous/retry': dict(pipeline.UNCLASSIFIED)}
    kinds = ['person', 'vehicle', 'car', 'dog', 'cat', 'bird', 'horse', 'sheep', 'cow', 'bear', 'unknown']
    boxes = [[0, 100, 100, 40, 40], [2, 140, 100, 40, 40]]
    tracks = [dict(id=i, **{'class': kind}, boxes=boxes, labels=dict(historical),
                   description='', entry_edge='left', exit_edge='right',
                   ground_track=[[0, 0, 2], [2, 1, 3]]) for i, kind in enumerate(kinds)]
    row = dict(clip='20-00-00.mp4', night=directory.name, start_utc='2026-09-29T20:00:00Z',
               duration_s=1, labels=historical, tracks=tracks, track=boxes, frames=frames,
               entry_edge='left', exit_edge='right', annotation_version=4, annotation_label=[])
    if legacy:
        del row['tracks']
        monkeypatch.setattr(pipeline, 'track', lambda *a, **kw: dict(tracks=tracks))
    sidecar.write_text(json.dumps(row))
    for name in [row['clip'], *frames, *[f'20-00-00.t{i}{suffix}.jpg' for i in range(len(kinds)) for suffix in ('', '.crop')]]:
        (directory / name).touch()
    hosted = Mock(side_effect=AssertionError('hosted call while CLASSIFY=off'))
    monkeypatch.setattr(pipeline, 'classify', hosted)
    rendered = []
    def annotate(clip, target, tracks, captions, stamp):
        rendered.append(captions)
        target.write_bytes(b'annotated')
    monkeypatch.setattr(pipeline, 'annotate', annotate)
    config = dict(CLASSIFY='off', MODELS=['nous/retry'], PRIMARY_MODEL='nous/retry',
                  MIN_BLOB_AREA=45, EDGE_MARGIN=120, MIN_TRACK_MOVE_RATIO=.75)
    pipeline._finish(sidecar, config, date(2026, 1, 1))
    saved = json.loads(sidecar.read_text())
    expected = ['vehicle' if kind == 'car' else kind for kind in kinds]
    assert [label for label, confidence in saved['annotation_label']] == expected
    assert [caption.split()[0] for caption in rendered[0]] == expected
    for item in [saved, *saved['tracks']]:
        for model, answer in historical.items():
            assert item['labels'][model] == answer
    page = render_night(directory.name, [saved], 'detector')
    assert 'Ground paths' in page and '<path d="M 0 -2 L 1 -3"' in page
    for label in expected:
        assert f'{label} (' in page
    # Off mode ignores pending hosted answers for retries and retention.
    pipeline._finish(sidecar, config, date(2026, 10, 1))
    hosted.assert_not_called()
    assert not sidecar.with_suffix('.mp4').exists()
    assert len(rendered) == 1
