"""Refit docs/calibration.md's eight pairs: python tests/fit_ground.py."""

import json
from pathlib import Path

import cv2
import numpy as np

from foxcam.ground import PATCH_OUTLINE_M


def main():
    names = ["Tape at 2 m", "Tape at 4 m", "Cross point", "Middle right", "Left",
             "Rear right", "Rear left", "Back of grass, centre line"]
    image = np.array([[881, 735], [858, 582], [847, 593], [1874, 514], [156, 582],
                      [1597, 439], [723, 484], [1281, 444]], dtype=float)
    recording = image * (5 / 6)
    ground = np.array([[-.30, 1.98], [-.65, 3.95], [-.71, 4.15], [1.84, 4.54],
                       [-3.03, 5.41], [2.07, 8.24], [-2.13, 8.80], [.64, 8.78]])
    matrix, _ = cv2.findHomography(recording, ground, method=0)
    estimated = cv2.perspectiveTransform(recording.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    residual = estimated - ground
    radial = np.linalg.norm(residual, axis=1)
    calibration = {
        "source": "docs/calibration.md, 2026-10-04 Camera Module 3 NoIR; fixed garden view",
        "image_size": [1920, 1080], "measurement_image_size": [2304, 1296],
        "measurement_to_recording_scale": [5, 6],
        "axes": "Camera (0,0); across positive right, forward along camera axis, metres",
        "limitations": "Ground-plane estimate, invalid for airborne birds; repeat if camera moves",
        "homography": matrix.tolist(),
        "fit": {"method": "OpenCV findHomography method=0, least squares using all eight pairs",
                "rms_radial_m": float(np.sqrt(np.mean(radial ** 2))),
                "max_radial_m": float(radial.max())},
        "patch_outline_m": PATCH_OUTLINE_M,
        "patch_outline_note": "Approximate 8 m square, centre line 4 degrees right, far edge at 8.8 m; corners not surveyed",
        "points": [dict(name=name, image_measurement_px=original.tolist(),
                        image_recording_px=scaled.tolist(), measured_ground_m=measured.tolist(),
                        fitted_ground_m=fitted.tolist(), residual_m=error.tolist(), radial_error_m=float(distance))
                   for name, original, scaled, measured, fitted, error, distance
                   in zip(names, image, recording, ground, estimated, residual, radial)],
    }
    target = Path(__file__).parents[1] / "vps/ground-calibration.json"
    if target.exists():
        calibration = json.loads(target.read_text()) | calibration
    target.write_text(json.dumps(calibration, indent=2, allow_nan=False) + "\n")
    print(f"Fit all 8 pairs: RMS {calibration['fit']['rms_radial_m']:.9f} m; max {radial.max():.9f} m")


if __name__ == "__main__":
    main()
