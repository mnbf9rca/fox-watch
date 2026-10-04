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
    if "camera" in calibration:
        camera, plane = calibration["camera"], calibration.get("ground_plane")
        if (not isinstance(camera, dict)
                or any(type(camera.get(key)) not in (int, float) or not math.isfinite(camera[key])
                       for key in ("focal_length_px", "height_m", "pitch_deg", "roll_deg", "yaw_deg"))
                or camera["focal_length_px"] <= 0 or camera["height_m"] <= 0
                or not isinstance(plane, list) or len(plane) != 3
                or any(type(value) not in (int, float) or not math.isfinite(value) for value in plane)):
            raise ValueError("invalid physical ground calibration")
    else:  # Older calibration files and synthetic fixtures remain readable.
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


def camera_rotation(camera: dict) -> np.ndarray:
    """Camera (right, down, optical forward) to world (across, forward, up).

    Positive pitch looks down, yaw looks right, roll rotates the camera's
    right axis down. R = yaw(-yaw) @ pitch(-pitch) @ level @ optical_roll.
    """
    pitch, roll, yaw = [math.radians(camera[key]) for key in ("pitch_deg", "roll_deg", "yaw_deg")]
    cp, sp, cr, sr, cy, sy = math.cos(pitch), math.sin(pitch), math.cos(roll), math.sin(roll), math.cos(yaw), math.sin(yaw)
    return (np.array([[cy, sy, 0], [-sy, cy, 0], [0, 0, 1]])
            @ np.array([[1, 0, 0], [0, cp, sp], [0, -sp, cp]])
            @ np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]])
            @ np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]]))


def ground_track(boxes: list[list], width: int, height: int,
                 calibration: dict | None) -> list[list]:
    """Return [frame, across metres, forward metres], nulling unsafe estimates.

    Resizing is valid only for the same full camera field of view. Values at
    the horizon, behind the camera or beyond 12 m forward are not usable here.
    """
    if width <= 0 or height <= 0:
        raise ValueError("invalid recording dimensions")
    camera = calibration.get("camera") if calibration else None
    rotation = camera_rotation(camera) if camera else None
    points = []
    for frame, x, y, w, h in boxes:
        point = [frame, None, None]
        points.append(point)
        if calibration is None or not all(math.isfinite(value) for value in (x, y, w, h)):
            continue
        image_width, image_height = calibration["image_size"]
        contact = ((x + w / 2) * image_width / width,
                   (y + h) * image_height / height, 1)
        if camera:
            focal = camera["focal_length_px"]
            dx, dy, dz = rotation @ [(contact[0] - image_width / 2) / focal,
                                     (contact[1] - image_height / 2) / focal, 1]
            a, b, c = calibration["ground_plane"]
            denominator = dz - b * dx - c * dy
            if not math.isfinite(denominator) or abs(denominator) < 1e-9:
                continue
            distance = (a - camera["height_m"]) / denominator
            if distance <= 0:  # Intersection lies behind the lens.
                continue
            across, forward = float(distance * dx), float(distance * dy)
        else:
            projected = [sum(value * coord for value, coord in zip(row, contact))
                         for row in calibration["homography"]]
            if not all(math.isfinite(value) for value in projected) or abs(projected[2]) < 1e-6:
                continue
            across, forward = (projected[0] / projected[2], projected[1] / projected[2])
        if math.isfinite(across) and math.isfinite(forward) and 0 <= forward <= MAX_FORWARD_M and math.hypot(across, forward) <= 100:
            point[1:] = [across, forward]
    return points
