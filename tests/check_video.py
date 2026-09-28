"""Exercise real video tools; pass a directory to retain the generated media."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from make_video import make_video
from foxcam.media import cut, scan


def check_video(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / "moving.mp4"
    blank = directory / "blank.mp4"
    target = directory / "cut.mp4"
    truncated = directory / "truncated.mp4"
    make_video(source)
    events = scan(source, min_blob_area=100)
    assert len(events) == 1, events
    assert events[0][0] == source
    assert 7.8 <= events[0][1] <= 8.2, events
    assert 14.8 <= events[0][2] <= 15.2, events
    duration = cut(*events[0], target, pad_seconds=2)
    assert target.is_file() and source.is_file()
    assert 10 <= duration <= 12, duration
    assert events[0][2] + 2 < 20
    stream = json.loads(subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_streams",
         "-of", "json", str(target)], text=True,
    ))["streams"][0]
    assert stream["codec_name"] == "h264"
    make_video(blank, moving=False)
    assert scan(blank, min_blob_area=100) == []
    truncated.write_bytes(source.read_bytes()[:100])
    try:
        scan(truncated, min_blob_area=100)
    except ValueError:
        pass
    else:
        raise AssertionError("truncated input accepted")
    assert truncated.exists()
    print(f"PASS: moving/static/truncated scan; H.264 cut {duration:.1f}s")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        check_video(Path(sys.argv[1]))
    else:
        with TemporaryDirectory() as directory:
            check_video(Path(directory))
