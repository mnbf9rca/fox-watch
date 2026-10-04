"""Refit the physical lawn model from docs/calibration.md; no new dependencies."""
import json
from pathlib import Path

import cv2
import numpy as np

from foxcam.ground import camera_rotation


# Full-sensor image coordinates and documented across/forward metres.
BOTTLES = [
    ("Bottle: tape 2 m", 881, 735, -.30, 1.98),
    ("Bottle: tape 4 m", 858, 582, -.65, 3.95),
    ("Bottle: cross point", 847, 593, -.71, 4.15),
    ("Bottle: middle right", 1874, 514, 1.84, 4.54),
    ("Bottle: left", 156, 582, -3.03, 5.41),
    ("Bottle: rear right", 1597, 439, 2.07, 8.24),
    ("Bottle: rear left", 723, 484, -2.13, 8.80),
    ("Bottle: back centre", 1281, 444, .64, 8.78),
]
# Final column is elevation relative to the lens; point 5a has no known position.
SURVEY = [
    ("Laser 8", 86, 792, -1.22, 2.04, -.380),
    ("Laser 7", 472, 671, -1.15, 2.99, -.370),
    ("Laser 6", 679, 601, -1.10, 4.12, -.340),
    ("Laser 4", 2050, 506, 1.92, 3.80, -.260),
    ("Laser 5", 863, 518, -1.08, 6.66, -.195),
    ("Laser 9", 161, 581, -3.30, 5.91, -.340),
    ("Laser 3", 1716, 443, 2.45, 7.71, -.100),
    ("Laser 1", 696, 460, -2.35, 9.15, -.100),
    ("Laser 2", 1290, 444, .74, 9.52, .002),
]


def fit_plane(survey, height_m):
    """World z=0 is ground directly below the lens; survey z is lens-relative."""
    design = np.column_stack([np.ones(len(survey)), survey[:, :2]])
    return np.linalg.lstsq(design, survey[:, 2] + height_m, rcond=None)[0]


def intersections(pixels, plane, camera, image_size):
    rays = np.column_stack([(pixels - np.asarray(image_size) / 2) / camera["focal_length_px"],
                            np.ones(len(pixels))]) @ camera_rotation(camera).T
    denominator = rays[:, 2] - rays[:, :2] @ plane[1:]
    if np.any(np.abs(denominator) < 1e-9):
        return np.full((len(pixels), 2), np.inf)
    distance = (plane[0] - camera["height_m"]) / denominator
    if np.any(distance <= 0):
        return np.full((len(pixels), 2), np.inf)
    return rays[:, :2] * distance[:, None]


def fit_rotation(pixels, ground, plane, camera, image_size):
    """Three-angle damped least squares, minimizing XY intersection errors (m).

    Intrinsics, camera position and the independently fitted plane stay fixed.
    Finite-difference Jacobian and a 3x3 solve use the existing NumPy dependency.
    """
    angles, damping = np.array([6., 0., 0.]), 1e-3
    def residual(values):
        pose = camera | dict(zip(("pitch_deg", "roll_deg", "yaw_deg"), values))
        return (intersections(pixels, plane, pose, image_size) - ground).ravel()
    for _ in range(100):
        error = residual(angles)
        jacobian = np.column_stack([(residual(angles + delta) - residual(angles - delta)) / 2e-5
                                    for delta in np.eye(3) * 1e-5])
        step = np.linalg.solve(jacobian.T @ jacobian + damping * np.eye(3), -jacobian.T @ error)
        candidate = residual(angles + step)
        if candidate @ candidate < error @ error:
            angles += step
            damping = max(damping / 3, 1e-12)
            if np.linalg.norm(step) < 1e-9:
                break
        else:
            damping *= 10
    if not np.all(np.isfinite(residual(angles))):
        raise ValueError("rotation fit has invalid intersections")
    return angles


def main():
    target = Path(__file__).parents[1] / "vps/ground-calibration.json"
    calibration = json.loads(target.read_text())
    rows = BOTTLES + SURVEY
    pixels = np.array([row[1:3] for row in rows], dtype=float) * (5 / 6)
    ground = np.array([row[3:5] for row in rows], dtype=float)
    heights = np.array([row[3:] for row in SURVEY], dtype=float)
    camera = dict(focal_length_px=1774 * 5 / 6, height_m=.327)
    plane = fit_plane(heights, camera["height_m"])
    angles = fit_rotation(pixels, ground, plane, camera, [1920, 1080])
    camera.update(zip(("pitch_deg", "roll_deg", "yaw_deg"), angles.tolist()))
    predicted = intersections(pixels, plane, camera, [1920, 1080])
    # Compare against the original eight-bottle homography, not a refitted baseline.
    old_matrix, _ = cv2.findHomography(pixels[:8], ground[:8], method=0)
    old = cv2.perspectiveTransform(pixels.reshape(-1, 1, 2), old_matrix).reshape(-1, 2)
    errors, old_errors = predicted - ground, old - ground
    radial, old_radial = np.linalg.norm(errors, axis=1), np.linalg.norm(old_errors, axis=1)
    plane_errors = plane[0] + heights[:, :2] @ plane[1:] - (heights[:, 2] + camera["height_m"])
    calibration.pop("homography", None)
    calibration.update(
        source="docs/calibration.md: eight bottle positions and nine confirmed laser points, 2026-10-04",
        model="pinhole_plane", camera=camera, ground_plane=plane.tolist(),
        axes="World (across, forward, up), metres; z=0 is ground directly below lens at (0,0,0.327)",
        rotation_convention="Positive pitch down, yaw right, roll right-axis down; principal point at image centre",
        fit=dict(method="OLS plane on nine laser elevations; fixed-intrinsics rotation minimizes summed XY ray-plane intersection errors for all 17 confirmed positions",
                 excluded_points=["Laser 5a: no marked pixel or bearing"],
                 plane_rms_vertical_m=float(np.sqrt(np.mean(plane_errors ** 2))),
                 rms_radial_m=float(np.sqrt(np.mean(radial ** 2))), max_radial_m=float(radial.max()),
                 old_homography_rms_radial_m=float(np.sqrt(np.mean(old_radial ** 2))),
                 old_homography_max_radial_m=float(old_radial.max())),
        points=[dict(name=row[0], image_measurement_px=list(row[1:3]), image_recording_px=pixel.tolist(),
                     measured_ground_m=measured.tolist(), fitted_ground_m=fitted.tolist(),
                     residual_m=error.tolist(), radial_error_m=float(distance),
                     old_homography_residual_m=old_error.tolist(), old_homography_radial_error_m=float(old_distance))
                for row, pixel, measured, fitted, error, distance, old_error, old_distance
                in zip(rows, pixels, ground, predicted, errors, radial, old_errors, old_radial)],
        survey_elevations=[dict(name=row[0], measured_relative_lens_m=row[5], residual_m=float(error))
                           for row, error in zip(SURVEY, plane_errors)],
    )
    target.write_text(json.dumps(calibration, indent=2, allow_nan=False) + "\n")
    print("Camera:", camera)
    print("Plane z = a + b*across + c*forward (world metres):", plane.tolist())
    print("| Point | Physical radial m | Old homography radial m |")
    print("|---|---:|---:|")
    for row in calibration["points"]:
        print(f"| {row['name']} | {row['radial_error_m']:.4f} | {row['old_homography_radial_error_m']:.4f} |")
    print("Fit:", calibration["fit"])
    print("Survey elevation residuals m:", plane_errors.tolist())


if __name__ == "__main__":
    main()
