import json
import math

import pytest

from foxcam.ground import ground_track, load_calibration


def physical(**pose):
    return {"image_size": [200, 200],
            "camera": {"focal_length_px": 100, "height_m": 1,
                       "pitch_deg": 0, "roll_deg": 0, "yaw_deg": 0, **pose},
            "ground_plane": [0, 0, 0]}


def test_pinhole_intersection_uses_bottom_centre_and_recording_scale(tmp_path):
    calibration = physical()
    path = tmp_path / "physical.json"
    path.write_text(json.dumps(calibration))
    assert load_calibration(path) == calibration
    assert ground_track([[7, 110, 100, 20, 20]], 200, 200, calibration) == [[7, 1, 5]]
    assert ground_track([[7, 55, 50, 10, 10]], 100, 100, calibration) == [[7, 1, 5]]
    assert ground_track([[7, 220, 200, 40, 40]], 400, 400, calibration) == [[7, 1, 5]]


def test_rays_parallel_behind_or_beyond_twelve_metres_stay_null():
    calibration = physical()
    boxes = [[0, 90, 80, 20, 20], [1, 90, 60, 20, 20],
             [2, 90, 85, 20, 20], [3, 90, 100, 20, 20]]
    assert ground_track(boxes, 200, 200, calibration) == [
        [0, None, None], [1, None, None], [2, None, None], [3, 0, 5]]


@pytest.mark.parametrize("pose,box,expected", [
    ({"pitch_deg": 30}, [0, 90, 80, 20, 20], [0, 0, math.sqrt(3)]),
    ({"roll_deg": 90}, [0, 110, 80, 20, 20], [0, 0, 5]),
    ({"yaw_deg": 30}, [0, 90, 100, 20, 20], [0, 2.5, 5 * math.cos(math.pi / 6)]),
])
def test_camera_pitch_roll_and_yaw_conventions(pose, box, expected):
    assert ground_track([box], 200, 200, physical(**pose))[0] == pytest.approx(expected)


def test_sloping_ground_uses_ray_plane_intersection():
    calibration = physical()
    calibration["ground_plane"] = [0, .05, .1]
    # ray [across=.2, forward=1, up=-.2]; t = 1/(.2+.05*.2+.1).
    t = 1 / .31
    assert ground_track([[0, 110, 100, 20, 20]], 200, 200, calibration)[0] == pytest.approx([0, .2*t, t])


@pytest.mark.parametrize("field,value", [("focal_length_px", 0), ("height_m", -1),
                                         ("pitch_deg", float("nan"))])
def test_invalid_camera_parameters_are_rejected(tmp_path, field, value):
    calibration = physical(**{field: value})
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(calibration))
    with pytest.raises(ValueError):
        load_calibration(path)
