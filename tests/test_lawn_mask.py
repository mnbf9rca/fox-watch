"""Include patio routes while excluding foreground plant silhouettes."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from foxcam.ground import load_calibration


@pytest.mark.parametrize("point,inside", [
    ((86 * 5 / 6, 792 * 5 / 6), False), # Survey 8: foreground leaf overlaps this stone.
    ((200, 700), False),                 # Foreground stems silhouetted over lawn.
    ((350, 850), False),
    ((500, 900), True),                 # Lawn immediately above the metal edging.
    ((40, 540), True),                  # Left grass edge beneath the bed.
    ((100, 300), False),                # Left bed/shrub.
    ((960, 200), True),                 # Table rectangle retained by operator.
    ((620, 350), True),                 # Patio steps.
    ((1050, 280), True),                # Door glazing accepted by operator.
    ((750, 250), True),                 # New direct edge from former vertex 7 to 11.
    ((700, 320), True),                 # Patio area by the steps, away from glass.
    ((620, 390), True),                 # In front of the steps.
    ((820, 350), False),                # Shrub in front of patio.
    ((1850, 350), False),               # Right bed/shrub.
    ((1200, 1000), False),              # Foreground mulch.
    ((100, 1050), False),               # Near-left side of edging, in the bed.
])
def test_lawn_and_patio_mask_excludes_vegetation(point, inside):
    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    polygon = np.asarray(calibration["motion_polygon"], dtype=np.float32)
    assert (cv2.pointPolygonTest(polygon, point, False) >= 0) == inside
