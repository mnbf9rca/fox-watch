from datetime import datetime, time
from zoneinfo import ZoneInfo
from foxcam.events import clip_name, merge_events, night_for

def test_events_and_local_calendar_dates():
    assert merge_events([], 10) == []
    assert merge_events([1.0, 1.1, 4.1, 7.3], 10) == [(1.0, 4.2), (7.3, 7.4)]
    zone = ZoneInfo("Europe/London")
    for stamp in ("2026-09-28T23:30:00+00:00", "2026-09-29T05:30:00+00:00"):
        for start in (time(7), time(19), time(23)):
            assert night_for(datetime.fromisoformat(stamp), start, zone) == "2026-09-29"
    early = datetime.fromisoformat("2026-10-25T00:30:00+00:00")
    late = datetime.fromisoformat("2026-10-25T01:30:00+00:00")
    assert night_for(early, time(19), zone) == night_for(late, time(19), zone) == "2026-10-25"
    assert clip_name(early) == "00-30-00.mp4"
    assert clip_name(early) != clip_name(late)
