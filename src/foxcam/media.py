from pathlib import Path
import subprocess

import cv2

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
