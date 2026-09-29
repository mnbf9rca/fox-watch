"""COCO object detection with YOLOX-S from the OpenCV model zoo, run through cv2.dnn."""
from hashlib import sha256
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
VEHICLES = {"bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat"}
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
            temporary.replace(path)
        if sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
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
    kept = cv2.dnn.NMSBoxes(boxes.tolist(), confidences[keep].tolist(), CONFIDENCE, 0.5)
    return [(CLASSES[classes[keep][i]], float(confidences[keep][i]), *map(int, boxes[i]))
            for i in np.asarray(kept).flatten()]


def iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    overlap = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return overlap / (aw * ah + bw * bh - overlap) if overlap else 0.0


def link(detections: list[tuple[int, list]], max_misses: int = 10) -> list[dict]:
    """Greedy same-class IoU linking; a track ends after max_misses consecutive processed frames."""
    # ponytail: IoU only; fast small animals may split into several tracks. Centroid distance or Kalman if so.
    tracks, live = [], []
    for frame, found in detections:
        matched = set()
        for name, _, *box in sorted(found, key=lambda d: -d[1]):
            best, best_iou = None, 0.1
            for track in live:
                if track["class"] == name and id(track) not in matched:
                    score = iou(track["boxes"][-1][1:], box)
                    if score > best_iou:
                        best, best_iou = track, score
            if best is None:
                best = {"id": len(tracks), "class": name, "boxes": [], "misses": 0}
                tracks.append(best)
                live.append(best)
            matched.add(id(best))
            best["boxes"].append([frame, *box])
            best["misses"] = 0
        for track in live:
            if id(track) not in matched:
                track["misses"] += 1
        live = [track for track in live if track["misses"] < max_misses]
    for track in tracks:
        del track["misses"]
    return tracks


if __name__ == "__main__":
    load()
    if len(sys.argv) > 1:
        print(detect(cv2.imread(sys.argv[1])))
