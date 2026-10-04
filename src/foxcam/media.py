from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import subprocess

import cv2
import numpy as np

from foxcam.detect import MAX_MISSES, detect, iou, link
from foxcam.edges import nearest_edge
from foxcam.events import merge_events
from foxcam.ground import ground_track


SCAN_WIDTH = 640
DETECT_INTERVAL = 2


def scan(
    source: Path, min_blob_area: float, gap_seconds: float = 3
) -> list[tuple[Path, float, float]]:
    video = cv2.VideoCapture(str(source))
    try:
        ok, image = video.read()
        if not ok:
            raise ValueError(f"Cannot decode video: {source}")
        fps = video.get(cv2.CAP_PROP_FPS)
        subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        times = []
        frame = 0
        while ok:
            small = cv2.resize(image, (SCAN_WIDTH, round(image.shape[0] * SCAN_WIDTH / image.shape[1])))
            mask = subtractor.apply(small)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            area = max((cv2.contourArea(c) for c in contours), default=0)
            if frame and area > min_blob_area:
                times.append(frame / fps)
            frame += 1
            ok, image = video.read()
        return [(source, start, end) for start, end in merge_events(times, fps, gap_seconds)]
    finally:
        video.release()


def duration(path: Path) -> float:
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)], text=True))


def cut(
    source: Path, start: float, end: float, target: Path, pad_seconds: float = 2
) -> float:
    """Copy a padded interval; stream-copy boundaries round to source keyframes."""
    if target.exists():
        return duration(target)
    length = duration(source)
    if not 0 <= start < end or pad_seconds < 0:
        raise ValueError("Invalid event interval or padding")
    seek = max(0, start - pad_seconds)
    stop = min(length, end + pad_seconds)
    if stop <= seek:
        raise ValueError("Event is outside the source video")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.stem}.tmp.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(seek), "-i", str(source),
         "-t", str(stop - seek), "-c", "copy", "-movflags", "+faststart", str(temporary)],
        check=True,
    )
    video = cv2.VideoCapture(str(temporary))
    try:
        if not video.read()[0]:
            raise ValueError(f"Cannot decode cut: {temporary}")
    finally:
        video.release()
    length = duration(temporary)
    temporary.replace(target)
    return length


def _write(target: Path, image) -> None:
    if target.exists():
        return
    temporary = target.with_name(f".{target.stem}.tmp.jpg")
    if not cv2.imwrite(str(temporary), image):
        raise OSError(f"Cannot write frame: {temporary}")
    temporary.replace(target)


def _frame(video, position: int, clip: Path):
    video.set(cv2.CAP_PROP_POS_FRAMES, position)
    ok, image = video.read()
    if not ok:
        raise ValueError(f"Cannot decode frame {position}: {clip}")
    return image


def _blob_boxes(image, subtractor, min_blob_area: float) -> list[tuple]:
    """All sizeable motion components, measured at the same scale as screening."""
    height, width = image.shape[:2]
    small = cv2.resize(image, (SCAN_WIDTH, round(height * SCAN_WIDTH / width)))
    mask = subtractor.apply(small)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    scale = width / SCAN_WIDTH
    return [("unknown", 1.0, *[round(value * scale) for value in cv2.boundingRect(contour)])
            for contour in contours if cv2.contourArea(contour) > min_blob_area]


def _unmatched_motion(motion: list[tuple[int, list]], tracks: list[dict]) -> list[tuple[int, list]]:
    # Hold the first box back over the detector miss window, interpolate
    # sampling gaps, then hold the last box for its unsampled frame.
    # Static detector tracks still explain motion.
    covered = {}
    for item in tracks:
        boxes = item["boxes"]
        for frame in range(max(0, boxes[0][0] - MAX_MISSES * DETECT_INTERVAL), boxes[0][0]):
            covered.setdefault(frame, []).append(boxes[0][1:])
        for first, last in zip(boxes, boxes[1:] + [[boxes[-1][0] + DETECT_INTERVAL, *boxes[-1][1:]]]):
            for frame in range(first[0], last[0]):
                fraction = (frame - first[0]) / (last[0] - first[0])
                box = [a + fraction * (b - a) for a, b in zip(first[1:], last[1:])]
                covered.setdefault(frame, []).append(box)
    return [(frame, [blob for blob in found
                     if not any(iou(blob[2:], box) > 0 for box in covered.get(frame, []))])
            for frame, found in motion]


def _moved(boxes: list[list[int]], ratio: float) -> bool:
    if not boxes:
        return False
    xs, ys = zip(*[(x + w / 2, y + h / 2) for _, x, y, w, h in boxes])
    mean_size = sum(max(w, h) for _, x, y, w, h in boxes) / len(boxes)
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys)) >= max(20, ratio * mean_size)


def track(clip: Path, min_blob_area: float, edge_margin: float, min_track_move_ratio: float = 0.75,
          ground_calibration: dict | None = None) -> dict:
    video = cv2.VideoCapture(str(clip))
    try:
        ok, image = video.read()
        if not ok:
            raise ValueError(f"Cannot decode video: {clip}")
        height, width = image.shape[:2]
        detections, motion, frame = [], [], 0
        subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        while ok:
            blobs = _blob_boxes(image, subtractor, min_blob_area)
            if frame:
                motion.append((frame, blobs))
            if frame % DETECT_INTERVAL == 0:
                detections.append((frame, detect(image)))
            frame += 1
            ok, image = video.read()
        tracks = link(detections, frame_width=width)
        unknown = link(_unmatched_motion(motion, tracks), frame_width=width)
        for item in unknown:
            item["id"] += len(tracks)
        tracks.extend(unknown)
        tracks = [item for item in tracks if _moved(item["boxes"], min_track_move_ratio)]
        for item in tracks:
            item["ground_track"] = ground_track(item["boxes"], width, height, ground_calibration)
            item["labels"], item["description"] = {}, ""
            item["entry_edge"], item["exit_edge"] = [
                nearest_edge(x + w / 2, y + h / 2, width, height, edge_margin)
                for _, x, y, w, h in (item["boxes"][0], item["boxes"][-1])]
            position, x, y, w, h = max(item["boxes"], key=lambda box: box[3] * box[4])
            item["largest"] = position
            drawn, crop = (clip.with_name(f"{clip.stem}.t{item['id']}{suffix}.jpg") for suffix in ("", ".crop"))
            if not drawn.exists() or not crop.exists():
                image = _frame(video, position, clip)
                _write(crop, image[max(0, y):y + h, max(0, x):x + w])
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                _write(drawn, image)
        primary = max(tracks, key=lambda item: len(item["boxes"]), default=None)
        if primary:
            boxes = primary["boxes"]
            selected = [boxes[0][0], boxes[len(boxes) // 2][0], boxes[-1][0], primary["largest"]]
            edges = [primary["entry_edge"], primary["exit_edge"]]
        else:
            boxes, selected, edges = [], [0, frame // 2, frame - 1, 0], ["unknown", "unknown"]
        for item in tracks:
            del item["largest"]
        frames = []
        for index, position in enumerate(selected):
            target = clip.with_name(f"{clip.stem}.f{index}.jpg")
            frames.append(target.name)
            if not target.exists():
                _write(target, _frame(video, position, clip))
        return {"tracks": tracks, "track": boxes, "entry_edge": edges[0], "exit_edge": edges[1], "frames": frames}
    finally:
        video.release()


TRACK_COLOURS = ((0, 255, 0), (255, 128, 0), (0, 128, 255), (255, 0, 255), (0, 255, 255))


def _timestamp(start_utc: datetime, frame: int, fps: float) -> str:
    if start_utc.utcoffset() is None:
        raise ValueError("start_utc must be an aware datetime")
    return (start_utc.astimezone(timezone.utc) + timedelta(seconds=frame / fps)).strftime("%Y-%m-%d %H:%M:%S UTC")


def annotate(clip: Path, target: Path, tracks: list[dict], captions: list[str], start_utc: datetime) -> None:
    if target.exists():
        return
    video = cv2.VideoCapture(str(clip))
    try:
        ok, image = video.read()
        if not ok:
            raise ValueError(f"Cannot decode video: {clip}")
        height, width = image.shape[:2]
        fps = video.get(cv2.CAP_PROP_FPS)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.stem}.tmp.mp4")
        by_frame = [{frame: (x, y, w, h) for frame, x, y, w, h in item["boxes"]} for item in tracks]
        points = [[] for _ in tracks]
        held = [None for _ in tracks]
        last = [max(boxes, default=-1) for boxes in by_frame]
        frame = 0
        with subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-an",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
            stdin=subprocess.PIPE,
        ) as encoder:
            while ok:
                for i, boxes in enumerate(by_frame):
                    colour = TRACK_COLOURS[tracks[i]["id"] % len(TRACK_COLOURS)]
                    if frame in boxes:
                        held[i] = boxes[frame]
                        x, y, w, h = held[i]
                        points[i].append((x + w / 2, y + h))
                    if held[i] is not None and frame <= last[i]:
                        x, y, w, h = held[i]
                        cv2.rectangle(image, (x, y), (x + w, y + h), colour, 2)
                        origin = (max(0, min(x, width - 200)), max(24, min(y - 8, height - 8)))
                        for ink, thickness in (((0, 0, 0), 4), (colour, 2)):
                            cv2.putText(image, captions[i], origin, cv2.FONT_HERSHEY_SIMPLEX,
                                        0.7, ink, thickness, cv2.LINE_AA)
                    # ponytail: redraw short clip paths; cache an overlay if long clips become costly.
                    if len(points[i]) > 1:
                        cv2.polylines(image, [np.asarray(points[i], dtype=np.int32)], False, colour, 2)
                for ink, thickness in (((0, 0, 0), 4), ((255, 255, 255), 2)):
                    cv2.putText(image, _timestamp(start_utc, frame, fps), (12, height - 12),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, ink, thickness, cv2.LINE_AA)
                encoder.stdin.write(image.tobytes())
                frame += 1
                ok, image = video.read()
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError(f"ffmpeg could not annotate: {clip}")
        temporary.replace(target)
    finally:
        video.release()
