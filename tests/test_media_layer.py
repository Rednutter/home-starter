"""Synthetic catalogue/discovery, local library safety and allocator handoff contracts."""

import io
import json
import random
import zipfile
from copy import deepcopy
from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock

import pytest
from homestarter import household_music, listnr, media_hygiene
from homestarter.ambient_catalogue import native_entries
from homestarter.listening import media_record
from homestarter.media_catalogue import MediaCatalogue
from homestarter.media_discovery import Discovery, constraints
from homestarter.postal_region import nearest_postcode
from homestarter.spotify_leases import AccountsBusy, SpotifyLeases


def track(identity="one", provider="shared", artist="artist", album="album", explicit=False):
    return {
        "item_id": identity,
        "uri": provider + "://track/" + identity,
        "name": "Example music",
        "media_type": "track",
        "provider_mappings": [{"provider_instance": provider, "available": True}],
        "artists": [{"item_id": artist}],
        "album": {"item_id": album},
        "metadata": {"explicit": explicit},
    }


async def test_catalogue_discovery_varies_and_never_reads_library():
    discovery = Discovery(random.Random(11), clock=lambda: 100)  # noqa: S311 -- deterministic catalogue test
    seeds = [discovery.seed({}) for _ in range(80)]
    assert len({s for s, _ in seeds}) == 4
    assert len({q for _, q in seeds}) > 30
    search = AsyncMock(return_value=[track()])
    chosen, diagnostic = await discovery.choose(search, "shared", {})
    assert chosen["item_id"] == "one"
    assert search.await_args.args[1] == 50
    assert diagnostic["exclusion_count"] == 1
    assert not discovery.playable(track("two"), "shared", {})  # same artist/album
    assert discovery.playable(track("three", artist="other", album="other"), "shared", {})


async def test_discovery_refuses_unavailable_other_account_and_explicit_results():
    engine = Discovery(random.Random(2))  # noqa: S311 -- deterministic catalogue test
    invalid = [track(provider="personal"), track(explicit=True), {**track(), "provider_mappings": []}]
    with pytest.raises(ValueError, match="catalogue discovery is unavailable"):
        await engine.choose(AsyncMock(return_value=invalid), "shared", {"exclude_explicit": True})


async def test_catalogue_failure_is_bounded_without_library_fallback():
    search = AsyncMock(side_effect=RuntimeError("upstream failure"))
    with pytest.raises(ValueError, match="catalogue discovery"):
        await Discovery().choose(search, "shared", {})
    assert search.await_count == 6


def test_discovery_modes_and_reseed_configuration():
    engine = Discovery(random.Random(5))  # noqa: S311 -- deterministic catalogue test
    assert "year:198" in engine.seed({"mode": "era", "era": 1980})[1]
    assert 'genre:"jazz"' in engine.seed({"mode": "genre", "genre": "jazz"})[1]
    assert constraints({"mode": "familiar", "genres": ["jazz"]})["genres"] == ["jazz"]
    for invalid in [{"reseed_tracks": 1}, {"mode": "genre", "genre": 'bad"query'}, {"mode": "era", "era": 1890}, {"mode": "unknown"}]:
        with pytest.raises(ValueError):
            constraints(invalid)


def test_repeat_window_expires_and_clock_rollback_does_not_pin_history():
    now = [100]
    discovery = Discovery(clock=lambda: now[0])
    discovery.remember(track())
    now[0] = 7300
    discovery.prune()
    assert discovery.recent == []
    discovery.remember(track())
    now[0] = 50
    discovery.prune()
    assert discovery.recent == []


def test_no_infinite_mix_is_exposed_as_household_discovery():
    assert media_record({"uri": "builtin://playlist/infinite_mix", "media_type": "playlist"}) is None
    assert media_record({"uri": "spotify://playlist/ordinary", "media_type": "playlist", "name": "Infinite summer"})


def test_catalogue_seed_can_be_saved_without_exposing_personal_overflow_source():
    providers = [{"id": "personal", "name": "Grant", "domain": "spotify", "available": True}, {"id": "radio", "domain": "radiobrowser", "available": True}]
    private = {"uri": "spotify://track/example", "kind": "track", "sources": ["personal"]}
    assert not household_music.visible(private, "House", providers)
    discovered = {**private, "sources": ["spotify_catalogue"]}
    assert household_music.visible(discovered, "House", providers)
    assert not household_music.visible({"uri": "spotify://track/unknown", "kind": "track"}, "House", providers)


def test_listnr_normalisation_and_local_region_ranking():
    row = {"id": "opaque", "slug": "rain", "name": "Light Rain", "stationType": "Music"}
    normal = listnr.normalize(row)
    assert normal["id"] == "listnr:opaque"
    assert (normal["category"], normal["subcategory"]) == ("ambient", "rain")
    assert normal["resolver"] == {"provider": "listnr", "station_id": "opaque"}
    assert listnr.regional_score({"name": "Example local radio"}, {"name": "Example", "search_terms": []}) > 0
    assert listnr.regional_score({"name": "Other radio"}, {"name": "Example", "search_terms": []}) == 0
    assert listnr.distance({"latitude": 0, "longitude": 0}, {"latitude": 0, "longitude": 0}) == 0
    assert listnr.distance({}, {}) is None
    assert listnr.ambient_group("Rainforest") == "nature"
    assert listnr.ambient_group("Pink noise") == "noise"
    assert listnr.ambient_group("Fans of Example Artist") is None


def test_native_ambient_identity_survives_provider_recreation_without_spotify():
    raw = {
        "item_id": "brown_noise",
        "provider": "ambient_old",
        "uri": "ambient_old://sound_effect/brown_noise",
        "name": "Brown noise",
        "media_type": "sound_effect",
    }
    first = native_entries([raw], [{"id": "ambient_old", "domain": "ambient_sounds", "available": True}], "first")[0]
    second = native_entries(
        [{**raw, "provider": "ambient_new", "uri": "ambient_new://sound_effect/brown_noise"}],
        [{"id": "ambient_new", "domain": "ambient_sounds", "available": True}],
        "second",
    )[0]
    assert first["id"] == second["id"] and first["uri"] != second["uri"]
    assert first["subcategory"] == "noise"


def test_postcode_is_computed_locally_from_country_dataset():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AU.txt", "AU\t1234\tExample\tState\tST\t\t\t\t\t0\t0\t1\nAU\t5678\tOther\tState\tST\t\t\t\t\t0\t10\t1\n")
    assert nearest_postcode(buffer.getvalue(), "AU", {"latitude": 0, "longitude": 0}) == "1234"
    assert nearest_postcode(buffer.getvalue(), "AU", {"latitude": 0, "longitude": 0}, ["Other"]) == "5678"


async def test_nearby_api_sends_only_a_postcode_and_never_home_coordinates():
    request = AsyncMock(return_value=(b'{"data":{"networks":[{"nearmeStations":[{"id":"opaque"}]}]}}', "application/json", listnr.API))
    assert await listnr.LiSTNR(request).nearby("1234") == {"listnr:opaque"}
    assert request.call_args.args[0] == listnr.API + "?postcode=1234"
    assert "latitude" not in request.call_args.args[1]["query"]


async def test_listnr_id_resolution_and_anonymous_catalogue_contract():
    row = {
        "id": "opaque",
        "slug": "example",
        "name": "Example Radio",
        "stationType": "Regional",
        "audioStreams": [{"url": "https://sa47.scastream.com.au/live/example/playlist.m3u8?dist=listnr-web"}],
    }
    request = AsyncMock(return_value=(json.dumps({"data": {"stations": [row]}}).encode(), "application/json", listnr.API))
    resolver = listnr.LiSTNR(request)
    result = await resolver.resolve("listnr:opaque")
    assert result["url"].endswith("?dist=listnr-web")
    assert request.call_args.args[1]["variables"] == {"ids": ["opaque"]}
    assert result["expires_at"] is None
    row["audioStreams"][0]["url"] += "&downloadSessionID=ephemeral"
    request.return_value = json.dumps({"data": {"stations": [row]}}).encode(), "application/json", listnr.API
    with pytest.raises(listnr.CatalogueError, match="dynamic_stream"):
        await resolver.resolve("listnr:opaque")


async def test_listnr_hls_master_child_minimal_audio_and_protected_failure():
    base = "https://sa47.scastream.com.au/live/example/playlist.m3u8"
    frame = bytes([255, 241, 76, 128, 4, 31, 252]) + bytes(25)
    responses = [
        (b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=130000,CODECS="mp4a.40.2"\nchild.m3u8\n', "application/vnd.apple.mpegurl", base),
        (b"#EXTM3U\n#EXTINF:5,\nsegment.aac\n", "application/vnd.apple.mpegurl", base),
        (frame * 2, "audio/aac", base),
    ]
    request = AsyncMock(side_effect=responses)
    result = await listnr.LiSTNR(request).validate({"url": base})
    assert result["url"] == base
    assert result["codec"] == "mp4a.40.2"
    assert result["bitrate"] == 130000
    assert request.call_args.kwargs == {"limit": 8192}
    request = AsyncMock(return_value=(b'#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="protected"', "application/vnd.apple.mpegurl", base))
    with pytest.raises(listnr.CatalogueError, match="unsupported_protected_stream"):
        await listnr.LiSTNR(request).validate({"url": base})
    assert not listnr.aac_frames(b"<html>not audio</html>")


async def test_listnr_upstream_failure_is_distinct_and_hosts_fail_closed():
    request = AsyncMock(return_value=(b'{"errors":[{"message":"private upstream detail"}]}', "application/json", listnr.API))
    with pytest.raises(listnr.CatalogueError, match="^catalogue_unavailable$"):
        await listnr.LiSTNR(request).discover()
    for url in ["http://sa47.scastream.com.au/a", "https://example.com/audio", "https://sa47.scastream.com.au:1234/a"]:
        assert not listnr.media_url(url)


async def test_library_hygiene_disables_write_back_first_and_reruns_idempotently():
    values = {k: not v if type(v) is bool else ["old-playlist"] for k, v in media_hygiene.HYGIENE.items()}
    config = Obj(values=values, get_value=values.get)
    calls = []

    async def save(domain, changes, instance):
        calls.append(deepcopy(changes))
        values.update(changes)

    mass = Obj(
        providers=[Obj(domain="spotify", instance_id="shared")], config=Obj(get_provider_config=AsyncMock(return_value=config), save_provider_config=save)
    )
    assert (await media_hygiene.inspect_policy(mass, True))[0]["state"] == "connected"
    assert calls[0] == {"library_sync_back": False}
    assert values["library_sync_playlist_tracks"] == []
    count = len(calls)
    await media_hygiene.inspect_policy(mass, True)
    assert len(calls) == count


async def test_safe_cleanup_is_previewed_then_only_removes_ma_provider_mapping():
    config = Obj(get_value=lambda key: False)
    spotify = Obj(provider_instance="shared", item_id="spotify-track", in_library=True)
    other = Obj(provider_instance="files", item_id="local-track", in_library=True)
    tracks = Obj(library_items=AsyncMock(return_value=[Obj(item_id="1", provider_mappings=[spotify, other])]), remove_provider_mapping=AsyncMock())
    mass = Obj(
        providers=[Obj(domain="spotify", instance_id="shared")], config=Obj(get_provider_config=AsyncMock(return_value=config)), music=Obj(tracks=tracks)
    )
    result = await media_hygiene.cleanup(mass)
    assert result["imported_mappings"] == 1 and result["removed"] == 0
    tracks.remove_provider_mapping.assert_not_awaited()
    await media_hygiene.cleanup(mass, True)
    tracks.remove_provider_mapping.assert_awaited_once_with("1", "shared", "spotify-track")
    config.get_value = lambda key: True
    with pytest.raises(ValueError, match="safe Spotify"):
        await media_hygiene.cleanup(mass, True)


async def test_discovery_allocator_handoff_stays_reserved_and_expires_safely(tmp_path):
    now = [100]
    observe = AsyncMock(return_value={})
    engine = SpotifyLeases(tmp_path / "leases.json", observe, AsyncMock(return_value="idle"), AsyncMock(), clock=lambda: now[0])
    providers = [{"id": name, "domain": "spotify", "name": name, "available": True} for name in ["House", "House #2", "Grant", "Renae"]]
    one = await engine.reserve(providers, "discovery:a", "pending-a", "House")
    two = await engine.reserve(providers, "discovery:b", "pending-b", "House")
    assert [one["provider"], two["provider"]] == ["House", "House #2"]
    adopted = await engine.adopt(one["token"], "a", "native-a")
    assert adopted["provider"] == "House" and adopted["token"] == one["token"]
    now[0] += 31
    with pytest.raises(AccountsBusy, match="expired"):
        await engine.adopt(two["token"], "b", "native-b")
    await engine.recover(providers)
    assert not engine.leases


async def test_catalogue_reconciliation_preserves_selection_and_outage(tmp_path, monkeypatch):
    from homestarter.household import HouseholdStore

    store = HouseholdStore(str(tmp_path))
    row = listnr.normalize({"id": "opaque", "slug": "rain", "name": "Rain", "stationType": "Music"})
    resolver = Obj(
        discover=AsyncMock(return_value=[row]),
        resolve=AsyncMock(return_value={"url": "https://sa47.scastream.com.au/live/example/playlist.m3u8"}),
        validate=AsyncMock(
            return_value={
                "url": "https://sa47.scastream.com.au/live/example/playlist.m3u8",
                "format": "hls",
                "codec": "aac",
                "bitrate": 130000,
                "resolved_at": 100,
                "validated_at": 100,
            }
        ),
    )
    runtime = Obj(
        connection=lambda: {"server_id": "first"},
        snapshot=AsyncMock(return_value={"providers": []}),
        command=AsyncMock(return_value=[]),
        endpoint=AsyncMock(return_value="ma"),
        control=AsyncMock(return_value={"state": "connected", "uri": "library://radio/1"}),
    )
    media = MediaCatalogue(runtime, Obj(config=AsyncMock(return_value={})), store, resolver)
    result = await media.sync(force=True)
    assert result["ready"] == 1
    assert media.item("listnr:opaque")["uri"] == "library://radio/1"
    resolver.discover.side_effect = listnr.CatalogueError("upstream_unavailable")
    result = await media.sync(force=True)
    assert result["issue"] and result["selected"] == 1
    assert media.load()["items"]["listnr:opaque"]["uri"] == "library://radio/1"
    assert runtime.control.await_args.args[2] == "homestarter/radio_upsert"
    from homestarter import media_catalogue

    resolver.discover.side_effect = None
    resolver.nearby = AsyncMock(return_value={"listnr:opaque"})
    postal = AsyncMock(return_value="1234")
    monkeypatch.setattr(media_catalogue.postal_region, "postcode", postal)
    monkeypatch.setattr(
        media_catalogue.household_services, "load", lambda *args: {"region": {"name": "Example", "country_code": "AU", "search_terms": ["Example"]}}
    )
    await media.sync(force=True)
    postal.assert_not_awaited()
    resolver.nearby.assert_not_awaited()
    await media.consent(True)
    await media.sync(force=True)
    resolver.nearby.assert_awaited_once_with("1234")
    assert media.view()["local_lookup_allowed"] is True
    await media.consent(False)
    await media.sync(force=True)
    resolver.nearby.assert_awaited_once()
    assert media.view()["local_lookup_state"] == "intentionally_skipped"
