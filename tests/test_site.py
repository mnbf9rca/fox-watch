import json

import pytest
from foxcam.site import build_site, render_index, render_night

def test_pages_from_sidecars():
    visit = dict(clip="19-05-00.mp4", night="2026-09-28", start_utc="2026-09-28T19:05:00Z",
                 duration_s=12, entry_edge="left", exit_edge="far", track=[[0, 0, 50, 20, 20]],
                 frames=[f"19-05-00.f{i}.jpg" for i in range(4)],
                 labels={"nous/a": {"label": "fox", "confidence": 0.9},
                         "deepinfra/b": {"label": "cat", "confidence": 0.7}})
    html = render_night("2026-09-28", [visit], "nous/a")
    for text in ("Fox Watch", "fox", "cat", "left", "far", "19-05-00.f3.jpg", "19-05-00.annotated.mp4", "<svg", "marker-end"):
        assert text in html
    assert "No visits recorded" in render_night("2026-09-29", [], "nous/a")
    index = render_index({"2026-09-28": [visit], "2026-09-29": []}, "nous/a")
    assert index.index("2026-09-29") < index.index("2026-09-28")
    visit["labels"]["<script>"] = {"label": "none", "confidence": 0}
    assert "<script>" not in render_night("2026-09-28", [visit], "nous/a")
    assert "unclassified" in render_night("2026-09-28", [visit], "nous/missing")
    visit["clip"] = "../secret.mp4"
    with pytest.raises(ValueError):
        render_night("2026-09-28", [visit], "nous/a")


def test_build_skips_bad_sidecars_and_keeps_empty_nights(tmp_path, caplog):
    night = tmp_path / "nights/2026-09-28"
    night.mkdir(parents=True)
    (tmp_path / "nights/2026-09-29").mkdir()
    visit = dict(clip="19-05-00.mp4", night=night.name, start_utc="2026-09-28T19:05:00Z",
                 duration_s=12, entry_edge="unknown", exit_edge="unknown", track=[],
                 frames=[f"19-05-00.f{i}.jpg" for i in range(4)],
                 labels={"nous/a": {"label": "fox", "confidence": 0.9}})
    (night / "19-05-00.json").write_text(json.dumps(visit))
    (night / "broken.json").write_text("{")
    (night / "missing.json").write_text("{}")
    visit["frames"][3] = "../secret.jpg"
    (night / "unsafe.json").write_text(json.dumps(visit))
    build_site(tmp_path, "nous/a")
    page = (tmp_path / "site/2026-09-28.html").read_text()
    assert page.count("<article") == 1
    assert "unknown" in page and "UTC" in page and "8" in page
    assert '/nights/2026-09-28/19-05-00.f3.jpg' in page
    assert "No visits recorded" in (tmp_path / "site/2026-09-29.html").read_text()
    assert "fox: 1" in (tmp_path / "site/index.html").read_text()
    assert all(name in caplog.text for name in ("broken.json", "missing.json", "unsafe.json"))
    assert not list((tmp_path / "site").glob("*.tmp"))
