from collections import Counter
from datetime import date, datetime, time, timezone
from html import escape
import json
import logging
import math
import os
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from foxcam.classify import parse_answer
from foxcam.ground import PATCH_OUTLINE_M


PALETTE = dict(fox="#a84300", hedgehog="#626400", cat="#7051a1", badger="#333333",
               rat="#755139", mouse="#846451", bird="#176b9b", deer="#856000",
               dog="#9b5100", person="#126451", vehicle="#2549a0",
               other="#006c67", none="#546e7a", unclassified="#777777")
EDGES = {"far", "fence", "left", "right", "unknown"}


def _page(title, body, css=""):
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fox Watch — {escape(title)}</title>
<style>body{{font:1rem system-ui;max-width:70rem;margin:auto;padding:1rem;background:#fff;color:#222}}a{{color:#125e96}}.visits{{display:grid;grid-template-columns:repeat(auto-fit,minmax(18rem,1fr));gap:1rem}}article{{border:1px solid #bbb;padding:1rem}}img{{width:100%}}svg{{width:100%;max-width:30rem}}li{{margin:.4rem 0}}main>label{{margin-right:1rem}}{css}</style>
<body><header><h1>Fox Watch</h1></header><main><h2>{escape(title)}</h2>{body}</main></body></html>'''


def _answer(answer):
    if answer == {"label": "unclassified", "confidence": 0}:
        return "unclassified", 0.0
    return parse_answer(json.dumps(answer))[:2]


def _primary(visit, model):
    return _answer(visit["labels"].get(model, {"label": "unclassified", "confidence": 0}))


def _ground_segments(rows):
    if not isinstance(rows, list):
        raise ValueError("invalid ground track")
    segments, current = [], []
    for row in rows:
        if (not isinstance(row, list) or len(row) != 3 or type(row[0]) is not int
                or row[0] < 0):
            raise ValueError("invalid ground point")
        _, across, forward = row
        if across is None and forward is None:
            valid = False
        else:
            if any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in (across, forward)):
                raise ValueError("invalid ground coordinate")
            valid = forward >= 0 and math.hypot(across, forward) <= 100
        if valid:
            current.append((across, -forward))
        elif current:
            segments.append(current)
            current = []
    if current:
        segments.append(current)
    return segments


def render_night(night: str, visits: list[dict], primary_model: str) -> str:
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError("invalid night")
    cards, arrows, legend, map_points = {}, [], [], []
    counts = Counter()
    zone = ZoneInfo(os.environ.get("TZ", "Europe/London"))
    stop_time = time.fromisoformat(os.environ.get("STOP_TIME", "07:00"))
    start_time = time.fromisoformat(os.environ.get("START_TIME", "19:00"))
    for number, visit in enumerate(visits, 1):
        if visit["night"] != night or not isinstance(visit["track"], list):
            raise ValueError("invalid sidecar")
        duration = visit["duration_s"]
        if type(duration) not in (int, float) or duration < 0 or not math.isfinite(duration):
            raise ValueError("invalid duration")
        frames, clip = visit["frames"], visit["clip"]
        if not isinstance(frames, list) or len(frames) != 4:
            raise ValueError("expected four frames")
        for name in [clip, *frames]:
            if not isinstance(name, str) or not name or any(part in name for part in ("/", "\\", "..")):
                raise ValueError("invalid media basename")
        stamp = datetime.fromisoformat(visit["start_utc"])
        if stamp.tzinfo is None:
            raise ValueError("timestamp must have a timezone")
        local = stamp.astimezone(zone)
        when = local.strftime("%Y-%m-%d %H:%M %Z")
        daytime = (stop_time <= local.time() < start_time if stop_time < start_time
                   else not start_time <= local.time() < stop_time)
        hour = local.replace(minute=0, second=0, microsecond=0).astimezone(timezone.utc)
        entry, exit_edge = visit["entry_edge"], visit["exit_edge"]
        if entry not in EDGES or exit_edge not in EDGES:
            raise ValueError("invalid edge")
        tracks = visit.get("tracks") or [visit]
        track_answers = [_primary(item, primary_model) for item in tracks]
        label, _ = max(track_answers, key=lambda answer: {"none": 0, "unclassified": 0, "vehicle": 1, "person": 2}.get(answer[0], 3))
        counts[label] += 1
        answers = []
        for model, answer in visit["labels"].items():
            species, score = _answer(answer)
            answers.append(f"<li>{escape(model)}: {species} ({score:.0%})</li>")
        media = f"/nights/{quote(night, safe='')}/"
        thumbnail = media + quote(frames[3], safe="")
        video = media + quote(clip.removesuffix(".mp4") + ".annotated.mp4", safe="")
        description = f"Visit {number}: {label}, {when}, {entry} → {exit_edge}"
        track_details = []
        for index, item in enumerate(tracks):
            species, score = track_answers[index]
            start, end = item["entry_edge"], item["exit_edge"]
            if start not in EDGES or end not in EDGES:
                raise ValueError("invalid track edge")
            detail = (f"Visit {number}, {when}, track {index + 1}: {item.get('class', 'unknown')} — "
                      f"{species} ({score:.0%}), {start} → {end}. {item.get('description', '')}")
            segments = _ground_segments(item.get("ground_track", []))
            map_points.extend(point for segment in segments for point in segment)
            if not segments:
                detail += " Ground position unavailable."
            track_details.append(f"<li>{escape(detail)}</li>")
            color = PALETTE[species]
            marker = f"arrow-{number}-{index}"
            path = " ".join(" ".join(f"{'M' if i == 0 else 'L'} {x:g} {y:g}"
                                     for i, (x, y) in enumerate(segment))
                            for segment in segments if len(segment) > 1)
            if path:
                arrows.append(f'''<defs><marker id="{marker}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker></defs>
<path d="{path}" fill="none" stroke="{color}" stroke-width=".06" marker-end="url(#{marker})"><title>{escape(detail)}</title></path>''')
            for segment in segments:
                if len(segment) == 1:
                    x, y = segment[0]
                    arrows.append(f'<circle cx="{x:g}" cy="{y:g}" r=".08" fill="{color}"><title>{escape(detail)}</title></circle>')
            legend.append(f'<li><span style="color:{color}" aria-hidden="true">●</span> {escape(detail)}</li>')
        heading = ', '.join(f'{species} ({score:.0%})' for species, score in track_answers)
        cards.setdefault(hour, []).append(f'''<article class="label-{label}{' daytime' if daytime else ''}" title="{escape(description)}"><h3>Visit {number}, {when}: {heading}</h3>
<a href="{video}"><img src="{thumbnail}" alt="{escape(description)}" loading="lazy"><br>Watch annotated clip</a>
<p>{when} · {duration:g} seconds · {entry} → {exit_edge}</p><ul>{''.join(answers)}</ul>
<ul aria-label="Tracks">{''.join(track_details)}</ul></article>''')
    filters = ''.join(f'<input type="checkbox" id="label-{label}"{" checked" if label != "none" else ""}><label for="label-{label}">{label} ({count})</label>'
                      for label, count in sorted(counts.items()))
    css = ''.join(f'#label-{label}:not(:checked) ~ .hours .label-{label} {{ display: none }}'
                  for label in counts)
    css += '#label-daytime:not(:checked) ~ .hours .daytime { display: none }details { margin: 1rem 0 }summary { cursor: pointer; font-weight: bold; margin: .5rem 0 }'
    groups = ''.join(f'<details open><summary>{hour.astimezone(zone):%Y-%m-%d %H:00 %Z} ({len(group)})</summary>'
                     f'<div class="visits">{"".join(group)}</div></details>' for hour, group in sorted(cards.items()))
    outline = " ".join(f"{across:g},{-forward:g}" for across, forward in PATCH_OUTLINE_M)
    viewbox = "-5 -10 11 11"
    if map_points:
        xs, ys = zip(*map_points)
        # Keep the outline, edge labels and scale bar in view, then include
        # every accepted path point with a half-metre margin.
        left, top = min(-5, min(xs)) - .5, min(-10, min(ys)) - .5
        right, bottom = max(6, max(xs)) + .5, max(1, max(ys)) + .5
        viewbox = f"{left:g} {top:g} {right - left:g} {bottom - top:g}"
    content = f'''<p><a href="index.html">All days</a> · Primary model: {escape(primary_model)}</p>
<p>Show visits by most interesting label:</p>{filters}
<input type="checkbox" id="label-daytime" checked><label for="label-daytime">Daytime</label>
<svg viewBox="{viewbox}" role="img" aria-labelledby="map-title map-description">
<title id="map-title">Ground paths on an approximate 8 × 8 metre garden patch</title>
<desc id="map-description">Calibrated bottom-centre ground-plane estimates in metres, across positive right and forward away from the camera. Paths break at unavailable positions. The outline is approximate and ground-plane estimates are invalid for airborne birds.</desc>
<polygon points="{outline}" fill="#f6f7f3" stroke="#333" stroke-width=".04"/>
<g font-size=".3" text-anchor="middle"><text x=".6" y="-9.6">far</text><text x="0" y="-.5">fence / near (approx.)</text><text x="0" y="-.15">Camera (0, 0)</text><text x="-4.5" y="-4.8">left</text><text x="5.4" y="-4.8">right</text></g>
<g stroke="#333" stroke-width=".04"><line x1="-4" y1=".6" x2="-3" y2=".6"/><line x1="-4" y1=".5" x2="-4" y2=".7"/><line x1="-3" y1=".5" x2="-3" y2=".7"/></g><text x="-3.5" y=".95" font-size=".3" text-anchor="middle">1 m</text>
{''.join(arrows)}</svg>
<p>Ground-plane estimates in metres, invalid for airborne birds. Approximate 8 × 8 m outline: centre line 4° right of the camera axis, far edge 8.8 m away; exact corners have not been surveyed. Edge names remain text descriptions. Legacy visits without ground data have no mapped path.</p>
<ul aria-label="Visit map legend">{''.join(legend)}</ul>
<div class="hours">{groups or '<p>No visits recorded</p>'}</div>'''
    return _page(night, content, css)


def render_index(nights: dict[str, list[dict]], primary_model: str) -> str:
    items = []
    for night in sorted(nights, reverse=True):
        counts = Counter(_primary(visit, primary_model)[0] for visit in nights[night])
        summary = ", ".join(f"{species}: {count}" for species, count in sorted(counts.items())) or "No visits recorded"
        items.append(f'<li><a href="{quote(night, safe="")}.html">{escape(night)}</a> — {summary}</li>')
    return _page("Days", f'<p>Primary model: {escape(primary_model)}</p><ul>{"".join(items)}</ul>')


def build_site(data_dir: Path, primary_model: str) -> None:
    nights = {}
    for directory in sorted((data_dir / "nights").glob("*")):
        if not directory.is_dir():
            continue
        try:
            render_night(directory.name, [], primary_model)
        except ValueError:
            logging.warning("Skipping invalid night directory %s", directory.name)
            continue
        visits = nights[directory.name] = []
        for sidecar in sorted(directory.glob("*.json")):
            try:
                visit = json.loads(sidecar.read_text())
                render_night(directory.name, [visit], primary_model)
                visits.append(visit)
            except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError):
                logging.warning("Skipping malformed sidecar %s", sidecar)
    site = data_dir / "site"
    site.mkdir(parents=True, exist_ok=True)
    pages = {f"{night}.html": render_night(night, visits, primary_model) for night, visits in nights.items()}
    pages["index.html"] = render_index(nights, primary_model)
    for name, html in pages.items():
        temporary = site / (name + ".tmp")
        temporary.write_text(html, encoding="utf-8")
        temporary.replace(site / name)
