"""Pinned adapter continuation, radio identity and automatic reseed contracts."""

import copy
import sys
import time
from dataclasses import dataclass
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock, Mock

import pytest
from homestarter.ma_media import MediaAdapter
from homestarter.ma_radio import RadioImporter


def candidate(identity):
    value = {
        "item_id": identity,
        "media_type": "track",
        "provider_mappings": [{"provider_instance": "house", "available": True}],
        "artists": [{"item_id": identity + "artist"}],
        "album": {"item_id": identity + "album"},
    }
    return Obj(item_id=identity, to_dict=lambda: copy.deepcopy(value))


@pytest.fixture
def adapter(tmp_path):
    one, two = candidate("one"), candidate("two")
    one.provider_mappings = [Obj(provider_instance="house", item_id="one")]
    current = Obj(queue_item_id="queue-one", media_item=one)
    data = Obj(session_id="native", queue=Obj(current_item=current, active=True, state="playing"), items=[current])
    provider = Obj(get_similar_tracks=AsyncMock(return_value=[two]))
    mass = Obj(storage_path=str(tmp_path), player_queues=Obj(queue_data_or_none=lambda q: data, set_autoplay=Mock()), get_provider=lambda p: provider)
    guard = Obj(mass=mass, spotify=lambda i: True, bind=AsyncMock(return_value={"provider": "house"}))
    media = MediaAdapter(guard)
    media.original_similar = AsyncMock(side_effect=AssertionError("No generic fallback"))
    return media, data, provider


async def test_continuation_uses_exact_allocated_provider_and_never_library(adapter):
    media, data, provider = adapter
    assert [t.item_id for t in await media.similar("q")] == ["two"]
    provider.get_similar_tracks.assert_awaited_once_with("one", limit=25)
    media.original_similar.assert_not_awaited()
    provider.get_similar_tracks.side_effect = ValueError("upstream failure")
    assert await media.similar("q") == []
    assert media.continuation["q"] == "unavailable"
    media.original_similar.assert_not_awaited()


async def test_continuation_discards_results_after_native_session_changes(adapter):
    media, data, provider = adapter

    async def changed(*args, **kwargs):
        data.session_id = "somebody-else"
        return [candidate("two")]

    provider.get_similar_tracks.side_effect = changed
    assert await media.similar("q") == []


async def test_keep_going_is_scoped_to_the_current_item(adapter):
    media, _, _ = adapter
    assert (await media.keep_going("q", "not-the-current-item"))["state"] == "changed"
    media.mass.player_queues.set_autoplay.assert_not_called()
    assert (await media.keep_going("q", "queue-one"))["state"] == "requested"
    media.mass.player_queues.set_autoplay.assert_called_once_with("q", True)


def session(**changes):
    return {
        "session": "native",
        "logical_session": "logical",
        "listener": "House",
        "options": {"mode": "anything", "reseed_tracks": 3, "reseed_minutes": 10},
        "checked_at": time.time(),
        "seeded_at": time.time(),
        "played_seconds": 0,
        "track_seconds": 0,
        "tracks": 0,
        "item": "queue-one",
        **changes,
    }


async def test_reseed_waits_for_track_boundary_and_not_each_skip(adapter):
    media, data, _ = adapter
    media.sessions["q"] = session(played_seconds=601)
    media.play = AsyncMock(return_value={"state": "requested"})
    await media.tick()
    media.play.assert_not_awaited()
    data.queue.current_item = Obj(queue_item_id="queue-two", media_item=candidate("two"))
    await media.tick()
    media.play.assert_awaited_once_with("q", "House", media.sessions["q"]["options"], "native", "queue-two", False)
    media.sessions["q"] = session()
    media.play.reset_mock()
    await media.tick()
    assert media.sessions["q"]["tracks"] == 0
    media.play.assert_not_awaited()


async def test_reseed_failure_disables_continuation_without_library_fallback(adapter):
    media, data, _ = adapter
    media.sessions["q"] = session(tracks=3)
    data.queue.current_item = Obj(queue_item_id="queue-two", media_item=candidate("two"))
    media.play = AsyncMock(return_value={"state": "discovery_unavailable"})
    await media.tick()
    assert "q" not in media.sessions
    media.mass.player_queues.set_autoplay.assert_called_once_with("q", False)


async def test_old_session_state_cannot_follow_another_users_queue(adapter):
    media, data, _ = adapter
    media.sessions["q"] = session()
    data.session_id = "replacement"
    assert (await media.queue_context("q"))["logical_session"] is None
    await media.tick()
    assert not media.sessions


@dataclass(frozen=True)
class Mapping:
    item_id: str
    provider_domain: str = "builtin"
    provider_instance: str = "builtin"
    available: bool = True


@pytest.fixture
def radio(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "music_assistant_models.enums", Obj(MediaType=Obj(RADIO="radio")))
    monkeypatch.setitem(sys.modules, "music_assistant_models.media_items", Obj(ProviderMapping=Mapping))
    items, stored, events = {}, {}, []

    async def by_id(item_id, provider):
        if provider == "library":
            return items.get(str(item_id))
        return next((i for i in items.values() if any(m.item_id == item_id and m.provider_instance == provider for m in i.provider_mappings)), None)

    async def add_url(url, name, image):
        events.append(("url", url))
        stored[url] = name
        return Obj(name=name, sort_name=name, provider_mappings={Mapping(url)}, metadata=Obj(description=None, images=[]))

    async def add_item(item):
        item.item_id = str(len(items) + 1)
        item.uri = "library://radio/" + item.item_id
        item.favorite = False
        items[item.item_id] = item
        return item

    async def update(item_id, item, overwrite):
        items[item_id] = item
        return item

    async def mappings(item_id, values):
        events.append(("mapping", values[0].item_id))
        items[item_id].provider_mappings.update(values)

    async def remove_mapping(item_id, provider, url):
        items[item_id].provider_mappings = {m for m in items[item_id].provider_mappings if m.item_id != url}

    builtin = Obj(instance_id="builtin", add_radio=add_url, library_remove=AsyncMock())
    controller = Obj(
        get_library_item_by_prov_id=by_id,
        library_items=AsyncMock(side_effect=lambda **kwargs: list(items.values())),
        add_item_to_library=add_item,
        update_item_in_library=update,
        add_provider_mappings=mappings,
        remove_provider_mapping=remove_mapping,
    )
    mass = Obj(storage_path=str(tmp_path), get_provider=lambda _: builtin, music=Obj(radio=controller))
    return RadioImporter(mass), items, builtin, events, mass


async def test_radio_import_is_idempotent_and_changed_url_keeps_library_id_and_favorite(radio):
    importer, items, builtin, events, _ = radio
    station = {"id": "listnr:opaque", "name": "Example Radio", "url": "https://sa47.scastream.com.au/live/old/playlist.m3u8"}
    first = await importer.upsert(station)
    items[first["library_id"]].favorite = True
    await importer.upsert(station)
    assert len(items) == 1
    updated = {**station, "url": "https://sa47.scastream.com.au/live/new/playlist.m3u8", "name": "Renamed Radio"}
    result = await importer.upsert(updated)
    assert result["library_id"] == first["library_id"]
    assert items[first["library_id"]].favorite is True
    assert len(items) == 1 and items[first["library_id"]].name == "Renamed Radio"
    assert [m.item_id for m in items[first["library_id"]].provider_mappings] == [updated["url"]]
    builtin.library_remove.assert_awaited_once_with(station["url"], "radio")
    assert events.index(("mapping", updated["url"])) < events.index(("url", updated["url"]))


async def test_radio_recovery_after_state_loss_finds_provenance_not_name(radio):
    importer, items, _, _, mass = radio
    station = {"id": "listnr:opaque", "name": "Same title", "url": "https://sa47.scastream.com.au/live/old/playlist.m3u8"}
    first = await importer.upsert(station)
    importer.path.unlink()
    recovered = RadioImporter(mass)
    result = await recovered.upsert({**station, "url": "https://sa47.scastream.com.au/live/new/playlist.m3u8"})
    assert result["library_id"] == first["library_id"] and len(items) == 1


async def test_radio_import_refuses_session_urls_before_any_library_write(radio):
    importer, items, _, _, _ = radio
    with pytest.raises(ValueError, match="sessions"):
        await importer.upsert({"id": "listnr:opaque", "name": "Example", "url": "https://sa47.scastream.com.au/live/test.m3u8?downloadSessionID=temporary"})
    assert not items


async def test_managed_radio_never_merges_only_by_name(radio):
    importer, _, _, _, mass = radio
    ctrl = mass.music.radio
    original = AsyncMock(return_value=99)
    ctrl._get_library_item_by_match = original
    importer.install()
    managed = Obj(
        metadata=Obj(description="Home Starter source: listnr:other"), provider_mappings={Mapping("https://sa47.scastream.com.au/live/other/test.m3u8")}
    )
    assert await ctrl._get_library_item_by_match(managed) is None
    original.assert_not_awaited()
    assert await ctrl._get_library_item_by_match(Obj(metadata=Obj(description=None))) == 99


async def test_reused_library_id_after_rebuild_never_overwrites_unrelated_radio(radio):
    importer, items, _, _, _ = radio
    unrelated = Obj(
        item_id="1",
        uri="library://radio/1",
        name="Unrelated",
        favorite=True,
        provider_mappings={Mapping("https://sa47.scastream.com.au/live/unrelated/test.m3u8")},
        metadata=Obj(description=None, images=[]),
    )
    items["1"] = unrelated
    importer.records["listnr:opaque"] = {"library_id": "1", "url": "https://sa47.scastream.com.au/live/old/test.m3u8"}
    result = await importer.upsert({"id": "listnr:opaque", "name": "Example", "url": "https://sa47.scastream.com.au/live/new/test.m3u8"})
    assert result["library_id"] != "1" and items["1"] is unrelated
    assert unrelated.favorite and unrelated.name == "Unrelated"


async def test_catalogue_search_result_cannot_replace_a_session_started_while_searching(adapter, monkeypatch):
    media, data, provider = adapter
    monkeypatch.setitem(sys.modules, "music_assistant_models.enums", Obj(MediaType=Obj(TRACK="track")))
    data.queue.state = "idle"
    media.mass.players = Obj(get_player=lambda _: Obj(state=Obj(playback_state="idle")))
    lease = {"queue": "discovery:q", "provider": "house", "token": "fixture-lease", "session": "preparing", "listener": "House"}
    engine = Obj(leases={"house": lease}, reserve=AsyncMock(return_value=lease), renew_discovery=AsyncMock(), abort_discovery=AsyncMock())
    media.guard.engine = engine
    media.guard.providers = lambda: []
    media.guard.play = AsyncMock()

    async def search(*args):
        data.session_id = "other-actor-started"
        return Obj(tracks=[candidate("different")])

    provider.search = search
    assert (await media.play("q", "House", {}))["state"] == "changed"
    media.guard.play.assert_not_awaited()
    engine.abort_discovery.assert_awaited_once_with("fixture-lease", None)
