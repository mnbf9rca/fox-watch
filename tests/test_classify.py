import pytest
from foxcam.classify import compare, parse_answer
from io import StringIO
import json
from unittest.mock import Mock

from foxcam import classify as classifier

def test_labels_and_comparison():
    assert parse_answer('{"label":"fox","confidence":0.9}') == ("fox", 0.9, "")
    assert parse_answer('I see a fox. {"label":"fox","confidence":0.9}') == ("fox", 0.9, "")
    assert parse_answer('```json\n{"label":"none","confidence":0}\n```') == ("none", 0.0, "")
    assert parse_answer('{"label":"dog","confidence":0.5,"description":"a dog"}') == ("dog", 0.5, "a dog")
    for text in ('{}', '[]', 'not JSON', '{"label":"wolf","confidence":1}',
                 '{"label":"fox","confidence":2}', '{"label":"fox","confidence":NaN}',
                 '{"label":"fox","confidence":true}', '{"label":"fox","confidence":"0.9"}',
                 '{"label":"fox","confidence":0.9,"description":1}'):
        with pytest.raises(ValueError):
            parse_answer(text)
    rows = [{"labels": {"nous/a": {"label": "fox", "confidence": 0.9},
                        "deepinfra/b": {"label": "fox", "confidence": 0.8},
                        "together/c": {"label": "unclassified", "confidence": 0}}}]
    assert compare(rows, "nous/a") == {"nous/a": (1, 1), "deepinfra/b": (1, 1), "together/c": (0, 0)}


def test_invalid_model_answer_logs_only_content_prefix(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("DEEPINFRA_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "secret-must-not-appear")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"private-image-must-not-appear")
    content = "invalid response " + "x" * 183 + "OMITTED_SUFFIX"
    response = json.dumps({"choices": [{"message": {"content": content}}]})
    monkeypatch.setattr(classifier.request, "build_opener", lambda *args: Mock(open=lambda *a, **kw: StringIO(response)))
    assert classifier.classify("deepinfra/qwen", [frame]) == ("unclassified", 0.0, "")
    assert content[:200] in caplog.text and "OMITTED_SUFFIX" not in caplog.text
    assert "secret-must-not-appear" not in caplog.text and "private-image-must-not-appear" not in caplog.text
