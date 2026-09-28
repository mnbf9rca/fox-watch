from collections import Counter
from datetime import date, datetime, timezone
from html import escape
import json
import logging
import math
from pathlib import Path
from urllib.parse import quote

from foxcam.classify import parse_answer


PALETTE = dict(fox="#a84300", hedgehog="#626400", cat="#7051a1", badger="#333333",
               rat="#755139", mouse="#846451", bird="#176b9b", deer="#856000",
               other="#006c67", none="#546e7a", unclassified="#777777")
EDGES = dict(far=(50, 0), fence=(50, 100), left=(0, 50), right=(100, 50), unknown=(50, 50))


def _page(title, body):
    return f'''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fox Watch — {escape(title)}</title>
<style>body{{font:1rem system-ui;max-width:70rem;margin:auto;padding:1rem;background:#fff;color:#222}}a{{color:#125e96}}.visits{{display:grid;grid-template-columns:repeat(auto-fit,minmax(18rem,1fr));gap:1rem}}article{{border:1px solid #bbb;padding:1rem}}img{{width:100%}}svg{{width:100%;max-width:30rem}}li{{margin:.4rem 0}}</style>
<body><header><h1>Fox Watch</h1></header><main><h2>{escape(title)}</h2>{body}</main></body></html>'''


def _answer(answer):
    if answer == {"label": "unclassified", "confidence": 0}:
        return "unclassified", 0.0
    return parse_answer(json.dumps(answer))


def _primary(visit, model):
    return _answer(visit["labels"].get(model, {"label": "unclassified", "confidence": 0}))


def render_night(night: str, visits: list[dict], primary_model: str) -> str:
    if date.fromisoformat(night).isoformat() != night:
        raise ValueError("invalid night")
    cards, arrows, legend = [], [], []
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
        when = stamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        entry, exit_edge = visit["entry_edge"], visit["exit_edge"]
        if entry not in EDGES or exit_edge not in EDGES:
            raise ValueError("invalid edge")
        label, confidence = _primary(visit, primary_model)
        answers = []
        for model, answer in visit["labels"].items():
            species, score = _answer(answer)
            answers.append(f"<li>{escape(model)}: {species} ({score:.0%})</li>")
        media = f"/nights/{quote(night, safe='')}/"
        thumbnail = media + quote(frames[3], safe="")
        video = media + quote(clip.removesuffix(".mp4") + ".annotated.mp4", safe="")
        description = f"Visit {number}: {label}, {when}, {entry} → {exit_edge}"
        cards.append(f'''<article><h3>Visit {number}: {label} ({confidence:.0%})</h3>
<a href="{video}"><img src="{thumbnail}" alt="{escape(description)}"><br>Watch annotated clip</a>
<p>{when} · {duration:g} seconds · {entry} → {exit_edge}</p><ul>{''.join(answers)}</ul></article>''')
        x1, y1 = EDGES[entry]
        x2, y2 = EDGES[exit_edge]
        path = f"M {x1} {y1} L {x2} {y2}"
        if (x1, y1) == (x2, y2):
            path = f"M {x1} {y1} c -15,-15 15,-15 0,0"
        color = PALETTE[label]
        arrows.append(f'''<defs><marker id="arrow-{number}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker></defs>
<path d="{path}" fill="none" stroke="{color}" stroke-width="1.5" marker-end="url(#arrow-{number})"><title>{escape(description)}</title></path>''')
        legend.append(f'<li><span style="color:{color}" aria-hidden="true">●</span> {escape(description)}</li>')
    content = f'''<p><a href="index.html">All nights</a> · Primary model: {escape(primary_model)}</p>
<svg viewBox="-20 -20 140 140" role="img" aria-labelledby="map-title map-description">
<title id="map-title">8 × 8 metre garden patch</title><desc id="map-description">Entry-to-exit arrows; visit details in the legend below. Unknown endpoints are drawn at the centre. These are schematic edges, not calibrated positions.</desc>
<rect x="0" y="0" width="100" height="100" fill="#f6f7f3" stroke="#333"/>
<g font-size="5" text-anchor="middle"><text x="50" y="-5">far</text><text x="50" y="110">fence</text><text x="-10" y="50">left</text><text x="110" y="50">right</text></g>{''.join(arrows)}</svg>
<p>Unknown endpoints use the centre; arrows show schematic edges, not calibrated positions.</p>
<ul aria-label="Visit map legend">{''.join(legend)}</ul>
<div class="visits">{''.join(cards) if cards else '<p>No visits recorded</p>'}</div>'''
    return _page(night, content)


def render_index(nights: dict[str, list[dict]], primary_model: str) -> str:
    items = []
    for night in sorted(nights, reverse=True):
        counts = Counter(_primary(visit, primary_model)[0] for visit in nights[night])
        summary = ", ".join(f"{species}: {count}" for species, count in sorted(counts.items())) or "No visits recorded"
        items.append(f'<li><a href="{quote(night, safe="")}.html">{escape(night)}</a> — {summary}</li>')
    return _page("Nights", f'<p>Primary model: {escape(primary_model)}</p><ul>{"".join(items)}</ul>')


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
