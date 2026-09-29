import pytest
from foxcam.classify import compare, parse_answer

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
