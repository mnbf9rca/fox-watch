"""Ground-plane estimates for the fixed, calibrated garden camera.

Bottom-centre boxes approximate ground contact, not an animal's true position.
The mapping is invalid for airborne birds and changes if the camera moves.
"""

import json
import math
from pathlib import Path

import numpy as np


# The patio wall is 9.5 m away; allow some fitting/box error beyond it.
MAX_FORWARD_M = 12


# Approximate 8 m square: centre line is 4 degrees right of the camera axis,
# ending 8.8 m from the camera. Exact lawn corners have not been surveyed.
PATCH_OUTLINE_M = tuple(
    (across * math.cos(math.radians(4)) + forward * math.sin(math.radians(4)),
     forward * math.cos(math.radians(4)) - across * math.sin(math.radians(4)))
    for across, forward in ((-4, .8), (-4, 8.8), (4, 8.8), (4, .8))
)


def load_calibration(path: str | Path | None) -> dict | None:
    """Load an explicitly enabled calibration; empty paths leave mapping off."""
    if not path:
        return None
    calibration = json.loads(Path(path).read_text())
    size = calibration["image_size"]
    if (not isinstance(size, list) or len(size) != 2
            or any(type(value) is not int or value <= 0 for value in size)):
        raise ValueError("invalid calibration image size")
    matrix = calibration.get("homography")
    if (not isinstance(matrix, list) or len(matrix) != 3
            or any(not isinstance(row, list) or len(row) != 3 for row in matrix)
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for row in matrix for value in row)):
        raise ValueError("invalid ground calibration")
    determinant = np.linalg.det(matrix)
    if not math.isfinite(determinant) or determinant == 0:
        raise ValueError("singular ground calibration")
    if "motion_polygon" in calibration:
        polygon = calibration["motion_polygon"]
        if (not isinstance(polygon, list) or len(polygon) < 3
                or any(not isinstance(point, list) or len(point) != 2
                       or any(type(value) not in (int, float) or not math.isfinite(value)
                              or not 0 <= value <= bound for value, bound in zip(point, size))
                       for point in polygon)):
            raise ValueError("invalid motion polygon")
        if sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1])) == 0:
            raise ValueError("zero-area motion polygon")
    return calibration


def ground_track(boxes: list[list], width: int, height: int,
                 calibration: dict | None) -> list[list]:
    """Return [frame, across metres, forward metres], nulling unsafe estimates.

    Resizing is valid only for the same full camera field of view. Values at
    the horizon, behind the camera or beyond 12 m forward are not usable here.
    """
    if width <= 0 or height <= 0:
        raise ValueError("invalid recording dimensions")
    points = []
    for frame, x, y, w, h in boxes:
        point = [frame, None, None]
        points.append(point)
        if calibration is None or not all(math.isfinite(value) for value in (x, y, w, h)):
            continue
        image_width, image_height = calibration["image_size"]
        contact = ((x + w / 2) * image_width / width,
                   (y + h) * image_height / height, 1)
        projected = [sum(value * coord for value, coord in zip(row, contact))
                     for row in calibration["homography"]]
        if not all(math.isfinite(value) for value in projected) or abs(projected[2]) < 1e-6:
            continue
        across, forward = (projected[0] / projected[2], projected[1] / projected[2])
        if math.isfinite(across) and math.isfinite(forward) and 0 <= forward <= MAX_FORWARD_M and math.hypot(across, forward) <= 100:
            point[1:] = [across, forward]
    return points
