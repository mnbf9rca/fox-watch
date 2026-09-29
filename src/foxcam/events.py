from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


def merge_events(
    times: list[float], fps: float, gap_seconds: float = 3
) -> list[tuple[float, float]]:
    if fps <= 0 or gap_seconds < 0:
        raise ValueError("fps must be positive and gap_seconds nonnegative")
    events = []
    if times:
        start = previous = times[0]
        for current in times[1:]:
            if round(current - previous, 6) > gap_seconds:
                events.append((round(start, 6), round(previous + 1 / fps, 6)))
                start = current
            previous = current
        events.append((round(start, 6), round(previous + 1 / fps, 6)))
    return events


def night_for(start_utc: datetime, start_time: time, zone: ZoneInfo) -> str:
    return start_utc.astimezone(zone).date().isoformat()


def clip_name(start_utc: datetime) -> str:
    return start_utc.astimezone(timezone.utc).strftime("%H-%M-%S.mp4")
