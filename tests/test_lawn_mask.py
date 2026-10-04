"""Check the operator-supplied lawn, steps, patio and table mask."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from foxcam.ground import load_calibration


@pytest.mark.parametrize("point,inside", [
    ((86 * 5 / 6, 792 * 5 / 6), True),  # Near stepping stone.
    ((200, 700), True),                 # Near-left lawn beneath unlit stems.
    ((350, 850), True),
    ((500, 900), True),                 # Lawn immediately above the metal edging.
    ((40, 540), True),                  # Left grass edge beneath the bed.
    ((100, 300), False),                # Left bed/shrub.
    ((960, 200), True),                 # Table and chairs.
    ((620, 350), True),                 # Patio steps.
    ((1050, 280), True),                # Patio/table area at the door rail.
    ((750, 250), True),                 # Patio approach included by the operator.
    ((700, 320), True),                 # Patio by the steps.
    ((620, 390), True),                 # In front of the steps.
    ((820, 350), True),                 # Front of patio inside the supplied outline.
    ((1300, 300), False),               # Shrubs beside the patio.
    ((100, 900), True),                 # Near-left lawn down to the corner.
    ((0, 980), True),                   # Corner on the inclusive boundary.
    ((100, 975), False),                # Below the corner-to-edging segment.
    ((1850, 350), False),               # Right bed/shrub.
    ((1200, 1000), False),              # Foreground mulch.
    ((100, 1050), False),               # Near-left side of edging, in the bed.
])
def test_lawn_and_patio_mask_excludes_vegetation(point, inside):
    calibration = load_calibration(Path(__file__).parents[1] / "vps/ground-calibration.json")
    polygon = np.asarray(calibration["motion_polygon"], dtype=np.float32)
    assert (cv2.pointPolygonTest(polygon, point, False) >= 0) == inside
