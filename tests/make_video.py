from pathlib import Path
import subprocess

import numpy as np


def make_video(path: Path, moving: bool = True, sprite=None) -> None:
    """Twenty seconds at 10 fps; a grey blob or the given BGR sprite crosses left to far during seconds 8–15."""
    background = np.random.default_rng(0).integers(24, 40, (720, 1280, 3), dtype=np.uint8)
    with subprocess.Popen(
        ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", "1280x720", "-r", "10", "-i", "pipe:0", "-an", "-c:v", "libx264",
         "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-g", "10",
         "-bf", "0", "-movflags", "+faststart", str(path)],
        stdin=subprocess.PIPE,
    ) as encoder:
        for frame in range(200):
            image = background.copy()
            if moving and 80 <= frame < 150:
                progress = (frame - 80) / 69
                x, y = round(900 * progress), round(320 * (1 - progress))
                if sprite is None:
                    image[y:y + 80, x:x + 120] = 180
                else:
                    image[y:y + sprite.shape[0], x:x + sprite.shape[1]] = sprite
            encoder.stdin.write(image.tobytes())
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("ffmpeg could not generate the fixture")
