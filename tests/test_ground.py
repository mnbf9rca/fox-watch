import json
import math
from pathlib import Path

import pytest


def test_ground_mapping_uses_bottom_centre_and_rescales_recording():
    from foxcam.ground import ground_track

    calibration = {"image_size": [1920, 1080],
                   "homography": [[0.01, 0, 0], [0, 0.01, 0], [0, 0, 1]]}
    assert ground_track([[7, 100, 200, 40, 60]], 1920, 1080, calibration) == [[7, 1.2, 2.6]]
    assert ground_track([[7, 50, 100, 20, 30]], 960, 540, calibration) == [[7, 1.2, 2.6]]
    assert ground_track([[7, 120, 240, 48, 72]], 2304, 1296, calibration) == [[7, 1.2, 2.6]]


def test_horizon_nonfinite_and_unbounded_projection_preserve_frame_rows():
    from foxcam.ground import ground_track

    calibration = {"image_size": [100, 100],
                   "homography": [[1, 0, 0], [0, 0, 1], [0, 1, -50]]}
    result = ground_track([[3, 10, 40, 20, 10], [4, 10, 39, 20, 10],
                           [5, float("nan"), 60, 20, 10], [6, 10, 49.000001, 20, 1],
                           [7, 10, 60, 20, 10]], 100, 100, calibration)
    assert result[:4] == [[3, None, None], [4, None, None], [5, None, None], [6, None, None]]
    assert result[4] == pytest.approx([7, 1, 0.05])
    assert "NaN" not in json.dumps(result, allow_nan=False)


def test_calibration_loader_is_optional_and_rejects_invalid_matrices(tmp_path):
    from foxcam.ground import ground_track, load_calibration

    assert load_calibration("") is None
    assert load_calibration(None) is None
    assert ground_track([[4, 0, 0, 10, 10]], 1920, 1080, None) == [[4, None, None]]
    target = tmp_path / "calibration.json"
    for matrix in ([[1, 2]], [[0, 0, 0]] * 3, [[float("nan"), 0, 0], [0, 1, 0], [0, 0, 1]]):
        target.write_text(json.dumps({"image_size": [1920, 1080], "homography": matrix}))
        with pytest.raises(ValueError):
            load_calibration(target)
    target.write_text(json.dumps({"image_size": [0, 1080], "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}))
    with pytest.raises(ValueError):
        load_calibration(target)


def test_measured_eight_point_fit_and_residuals():
    from foxcam.ground import ground_track, load_calibration

    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    pairs = [(881, 735, -.30, 1.98), (858, 582, -.65, 3.95), (847, 593, -.71, 4.15),
             (1874, 514, 1.84, 4.54), (156, 582, -3.03, 5.41), (1597, 439, 2.07, 8.24),
             (723, 484, -2.13, 8.80), (1281, 444, .64, 8.78)]
    boxes = [[i, x - 3, y - 30, 6, 30] for i, (x, y, _, _) in enumerate(pairs)]
    mapped = ground_track(boxes, 2304, 1296, calibration)
    errors = [math.hypot(a - expected_a, f - expected_f)
              for (_, a, f), (_, _, expected_a, expected_f) in zip(mapped, pairs)]
    assert len(calibration["points"]) == 8
    assert math.sqrt(sum(error ** 2 for error in errors) / 8) == pytest.approx(0.2038601506, abs=1e-8)
    assert max(errors) == pytest.approx(0.3049634949, abs=1e-8)
    assert calibration["fit"]["rms_radial_m"] == pytest.approx(0.2038601506, abs=1e-8)
    assert calibration["fit"]["max_radial_m"] == pytest.approx(0.3049634949, abs=1e-8)
    assert calibration["points"][0]["image_recording_px"] == pytest.approx([734.1666666667, 612.5])


def test_garden_mapping_rejects_shrub_top_horizon_artifacts():
    from foxcam.ground import ground_track, load_calibration

    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    # At the image centre these bottoms project to about 34.7 m and 17 m;
    # the patio wall is only 9.5 m away.
    boxes = [[0, 950, 280, 20, 20], [1, 950, 310, 20, 20], [2, 950, 380, 20, 20]]
    mapped = ground_track(boxes, 1920, 1080, calibration)
    assert mapped[:2] == [[0, None, None], [1, None, None]]
    assert 0 < mapped[2][2] < 12


def test_ground_forward_limit_includes_twelve_metres():
    from foxcam.ground import ground_track

    calibration = {"image_size": [1920, 1080],
                   "homography": [[.01, 0, 0], [0, .1, 0], [0, 0, 1]]}
    boxes = [[0, 0, 109, 10, 10], [1, 0, 110, 10, 10], [2, 0, 111, 10, 10]]
    mapped = ground_track(boxes, 1920, 1080, calibration)
    assert mapped[0] == pytest.approx([0, .05, 11.9])
    assert mapped[1] == [1, .05, 12]
    assert mapped[2] == [2, None, None]


@pytest.mark.parametrize("polygon", [[], [[0, 0], [1, 1]],
    [[0, 0], [float("nan"), 2], [3, 4]], [[0, 0], [1921, 0], [3, 4]],
    [[0, 0], [1, 1], [2, 2]]])
def test_calibration_rejects_invalid_motion_polygon(tmp_path, polygon):
    from foxcam.ground import load_calibration

    target = tmp_path / "calibration.json"
    target.write_text(json.dumps({"image_size": [1920, 1080],
        "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "motion_polygon": polygon}))
    with pytest.raises(ValueError, match="motion polygon"):
        load_calibration(target)
