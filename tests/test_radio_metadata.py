"""Synthetic radio cue/receiver regressions; no Cast device is contacted."""

from copy import deepcopy
from types import ModuleType
from types import SimpleNamespace as NS

import pytest
from homestarter.listening import media_record
from homestarter.listening_sessions import title as queue_display_title
from homestarter.ma_radio_metadata import cast_payload, wrap
from homestarter.radio_metadata import fields, text
from homestarter.wall_media import now_playing


@pytest.mark.parametrize("failure", ["version", "audio", "cast", "player", "signature"])
def test_native_candidate_refuses_incompatibility_before_either_hook_changes(tmp_path, monkeypatch, failure):
    import hashlib
    import sys

    from homestarter import ma_radio_metadata as candidate

    def update(streamdetails, artist, title, image_url=None, album=None):
        pass

    class Cast:
        def _create_cc_media_item(self, media, stream_url):
            pass

    original_cast = Cast._create_cc_media_item
    module = ModuleType("music_assistant.providers.chromecast.player")
    module.ChromecastPlayer = Cast
    monkeypatch.setitem(sys.modules, module.__name__, module)
    player_module = ModuleType("music_assistant.models.player")
    player_module.Player = type("Player", (), {})
    monkeypatch.setitem(sys.modules, player_module.__name__, player_module)
    path = tmp_path / "synthetic.py"
    path.write_text("synthetic reviewed implementation", encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(candidate, "AUDIO_SHA256", "different" if failure == "audio" else sha)
    monkeypatch.setattr(candidate, "CAST_SHA256", "different" if failure == "cast" else sha)
    monkeypatch.setattr(candidate, "PLAYER_SHA256", "different" if failure == "player" else sha)
    monkeypatch.setattr(candidate.inspect, "getsourcefile", lambda _: str(path))
    if failure == "signature":

        def update(unexpected):
            pass

    audio = NS(_update_radio_stream_metadata=update)
    mass = NS(version="2.10.8" if failure == "version" else "2.10.7", streams=NS(audio=audio))
    with pytest.raises(RuntimeError, match="nothing changed"):
        candidate.install(mass)
    assert audio._update_radio_stream_metadata is update
    assert Cast._create_cc_media_item is original_cast


@pytest.mark.parametrize("cue", ["Asset Stop 00:00 2026-10-19T05:20:00Z", "ASSET START 00:00", "Asset Link 12:15", "2026-10-19T05:20:00Z", "", None])
def test_control_metadata_falls_back_without_stale_cue_artist(cue):
    assert fields(cue, "old artist", "Home Starter source: listnr:synthetic", station="Example Radio") == {"title": "Example Radio", "artist": "", "album": ""}


@pytest.mark.parametrize("title", ["Stop", "Don't Stop Me Now", "Asset Stop", "News at 12:00", "Morning Show", "1999", "00:00", "Ocean - Live"])
def test_genuine_track_show_and_ambiguous_titles_are_preserved(title):
    assert fields(title, "Artist", "Show") == {"title": title, "artist": "Artist", "album": "Show"}


def test_native_update_feeds_station_fallback_to_both_cast_paths():
    calls = []

    def original(*args):
        calls.append(args)

    details, image = object(), "https://example.invalid/art.jpg"
    update = wrap(original)
    update(details, "Asset Stop 00:00", "Asset Stop 00:00 2026-10-19T05:20:00Z", image)
    assert calls[-1] == (details, None, "", image, None)
    # Reviewed Player model: empty stream title -> current catalogue station;
    # initial Cast metadata and live customData metadata both use PlayerMedia.
    player_title = calls[-1][2] or "Example Radio"
    assert player_title == "Example Radio"
    update(details, "Real Artist", "Real Song", image, "Real Album")
    assert calls[-1] == (details, "Real Artist", "Real Song", image, "Real Album")


def test_cast_initial_payload_keeps_transport_and_artwork_untouched():
    payload = {
        "metadata": {
            "title": "Asset Stop 00:00 2026-10-19T05:20:00Z",
            "songName": "cue",
            "artist": "cue",
            "albumName": "Home Starter source: listnr:synthetic",
            "images": [{"url": "synthetic-art"}],
        },
        "contentId": "synthetic-transport",
        "customData": {"queue_item_id": "item"},
        "duration": None,
        "streamType": "LIVE",
    }
    before = deepcopy(payload)
    media = NS(media_type="radio", queue_item_id="item")
    queue = NS(current_item=NS(queue_item_id="item", media_item=NS(name="Example Radio")))
    result = cast_payload(payload, media, queue)
    assert result["metadata"]["title"] == result["metadata"]["songName"] == "Example Radio"
    assert result["metadata"]["artist"] == result["metadata"]["albumName"] == ""
    assert result["metadata"]["images"] == before["metadata"]["images"]
    assert {k: v for k, v in result.items() if k != "metadata"} == {k: v for k, v in before.items() if k != "metadata"}
    assert payload == before
    queue.current_item.queue_item_id = "different"
    assert cast_payload(payload, media, queue)["metadata"]["title"] == "Radio"
    media.media_type = "track"
    assert cast_payload(payload, media, queue) is payload


def test_web_and_airtouch_use_catalogue_identity_and_wall_keeps_station():
    row = {"uri": "builtin://radio/synthetic", "media_type": "radio", "name": "Example Radio"}
    assert media_record(row)["title"] == "Example Radio"
    assert media_record({**row, "name": "Asset Stop 00:00"})["title"] == "Radio"
    assert queue_display_title("Asset Stop 00:00", radio=True) == "Radio"
    assert queue_display_title("Example Radio", radio=True) == "Example Radio"
    player = {
        "player_id": "p",
        "name": "Room",
        "available": True,
        "playback_state": "playing",
        "active_source": "p",
        "current_media": {"title": "Asset Stop 00:00"},
    }
    queue = {"queue_id": "p", "active": True, "state": "playing", "current_item": {"media_item": row}}
    assert now_playing([player], [queue]) == [{"title": "Example Radio", "artist": "", "room": "Room"}]
    assert text("https://example.invalid/private-delivery") == ""
