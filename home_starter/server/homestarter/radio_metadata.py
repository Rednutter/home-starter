"""Conservative radio display hygiene; never changes stream or queue identity."""

import re

_CUE = re.compile(r"^asset\s+(?:stop|start|end|link)\b[\s:|_-]*(?:\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}T)", re.IGNORECASE)
_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$")


def text(value):
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    if not value or "://" in value or _CUE.match(value) or _STAMP.fullmatch(value) or value.startswith("Home Starter source:"):
        return ""
    return value[:240]


def fields(title, artist=None, album=None, *, station=""):
    """Keep genuine radio metadata; an invalid title must not retain its cue artist."""
    clean = text(title)
    return {"title": clean or text(station), "artist": text(artist) if clean else "", "album": text(album)}


def queue_title(row, fallback="Radio"):
    media = row.get("media_item") or {}
    return text(media.get("name")) or text(fallback) or "Radio"
