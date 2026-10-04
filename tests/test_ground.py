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


def test_selected_survey_fit_and_runtime_residuals():
    from foxcam.ground import ground_track, load_calibration

    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    assert "camera" not in calibration
    assert "homography" in calibration
    assert len(calibration["points"]) == 17
    scores = calibration["cross_validation"]["models"]
    assert calibration["model"] == min(scores, key=lambda name: scores[name]["rms_radial_m"])
    assert calibration["model"] == "old_8_bottle_homography"
    errors = []
    for i, point in enumerate(calibration["points"]):
        x, y = point["image_measurement_px"]
        mapped = ground_track([[i, x - 3, y - 30, 6, 30]], 2304, 1296, calibration)[0][1:]
        assert mapped == pytest.approx(point["fitted_ground_m"])
        error = math.dist(mapped, point["measured_ground_m"])
        assert error == pytest.approx(point["radial_error_m"])
        errors.append(error)
    assert math.sqrt(sum(error ** 2 for error in errors) / 17) == pytest.approx(.5849001826)
    assert max(errors) == pytest.approx(1.9673165383)
    assert calibration["fit"]["rms_radial_m"] == pytest.approx(.5849001826)
    for score in scores.values():
        assert len(score["radial_errors_m"]) == 17
        assert score["rms_radial_m"] == pytest.approx(
            math.sqrt(sum(e**2 for e in score["radial_errors_m"]) / 17))


def test_garden_mapping_rejects_shrub_top_horizon_artifacts():
    from foxcam.ground import ground_track, load_calibration

    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    # These shrub-top bottoms project beyond the 12 m bound;
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
