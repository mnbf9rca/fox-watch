"""COCO object detection with YOLOX-S from the OpenCV model zoo, run through cv2.dnn."""
from hashlib import sha256
from math import hypot
import os
from pathlib import Path
import sys
from urllib import request

import cv2
import numpy as np


MODEL_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
             "object_detection_yolox/object_detection_yolox_2022nov.onnx")
MODEL_SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
CLASSES = (
    "person bicycle car motorcycle airplane bus train truck boat traffic_light fire_hydrant stop_sign "
    "parking_meter bench bird cat dog horse sheep cow elephant bear zebra giraffe backpack umbrella handbag "
    "tie suitcase frisbee skis snowboard sports_ball kite baseball_bat baseball_glove skateboard surfboard "
    "tennis_racket bottle wine_glass cup fork knife spoon bowl banana apple sandwich orange broccoli carrot "
    "hot_dog pizza donut cake chair couch potted_plant bed dining_table toilet tv laptop mouse remote keyboard "
    "cell_phone microwave oven toaster sink refrigerator book clock vase scissors teddy_bear hair_drier toothbrush"
).split()
VEHICLES = {"bicycle", "car", "motorcycle", "bus", "truck"}
TRACK_CLASSES = {name: name for name in ("person", "dog", "cat", "bird", "horse", "sheep", "cow", "bear")}
TRACK_CLASSES.update(dict.fromkeys(VEHICLES, "vehicle"))
SIZE = 640
CONFIDENCE = float(os.environ.get("DETECT_CONFIDENCE", 0.5))
_net = None
_grids = np.concatenate([np.stack(np.meshgrid(np.arange(SIZE // s), np.arange(SIZE // s)), 2).reshape(-1, 2)
                         for s in (8, 16, 32)])
_strides = np.concatenate([np.full(((SIZE // s) ** 2, 1), s) for s in (8, 16, 32)])


def model_path() -> Path:
    return Path(os.environ.get("MODEL_DIR", "/opt/foxcam/models")) / "yolox.onnx"


def load() -> cv2.dnn.Net:
    global _net
    if _net is None:
        path = model_path()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(".yolox.tmp")
            request.urlretrieve(MODEL_URL, temporary)
            if sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
                temporary.unlink()
                raise ValueError(f"Model checksum mismatch: {temporary}")
            temporary.replace(path)
        elif sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError(f"Model checksum mismatch: {path}")
        _net = cv2.dnn.readNet(str(path))
    return _net


def detect(frame: np.ndarray) -> list[tuple[str, float, int, int, int, int]]:
    """Boxes as (class, confidence, x, y, w, h) in frame pixels."""
    height, width = frame.shape[:2]
    ratio = min(SIZE / height, SIZE / width)
    canvas = np.full((SIZE, SIZE, 3), 114, np.uint8)
    resized = cv2.resize(frame, (round(width * ratio), round(height * ratio)))
    canvas[:resized.shape[0], :resized.shape[1]] = resized[:, :, ::-1]
    net = load()
    net.setInput(cv2.dnn.blobFromImage(canvas))
    raw = net.forward()[0]
    xy = (raw[:, :2] + _grids) * _strides
    wh = np.exp(raw[:, 2:4]) * _strides
    scores = raw[:, 4:5] * raw[:, 5:]
    classes, confidences = scores.argmax(1), scores.max(1)
    keep = confidences >= CONFIDENCE
    boxes = (np.hstack([xy - wh / 2, wh])[keep] / ratio).round().astype(int)
    kept = cv2.dnn.NMSBoxesBatched(boxes.tolist(), confidences[keep].tolist(),
                                   classes[keep].tolist(), CONFIDENCE, 0.5)
    return [(TRACK_CLASSES[CLASSES[classes[keep][i]]], float(confidences[keep][i]), *map(int, boxes[i]))
            for i in np.asarray(kept).flatten() if CLASSES[classes[keep][i]] in TRACK_CLASSES]


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return overlap / (aw * ah + bw * bh - overlap) if overlap else 0.0


def link(detections: list[tuple[int, list]], max_misses: int = 10) -> list[dict]:
    """Link by same-class IoU, then distance; expire after max_misses processed frames."""
    tracks, live = [], []
    for frame, found in detections:
        found = sorted(found, key=lambda d: -d[1])
        matched, assignments = set(), {}
        # Finish every IoU match before distance can consume a track.
        for index, (name, _, *box) in enumerate(found):
            best, best_iou = None, 0.0
            for track in live:
                if track["class"] == name and track["id"] not in matched:
                    score = iou(track["boxes"][-1][1:], box)
                    if score >= 0.05 and score > best_iou:
                        best, best_iou = track, score
            if best is not None:
                assignments[index] = best
                matched.add(best["id"])
        # Calibration: a 12 cm bird at 5 m is ~35 px; 1 m travel is ~296 px.
        # 9 box lengths admits that jump (8.33 lengths), with rounding margin.
        # ponytail: nearest centroid can swap nearby same-class movers; add
        # velocity prediction only if field footage demonstrates that ambiguity.
        for index, (name, _, x, y, w, h) in enumerate(found):
            if index in assignments:
                continue
            best, best_distance = None, float("inf")
            for track in live:
                if track["class"] != name or track["id"] in matched:
                    continue
                px, py, pw, ph = track["boxes"][-1][1:]
                size = min(max(w, h), max(pw, ph))
                distance = hypot(x + w / 2 - px - pw / 2, y + h / 2 - py - ph / 2)
                if size > 0 and distance <= 9 * size and distance < best_distance:
                    best, best_distance = track, distance
            if best is not None:
                assignments[index] = best
                matched.add(best["id"])
        # Add newborns only after both passes, so this frame cannot rematch them.
        for index, (_, _, *box) in enumerate(found):
            best = assignments.get(index)
            if best is None:
                best = {"id": len(tracks), "class": found[index][0], "boxes": [], "misses": 0}
                tracks.append(best)
                live.append(best)
                matched.add(best["id"])
            best["boxes"].append([frame, *box])
            best["misses"] = 0
        for track in live:
            if track["id"] not in matched:
                track["misses"] += 1
        live = [track for track in live if track["misses"] < max_misses]
    for track in tracks:
        del track["misses"]
    return tracks


if __name__ == "__main__":
    load()
    if len(sys.argv) > 1:
        print(detect(cv2.imread(sys.argv[1])))
