"""Render the exact configured motion polygon over both calibration stills."""
import json
from pathlib import Path

import cv2
import numpy as np


root = Path(__file__).resolve().parents[1]
calibration = json.loads((root / "vps/ground-calibration.json").read_text())
for source, target in (("lawn-still-2304.jpg", "08-motion-mask-day.jpg"),
                       ("lawn-night-flood-2304.jpg", "09-motion-mask-night.jpg")):
    image = cv2.imread(str(root / ".research" / source))
    if image is None:
        raise FileNotFoundError(source)
    height, width = image.shape[:2]
    polygon = np.rint(np.asarray(calibration["motion_polygon"]) *
                      (np.array([width, height]) / calibration["image_size"])).astype(np.int32)
    tint = image.copy()
    cv2.fillPoly(tint, [polygon], (255, 255, 0))
    image = cv2.addWeighted(image, .85, tint, .15, 0)
    cv2.polylines(image, [polygon], True, (255, 0, 255), 4, cv2.LINE_AA)
    for index, (x, y) in enumerate(polygon, 1):
        cv2.circle(image, (x, y), 6, (255, 0, 255), -1)
        position = (max(8, min(int(x) + 10, width - 55)), max(30, int(y) - 10))
        for color, thickness in (((0, 0, 0), 5), ((255, 255, 255), 2)):
            cv2.putText(image, str(index), position, cv2.FONT_HERSHEY_SIMPLEX, .8, color, thickness, cv2.LINE_AA)
    cv2.rectangle(image, (10, 10), (1090, 68), (0, 0, 0), -1)
    cv2.putText(image, "Unknown motion mask: bottom-centre inside cyan lawn; detector tracks unrestricted",
                (22, 48), cv2.FONT_HERSHEY_SIMPLEX, .7, (255, 255, 255), 2, cv2.LINE_AA)
    destination = root / "docs/calibration" / target
    if not cv2.imwrite(str(destination), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)
    print(f"PASS: {destination.relative_to(root)} ({width}x{height})")
