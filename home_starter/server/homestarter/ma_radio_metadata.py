"""Prepared, opt-in MA radio metadata fix. No startup hook installs this module.

Separate review/deployment from the existing account-guard repair is required.
The shared Player model derives station fallback when stream title is empty;
both Cast initial-load and live-update metadata use that PlayerMedia.
"""

import hashlib
import inspect
from copy import deepcopy
from functools import wraps
from pathlib import Path

from .radio_metadata import fields, queue_title

AUDIO_SHA256 = "0e97b57795c20a231b860fdb5edc8fa71db03288f31d1b515a509cd117a1b1a9"
CAST_SHA256 = "f373d652ef77dbc2b3a7d2449534f2d22a4f253276c146011e28530dcefc4cb9"
PLAYER_SHA256 = "8fa9bc2132ef6505fed6ee6ff8b8eac76307838924cdfa63a034a15c967deac3"


def cast_payload(payload, media, queue):
    """Display-only copy; never rewrite contentId, customData, timers or artwork."""
    if media.media_type != "radio":
        return payload
    item = getattr(queue, "current_item", None)
    station = "Radio"
    if item is not None and item.queue_item_id == media.queue_item_id:
        station = queue_title({"media_item": {"name": getattr(item.media_item, "name", None)}})
    result = deepcopy(payload)
    meta = result["metadata"]
    clean = fields(meta.get("title"), meta.get("artist"), meta.get("albumName"), station=station)
    meta.update(title=clean["title"], songName=clean["title"], artist=clean["artist"], albumName=clean["album"])
    return result


def wrap(original):
    @wraps(original)
    def update(streamdetails, artist, title, image_url=None, album=None):
        clean = fields(title, artist, album)
        # Empty title deliberately selects MA's current catalogue station name.
        # Artwork and transport identity are passed through without alteration.
        return original(streamdetails, clean["artist"] or None, clean["title"], image_url, clean["album"] or None)

    return update


def install(mass):
    """Explicit operator entry only; reject a different installed implementation."""
    from music_assistant.models.player import Player
    from music_assistant.providers.chromecast.player import ChromecastPlayer

    audio = mass.streams.audio
    original = audio._update_radio_stream_metadata
    original_cast = ChromecastPlayer._create_cc_media_item
    path = inspect.getsourcefile(original)
    cast_path = inspect.getsourcefile(original_cast)
    player_path = inspect.getsourcefile(Player)
    if (
        mass.version != "2.10.7"
        or not path
        or hashlib.sha256(Path(path).read_bytes()).hexdigest() != AUDIO_SHA256
        or not cast_path
        or hashlib.sha256(Path(cast_path).read_bytes()).hexdigest() != CAST_SHA256
        or not player_path
        or hashlib.sha256(Path(player_path).read_bytes()).hexdigest() != PLAYER_SHA256
    ):
        raise RuntimeError("Radio metadata fix needs review against the installed MA source; nothing changed.")
    if list(inspect.signature(original).parameters) != ["streamdetails", "artist", "title", "image_url", "album"] or list(
        inspect.signature(original_cast).parameters
    ) != ["self", "media", "stream_url"]:
        raise RuntimeError("Radio metadata signature changed; nothing changed.")

    @wraps(original_cast)
    def create(player, media, stream_url):
        payload = original_cast(player, media, stream_url)
        queue = mass.player_queues.get(media.source_id) if media.media_type == "radio" else None
        return cast_payload(payload, media, queue)

    audio._update_radio_stream_metadata = wrap(original)
    ChromecastPlayer._create_cc_media_item = create
