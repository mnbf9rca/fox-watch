import base64
from http.client import HTTPException
import json
import logging
import math
import os
from pathlib import Path
import re
from urllib import error, request
from urllib.parse import urlsplit


LABELS = ("fox", "hedgehog", "cat", "badger", "rat", "mouse", "bird", "deer", "other", "none")


def parse_answer(text: str) -> tuple[str, float]:
    if not isinstance(text, str):
        raise ValueError("answer must be text")
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), re.DOTALL)
    try:
        answer = json.loads(fenced[1] if fenced else text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise
        answer, _ = json.JSONDecoder().raw_decode(text, start)
    if not isinstance(answer, dict) or answer.get("label") not in LABELS:
        raise ValueError("invalid label")
    confidence = answer.get("confidence")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1 or not math.isfinite(confidence):
        raise ValueError("invalid confidence")
    return answer["label"], float(confidence)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def classify(model: str, frames: list[Path]) -> tuple[str, float]:
    try:
        provider, model_id = model.split("/", 1)
        if provider not in ("nous", "deepinfra", "together") or not model_id or len(frames) != 4:
            raise ValueError("invalid model or frames")
        base = os.environ[f"{provider.upper()}_BASE_URL"]
        url = urlsplit(base)
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("invalid base URL")
        content = [{"type": "text", "text": (
            "These four infrared garden camera frames show one visit. Identify the animal. "
            f"Return only a JSON object with label (one of {', '.join(LABELS)}) and "
            "confidence (a number from 0 to 1). Use none if no animal is visible."
        )}]
        for frame in frames:
            encoded = base64.b64encode(frame.read_bytes()).decode("ascii")
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}"}})
        payload = {"model": model_id, "messages": [{"role": "user", "content": content}], "temperature": 0}
        req = request.Request(base.rstrip("/") + "/chat/completions", json.dumps(payload).encode(), headers={
            "Authorization": "Bearer " + os.environ[f"{provider.upper()}_API_KEY"],
            "Content-Type": "application/json",
            "User-Agent": "foxcam/0.1",
        })
        with request.build_opener(_NoRedirect()).open(req, timeout=60) as response:
            return parse_answer(json.load(response)["choices"][0]["message"]["content"])
    except (OSError, error.URLError, HTTPException, ValueError, KeyError, IndexError, TypeError) as exc:
        logging.warning("%s: %s status=%s", model, type(exc).__name__, getattr(exc, "code", "-"))
        return "unclassified", 0.0


def compare(sidecars: list[dict], primary_model: str) -> dict[str, tuple[int, int]]:
    models = dict.fromkeys(model for row in sidecars for model in row["labels"])
    result = {}
    for model in models:
        pairs = [(row["labels"].get(model, {}).get("label"),
                  row["labels"].get(primary_model, {}).get("label")) for row in sidecars]
        valid = [(label, primary) for label, primary in pairs if label in LABELS and primary in LABELS]
        result[model] = (sum(label == primary for label, primary in valid), len(valid))
    return result
