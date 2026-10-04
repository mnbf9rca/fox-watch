"""The surveyed near-left stones and lawn must not be cut out as vegetation."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from foxcam.ground import load_calibration


@pytest.mark.parametrize("point,inside", [
    ((86 * 5 / 6, 792 * 5 / 6), True),  # Survey 8: near stepping stone.
    ((200, 700), True),                 # Near-left lawn behind foreground stems.
    ((350, 850), True),
    ((500, 900), True),                 # Lawn immediately above the metal edging.
    ((40, 540), True),                  # Left grass edge beneath the bed.
    ((100, 300), False),                # Left bed/shrub.
    ((960, 200), False),                # Patio.
    ((1850, 350), False),               # Right bed/shrub.
    ((1200, 1000), False),              # Foreground mulch.
    ((100, 1050), False),               # Near-left side of edging, in the bed.
])
def test_full_lawn_mask_includes_wedge_but_excludes_non_lawn(point, inside):
    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    polygon = np.asarray(calibration["motion_polygon"], dtype=np.float32)
    assert (cv2.pointPolygonTest(polygon, point, False) >= 0) == inside
