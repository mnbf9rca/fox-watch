"""Cross-validate and refit the ground model from docs/calibration.md; no new dependencies."""
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


def fit_models(rows, held=None):
    """Refit each candidate, excluding held XY and elevation from all fits."""
    pixels = np.array([row[1:3] for row in rows], dtype=float) * (5 / 6)
    ground = np.array([row[3:5] for row in rows], dtype=float)
    train = np.arange(len(rows)) != held
    models = {}
    for name, subset in (("old_8_bottle_homography", train & (np.arange(len(rows)) < 8)),
                         ("homography_17_point", train)):
        matrix, _ = cv2.findHomography(pixels[subset], ground[subset], method=0)
        models[name] = {"homography": matrix.tolist()}
    heights = np.array([row[3:] for i, row in enumerate(rows) if len(row) == 6 and i != held])
    camera = dict(focal_length_px=1774 * 5 / 6, height_m=.327)
    plane = fit_plane(heights, camera["height_m"])
    angles = fit_rotation(pixels[train], ground[train], plane, camera, [1920, 1080])
    camera.update(zip(("pitch_deg", "roll_deg", "yaw_deg"), angles.tolist()))
    models["pinhole_plane"] = dict(camera=camera, ground_plane=plane.tolist())
    return models


def project_model(pixels, model):
    if "homography" in model:
        return cv2.perspectiveTransform(pixels[:, None], np.asarray(model["homography"]))[:, 0]
    return intersections(pixels, np.asarray(model["ground_plane"]), model["camera"], [1920, 1080])


def leave_one_out(rows):
    """Return held-out predictions without the runtime cap or discarded errors."""
    predictions = {}
    for held, row in enumerate(rows):
        pixel = np.asarray([row[1:3]], dtype=float) * (5 / 6)
        for name, model in fit_models(rows, held).items():
            predictions.setdefault(name, []).append(project_model(pixel, model)[0])
    return {name: np.asarray(points) for name, points in predictions.items()}


def main():
    target = Path(__file__).parents[1] / "vps/ground-calibration.json"
    previous = json.loads(target.read_text())
    rows = BOTTLES + SURVEY
    pixels = np.asarray([row[1:3] for row in rows], dtype=float) * (5 / 6)
    ground = np.asarray([row[3:5] for row in rows], dtype=float)
    models, held_predictions = fit_models(rows), leave_one_out(rows)
    scores = {}
    for name, predictions in held_predictions.items():
        errors = np.linalg.norm(predictions - ground, axis=1)
        scores[name] = dict(rms_radial_m=float(np.sqrt(np.mean(errors ** 2))),
                           max_radial_m=float(errors.max()), radial_errors_m=errors.tolist(),
                           predictions_m=predictions.tolist())
    chosen = min(scores, key=lambda name: scores[name]["rms_radial_m"])
    predicted = project_model(pixels, models[chosen])
    errors = predicted - ground
    radial = np.linalg.norm(errors, axis=1)
    # Keep only the winning model's runtime parameters: camera would override H.
    calibration = {key: value for key, value in previous.items()
                   if key in ("image_size", "measurement_image_size", "measurement_to_recording_scale",
                              "limitations", "patch_outline_m", "patch_outline_note",
                              "motion_polygon", "motion_polygon_note")}
    calibration.update(
        source="docs/calibration.md: eight bottles and nine confirmed laser points, 2026-10-04",
        model=chosen, **models[chosen],
        axes="Across right, forward from lens; metres. Lawn-ground estimates; patio approximate.",
        fit=dict(method="Lowest leave-one-out radial RMS across all 17 positions; winner refitted on its complete training set",
                 excluded_points=["Laser 5a: no marked pixel or bearing"],
                 rms_radial_m=float(np.sqrt(np.mean(radial ** 2))), max_radial_m=float(radial.max())),
        cross_validation=dict(
            method="17 held-out predictions; old homography uses only remaining bottles; other models exclude held XY; physical plane also excludes held survey elevation; no 12 m clipping during scoring",
            models=scores),
        points=[dict(name=row[0], image_measurement_px=list(row[1:3]), image_recording_px=pixel.tolist(),
                     measured_ground_m=measured.tolist(), fitted_ground_m=fitted.tolist(),
                     residual_m=error.tolist(), radial_error_m=float(distance))
                for row, pixel, measured, fitted, error, distance
                in zip(rows, pixels, ground, predicted, errors, radial)],
    )
    target.write_text(json.dumps(calibration, indent=2, allow_nan=False) + "\n")
    print("| Held-out point | Old 8-bottle H | 17-point H | Physical |")
    print("|---|---:|---:|---:|")
    for i, row in enumerate(rows):
        print("| " + row[0] + " | " + " | ".join(f"{score['radial_errors_m'][i]:.4f}" for score in scores.values()) + " |")
    for label, key in (("RMS", "rms_radial_m"), ("Maximum", "max_radial_m")):
        print("| " + label + " | " + " | ".join(f"{score[key]:.4f}" for score in scores.values()) + " |")
    print("Chosen:", chosen)
    print("All-point refit:", calibration["fit"])


if __name__ == "__main__":
    main()
