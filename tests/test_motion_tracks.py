"""Real motion segmentation with only the object detector stubbed."""
import cv2
import numpy as np
import pytest

from foxcam.media import _unmatched_motion, track


def moving_scene(tmp_path, monkeypatch, *, known=True, extras=1, start=10, detector_start=10, step=12):
    source = tmp_path / "mixed.mp4"
    writer = cv2.VideoWriter(str(source), cv2.VideoWriter_fourcc(*"mp4v"), 10, (1920, 1080))
    assert writer.isOpened()
    detections = []
    try:
        for frame in range(40):
            image = np.full((1080, 1920, 3), 30, dtype=np.uint8)
            found = []
            if frame >= start:
                x = 150 + step * (frame - start)
                cv2.rectangle(image, (x, 200), (x + 120, 280), (180, 180, 180), -1)
                if known and frame >= detector_start:
                    found = [("cat", .9, x - 6, 194, 132, 92)]
                for index in range(extras):
                    # 25 x 12 cm at 9 m: 41 x 20 px at recording resolution.
                    cv2.ellipse(image, (200 + step * (frame - start), 650 + index * 200),
                                (20, 9), 0, 0, 360, (180, 180, 180), -1)
                # Below threshold, plus a large stationary newly appearing patch.
                cv2.rectangle(image, (1200 + frame * 6, 500), (1203 + frame * 6, 503), (180, 180, 180), -1)
                cv2.rectangle(image, (1400, 700), (1460, 760), (180, 180, 180), -1)
            writer.write(image)
            if frame % 2 == 0:
                detections.append(found)
    finally:
        writer.release()
    found = iter(detections)
    monkeypatch.setattr("foxcam.media.detect", lambda image: next(found))
    return track(source, 25, 120)


@pytest.mark.parametrize("extras", [1, 2])
def test_small_unknown_animals_survive_alongside_detected_cat(tmp_path, monkeypatch, extras):
    result = moving_scene(tmp_path, monkeypatch, extras=extras)
    assert [t["class"] for t in result["tracks"]].count("cat") == 1
    unknown = [t for t in result["tracks"] if t["class"] == "unknown"]
    assert len(unknown) == extras
    assert len({t["id"] for t in result["tracks"]}) == extras + 1
    for item in unknown:
        assert len(item["boxes"]) > 10
        assert all(600 < box[2] < 900 and box[3] < 60 for box in item["boxes"])


def test_matched_motion_and_static_noise_add_no_unknown(tmp_path, monkeypatch):
    result = moving_scene(tmp_path, monkeypatch, extras=0)
    assert [t["class"] for t in result["tracks"]] == ["cat"]


def test_multiple_unknown_animals_are_separate_tracks(tmp_path, monkeypatch):
    result = moving_scene(tmp_path, monkeypatch, known=False, extras=2)
    assert len(result["tracks"]) == 3
    assert all(t["class"] == "unknown" for t in result["tracks"])
    assert len({t["id"] for t in result["tracks"]}) == 3


def test_motion_overlap_uses_detector_gaps_and_unsampled_final_frame():
    # A sampled detection gap must not turn the same animal into an unknown.
    known = [{"boxes": [[0, 100, 100, 40, 20], [6, 220, 100, 40, 20]]}]
    overlapping = ("unknown", 1.0, 165, 105, 10, 10)
    separate = ("unknown", 1.0, 165, 200, 10, 10)
    final = ("unknown", 1.0, 225, 105, 10, 10)
    assert _unmatched_motion([(3, [overlapping, separate]), (7, [final]), (8, [final])], known) == [
        (3, [separate]), (7, []), (8, [final]),
    ]


def test_static_detector_track_still_suppresses_its_motion():
    known = [{"boxes": [[0, 100, 100, 40, 20], [2, 100, 100, 40, 20]]}]
    motion = [(1, [("unknown", 1.0, 110, 105, 10, 10)])]
    assert _unmatched_motion(motion, known) == [(1, [])]


def test_late_detector_does_not_duplicate_leading_motion(tmp_path, monkeypatch):
    result = moving_scene(tmp_path, monkeypatch, extras=1, start=1, detector_start=10, step=14)
    assert [item["class"] for item in result["tracks"]].count("cat") == 1
    unknown = [item for item in result["tracks"] if item["class"] == "unknown"]
    assert len(unknown) == 1, "late cat detection left a duplicate unknown track"
    assert all(box[2] > 600 for box in unknown[0]["boxes"])


def test_first_detector_box_covers_only_preceding_miss_window():
    known = [{"boxes": [[30, 100, 100, 40, 20]]}]
    same = ("unknown", 1.0, 110, 105, 10, 10)
    separate = ("unknown", 1.0, 110, 200, 10, 10)
    motion = [(9, [same]), (10, [same, separate]), (29, [same])]
    assert _unmatched_motion(motion, known) == [(9, [same]), (10, [separate]), (29, [])]
