import numpy as np
import pytest

from fit_ground import camera_rotation


def test_plane_least_squares_uses_all_confirmed_survey_elevations():
    from fit_ground import fit_plane

    survey = np.array([[-1.22, 2.04, -.380], [-1.15, 2.99, -.370], [-1.10, 4.12, -.340],
                       [1.92, 3.80, -.260], [-3.30, 5.91, -.340], [2.45, 7.71, -.100],
                       [-2.35, 9.15, -.100], [.74, 9.52, .002]])
    plane = fit_plane(survey, height_m=.327)
    design = np.column_stack([np.ones(8), survey[:, :2]])
    errors = design @ plane - (survey[:, 2] + .327)
    assert design.T @ errors == pytest.approx([0, 0, 0], abs=1e-10)
    assert plane == pytest.approx([-.15404903, .02541962, .04558632], abs=1e-8)


def test_rotation_fit_recovers_known_pose_without_changing_intrinsics_or_height():
    from fit_ground import fit_rotation

    camera = dict(focal_length_px=1774 * 5 / 6, height_m=.327,
                  pitch_deg=8, roll_deg=1, yaw_deg=-2)
    plane = np.array([-.15, .02, .04])
    ground = np.array([(x, y) for y in (2, 5, 9) for x in (-1, 0, 1)])
    elevation = plane[0] + ground @ plane[1:]
    world = np.column_stack([ground, elevation - camera["height_m"]])
    local = world @ camera_rotation(camera)
    pixels = local[:, :2] / local[:, 2:] * camera["focal_length_px"] + [960, 540]
    angles = fit_rotation(pixels, ground, plane, camera, [1920, 1080])
    assert angles == pytest.approx([8, 1, -2], abs=1e-6)
    assert camera["focal_length_px"] == 1774 * 5 / 6 and camera["height_m"] == .327


def test_confirmed_farther_slab_is_in_fit_but_unlocated_nearer_slab_is_not():
    from fit_ground import SURVEY

    assert len(SURVEY) == 9
    assert ("Laser 5", 863, 518, -1.08, 6.66, -.195) in SURVEY
    assert not any(row[0] == "Laser 5a" for row in SURVEY)


@pytest.mark.parametrize('held', [0, 8])
def test_cross_validation_excludes_held_ground_and_elevation(held):
    from fit_ground import BOTTLES, SURVEY, leave_one_out

    rows = BOTTLES + SURVEY
    predictions = leave_one_out(rows)
    changed = list(rows)
    row = list(changed[held])
    row[3] += .25
    row[4] += .4
    if len(row) == 6:
        row[5] += .05
    changed[held] = tuple(row)
    changed_predictions = leave_one_out(changed)
    for model, points in predictions.items():
        assert np.asarray(points).shape == (17, 2)
        assert np.isfinite(points).all()
        assert points[held] == pytest.approx(changed_predictions[model][held])


def test_old_model_cross_validation_uses_only_remaining_bottles():
    import cv2
    from fit_ground import BOTTLES, SURVEY, leave_one_out

    rows = BOTTLES + SURVEY
    pixels = np.array([r[1:3] for r in rows], dtype=float) * 5 / 6
    ground = np.array([r[3:5] for r in rows], dtype=float)
    predictions = leave_one_out(rows)['old_8_bottle_homography']
    for held in (0, 8):
        train = [i for i in range(8) if i != held]
        matrix, _ = cv2.findHomography(pixels[train], ground[train], method=0)
        expected = cv2.perspectiveTransform(pixels[held:held+1, None], matrix)[0, 0]
        assert predictions[held] == pytest.approx(expected)
