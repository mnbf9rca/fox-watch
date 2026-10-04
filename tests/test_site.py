import json
import re

import pytest
from foxcam.classify import LABELS
from foxcam.site import PALETTE, build_site, render_index, render_night


def test_palette_covers_every_label():
    assert set(LABELS) <= PALETTE.keys()

def test_pages_from_sidecars():
    visit = dict(clip="19-05-00.mp4", night="2026-09-28", start_utc="2026-09-28T19:05:00Z",
                 duration_s=12, entry_edge="left", exit_edge="far", track=[[0, 0, 50, 20, 20]],
                 frames=[f"19-05-00.f{i}.jpg" for i in range(4)],
                 labels={"nous/a": {"label": "fox", "confidence": 0.9},
                         "deepinfra/b": {"label": "cat", "confidence": 0.7}})
    html = render_night("2026-09-28", [visit], "nous/a")
    for text in ("Fox Watch", "fox", "cat", "left", "far", "19-05-00.f3.jpg", "19-05-00.annotated.mp4", "<svg"):
        assert text in html
    assert "No visits recorded" in render_night("2026-09-29", [], "nous/a")
    index = render_index({"2026-09-28": [visit], "2026-09-29": []}, "nous/a")
    assert index.index("2026-09-29") < index.index("2026-09-28")
    visit["labels"]["<script>"] = {"label": "none", "confidence": 0}
    assert "<script>" not in render_night("2026-09-28", [visit], "nous/a")
    assert "unclassified" in render_night("2026-09-28", [visit], "nous/missing")
    visit["tracks"] = [dict(id=0, class_="dog", labels={"nous/a": {"label": "dog", "confidence": 0.8}},
                            description="a dog trotting <outside>", entry_edge="left", exit_edge="far",
                            boxes=[[0, 0, 50, 20, 20]]),
                       dict(id=1, class_="person", labels={"nous/a": {"label": "person", "confidence": 1.0}},
                            description="", entry_edge="right", exit_edge="left", boxes=[[0, 500, 50, 20, 60]])]
    for item in visit["tracks"]:
        item["class"] = item.pop("class_")
    html = render_night("2026-09-28", [visit], "nous/a")
    assert "marker-end" not in html and "a dog trotting &lt;outside&gt;" in html
    assert 'id="label-dog"' in html and "dog (1)" in html and 'class="label-dog"' in html
    assert "#label-dog:not(:checked) ~ .hours .label-dog" in html
    assert "dog (80%)" in html and "person (100%)" in html and "<script>" not in html
    assert "dog (2)" in render_night("2026-09-28", [visit, visit], "nous/a")
    visit["tracks"] = []
    assert "marker-end" not in render_night("2026-09-28", [visit], "nous/a")
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
    assert "unknown" in page and "BST" in page and "8" in page
    assert '/nights/2026-09-28/19-05-00.f3.jpg' in page
    assert "No visits recorded" in (tmp_path / "site/2026-09-29.html").read_text()
    assert "fox: 1" in (tmp_path / "site/index.html").read_text()
    assert all(name in caplog.text for name in ("broken.json", "missing.json", "unsafe.json"))
    assert not list((tmp_path / "site").glob("*.tmp"))


def _visit(labels, stamp="2026-09-28T19:05:00Z"):
    tracks = [dict(id=i, labels={"nous/a": {"label": label, "confidence": 1.0}},
                   entry_edge="left", exit_edge="far", boxes=[[0, 0, 50, 20, 20]])
              for i, label in enumerate(labels)]
    return dict(clip="19-05-00.mp4", night="2026-09-28", start_utc=stamp, duration_s=12,
                entry_edge="left", exit_edge="far", track=tracks[0]["boxes"], tracks=tracks,
                frames=[f"19-05-00.f{i}.jpg" for i in range(4)], labels=tracks[0]["labels"])


def test_interest_filters_and_all_track_headings():
    animals = ("fox", "hedgehog", "badger", "deer", "cat", "dog", "rat", "mouse", "bird", "other")
    cases = [(animal, ["vehicle", "person", animal]) for animal in animals]
    cases += [("person", ["vehicle", "person"]), ("vehicle", ["none", "vehicle"]),
              ("person", ["unclassified", "person"])]
    for expected, labels in cases:
        visit = _visit(labels)
        if "unclassified" in labels:
            visit["tracks"][0]["labels"]["nous/a"]["confidence"] = 0
        html = render_night("2026-09-28", [visit], "nous/a")
        assert f'class="label-{expected}"' in html
        assert f'{expected} (1)</label>' in html
        heading = re.search(r"<h3>(.*?)</h3>", html)[1]
        assert all(label in heading for label in labels)


def test_default_ticks_local_hour_groups_and_lazy_images(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/London")
    monkeypatch.setenv("STOP_TIME", "07:00")
    monkeypatch.setenv("START_TIME", "19:00")
    visits = [_visit([label], "2026-09-28T" + stamp + "Z") for label, stamp in [
        ("dog", "05:59:00"), ("none", "06:00:00"), ("dog", "06:15:00"),
        ("vehicle", "17:59:00"), ("person", "18:00:00")]]
    html = render_night("2026-09-28", visits, "nous/a")
    assert '<input type="checkbox" id="label-none">' in html
    for label in ("dog", "vehicle", "person", "daytime"):
        assert f'<input type="checkbox" id="label-{label}" checked>' in html
    assert re.findall(r'<article class="([^"]+)"', html) == [
        "label-dog", "label-none daytime", "label-dog daytime", "label-vehicle daytime", "label-person"]
    assert html.count('<details open>') == 4
    assert '<summary>2026-09-28 07:00 BST (2)</summary>' in html
    assert html.count('loading="lazy"') == 5
    assert '#label-none:not(:checked) ~ .hours .label-none { display: none }' in html
    assert '#label-daytime:not(:checked) ~ .hours .daytime { display: none }' in html
    assert html.index('id="label-none"') < html.index('<svg') < html.index('<div class="hours">')
    assert '<script' not in html


def test_daytime_respects_config_and_groups_distinct_dst_hours(monkeypatch):
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.setenv("STOP_TIME", "08:00")
    monkeypatch.setenv("START_TIME", "18:00")
    visits = [_visit(["dog"], f"2026-09-28T{stamp}Z") for stamp in ("07:59:00", "08:00:00", "18:00:00")]
    html = render_night("2026-09-28", visits, "nous/a")
    assert re.findall(r'<article class="([^"]+)"', html) == ["label-dog", "label-dog daytime", "label-dog"]
    monkeypatch.setenv("TZ", "Europe/London")
    visits = [_visit(["dog"], f"2026-10-25T{stamp}Z") for stamp in ("00:30:00", "01:30:00")]
    html = render_night("2026-09-28", visits, "nous/a")
    assert '<summary>2026-10-25 01:00 BST (1)</summary>' in html
    assert '<summary>2026-10-25 01:00 GMT (1)</summary>' in html


def test_all_displayed_times_are_local_and_index_lists_days(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/London")
    visit = _visit(["dog", "person"], "2026-09-28T20:13:00Z")
    for item in visit["tracks"]:
        item["ground_track"] = [[0, -1, 2], [1, 0, 4]]
    html = render_night("2026-09-28", [visit], "nous/a")
    assert "UTC" not in html and "All days" in html and "All nights" not in html
    assert "21:13 BST" in re.search(r"<h3>(.*?)</h3>", html)[1]
    assert 'title="' in html and "21:13 BST" in re.search(r'<article[^>]*title="([^"]+)"', html)[1]
    tooltips = re.findall(r'<path[^>]*marker-end=[^>]*><title>(.*?)</title>', html)
    assert len(tooltips) == 2 and all("21:13 BST" in title for title in tooltips)
    index = render_index({"2026-09-28": [visit]}, "nous/a")
    assert "Fox Watch — Days" in index and "Nights" not in index


def test_map_uses_measured_paths_and_keeps_legacy_edges_as_text():
    visit = _visit(["fox", "bird"])
    visit["tracks"][0]["ground_track"] = [[0, -1, 2], [1, 0, 4], [2, None, None],
                                           [3, 1, 5], [4, 5, 6]]
    visit["tracks"][0]["description"] = "<script>alert(1)</script>"
    html = render_night("2026-09-28", [visit], "nous/a")
    paths = re.findall(r'<path d="([^"]+)"[^>]*marker-end=', html)
    assert paths == ["M -1 -2 L 0 -4 M 1 -5 L 5 -6"]
    assert '<polygon ' in html and "clip-path" not in html
    assert "fence / near" in html and "Camera (0, 0)" in html
    assert '<line x1="-4" y1=".6" x2="-3" y2=".6"' in html and ">1 m</text>" in html
    assert "approximate" in html.lower() and "4°" in html and "8.8" in html
    assert "airborne birds" in html.lower() and "ground-plane" in html
    assert "left → far" in html and "Ground position unavailable" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "Unknown endpoints use the centre" not in html


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), "\"/><script>", True])
def test_map_rejects_non_numeric_or_nonfinite_sidecar_ground_coordinates(coordinate):
    visit = _visit(["fox"])
    visit["tracks"][0]["ground_track"] = [[0, coordinate, 2], [1, 0, 4]]
    with pytest.raises(ValueError):
        render_night("2026-09-28", [visit], "nous/a")


def test_map_extreme_finite_points_break_paths_and_single_points_are_visible():
    visit = _visit(["fox"])
    visit["tracks"][0]["ground_track"] = [[0, -1, 2], [1, 1e200, 2], [2, 1, 3]]
    html = render_night("2026-09-28", [visit], "nous/a")
    assert "1e+200" not in html and "marker-end" not in html
    assert re.findall(r'<circle cx="([^"]+)" cy="([^"]+)"', html) == [("-1", "-2"), ("1", "-3")]


def test_map_bounds_include_nearby_paths_but_reject_distant_sidecar_points():
    visit = _visit(["fox"])
    visit["tracks"][0]["ground_track"] = [[0, 5, 11], [1, 7, 3], [2, 1, 34.7],
                                           [3, 1, 17], [4, 0, 12], [5, 1, 12.01]]
    html = render_night("2026-09-28", [visit], "nous/a")
    x, y, width, height = map(float, re.search(r'<svg viewBox="([^"]+)"', html)[1].split())
    assert x <= 4.5 and x + width >= 7.5
    assert y == -12 and y + height >= -.5
    assert '<circle cx="0" cy="-12"' in html
    assert "-34.7" not in html and "-17" not in html and "-12.01" not in html
    assert x <= -5 and x + width >= 6 and y + height >= 1
    assert 'd="M 5 -11 L 7 -3"' in html
    legacy = render_night("2026-09-28", [_visit(["fox"])], "nous/a")
    assert '<svg viewBox="-5 -10 11 11"' in legacy
