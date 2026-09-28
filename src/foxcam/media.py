from pathlib import Path
import subprocess

import cv2
import numpy as np

from foxcam.edges import nearest_edge
from foxcam.events import merge_events


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
            small = cv2.resize(image, (320, round(image.shape[0] * 320 / image.shape[1])))
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


def cut(
    source: Path, start: float, end: float, target: Path, pad_seconds: float = 2
) -> float:
    """Copy a padded interval; stream-copy boundaries round to source keyframes."""
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(target if target.exists() else source)],
        text=True,
    ))
    if target.exists():
        return duration
    if not 0 <= start < end or pad_seconds < 0:
        raise ValueError("Invalid event interval or padding")
    seek = max(0, start - pad_seconds)
    stop = min(duration, end + pad_seconds)
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
    duration = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(temporary)], text=True,
    ))
    temporary.replace(target)
    return duration


def track(clip: Path, min_blob_area: float, edge_margin: float) -> dict:
    video = cv2.VideoCapture(str(clip))
    try:
        ok, image = video.read()
        if not ok:
            raise ValueError(f"Cannot decode video: {clip}")
        height, width = image.shape[:2]
        subtractor = cv2.createBackgroundSubtractorMOG2(detectShadows=False)
        boxes = []
        largest_area = 0
        largest_frame = 0
        frame = 0
        while ok:
            mask = subtractor.apply(image)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contour = max(contours, key=cv2.contourArea, default=None)
            area = cv2.contourArea(contour) if contour is not None else 0
            if frame and area > min_blob_area * (width / 320) ** 2:
                boxes.append([frame, *cv2.boundingRect(contour)])
                if area > largest_area:
                    largest_area, largest_frame = area, frame
            frame += 1
            ok, image = video.read()
        if boxes:
            selected = [boxes[0][0], boxes[len(boxes) // 2][0], boxes[-1][0], largest_frame]
            edges = [nearest_edge(x + w / 2, y + h / 2, width, height, edge_margin)
                     for _, x, y, w, h in (boxes[0], boxes[-1])]
        else:
            selected = [0, frame // 2, frame - 1, 0]
            edges = ["unknown", "unknown"]
        frames = []
        for index, position in enumerate(selected):
            target = clip.with_name(f"{clip.stem}.f{index}.jpg")
            frames.append(target.name)
            if target.exists():
                continue
            video.set(cv2.CAP_PROP_POS_FRAMES, position)
            ok, image = video.read()
            if not ok:
                raise ValueError(f"Cannot decode frame {position}: {clip}")
            temporary = target.with_name(f".{target.stem}.tmp.jpg")
            if not cv2.imwrite(str(temporary), image):
                raise OSError(f"Cannot write frame: {temporary}")
            temporary.replace(target)
        return {"track": boxes, "entry_edge": edges[0], "exit_edge": edges[1], "frames": frames}
    finally:
        video.release()


def annotate(
    clip: Path, target: Path, boxes: list[list[int]], label: str, confidence: float
) -> None:
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
        by_frame = {frame: (x, y, w, h) for frame, x, y, w, h in boxes}
        points = []
        frame = 0
        with subprocess.Popen(
            ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
             "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-an",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)],
            stdin=subprocess.PIPE,
        ) as encoder:
            while ok:
                if frame in by_frame:
                    x, y, w, h = by_frame[frame]
                    cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    points.append((x + w // 2, y + h // 2))
                # ponytail: redraw short clip paths; cache an overlay if long clips become costly.
                if len(points) > 1:
                    cv2.polylines(image, [np.asarray(points, dtype=np.int32)], False, (0, 255, 255), 2)
                cv2.rectangle(image, (0, 0), (280, 44), (0, 0, 0), -1)
                cv2.putText(image, f"{label} {confidence:.0%}", (12, 32),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
                encoder.stdin.write(image.tobytes())
                frame += 1
                ok, image = video.read()
            encoder.stdin.close()
            if encoder.wait() != 0:
                raise RuntimeError(f"ffmpeg could not annotate: {clip}")
        temporary.replace(target)
    finally:
        video.release()
