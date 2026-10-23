"""Profile-owned recipes and previews use synthetic catalogues, never playback."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter.listening import ListeningRuntime
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup
from test_stations import SPEC, track


@pytest.fixture
def catalogue(setup, monkeypatch):
    runtime, music, _, _ = setup
    snapshot = {
        "connected": True,
        "providers": [{"id": "fixture_catalogue", "domain": "fixture", "available": True, "features": ["search", "library_tracks"]}],
        "players": [],
    }
    # Preserve the original player map without real registry/network calls.
    snapshot["players"] = [{"id": p, "name": "Example " + p, "available": True, "single": True, "state": "idle"} for p in ("a", "b")]
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.10.7"}))
    runtime.core.config = AsyncMock(return_value={"time_zone": "Australia/Sydney"})
    rows = [track(str(i)) for i in range(30)]
    searches = []
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "auth/users":
            return [
                {"user_id": "native-" + p, "display_name": n, "provider_filter": [v["id"] for v in snapshot["providers"]]}
                for p, n in (("one", "Example one"), ("two", "Example two"), ("house", "House"))
            ]
        if name == "music/search":
            searches.append(deepcopy(args))
            return {"tracks": deepcopy(rows)}
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    return setup, rows, searches


async def action(catalogue, operation, person="one", **extra):
    runtime, _, house, _ = catalogue[0]
    return await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": operation, **extra})


async def saved(catalogue):
    await action(catalogue, "station_save", settings=SPEC)
    value = await catalogue[0][0].view("admin", "panel", "one")
    return value["stations"]["recipes"][0]["id"]


async def test_saved_recipe_survives_restart_regenerates_and_remains_profile_scoped(catalogue):
    setup, _, searches = catalogue
    runtime, music, house, _ = setup
    identifier = await saved(catalogue)
    await action(catalogue, "station_preview", station=identifier)
    first = runtime.load(house, music.conn)
    original_keys = {r["key"] for r in first["profiles"]["person:one"]["station_history"]}
    restarted = ListeningRuntime(music, runtime.core, runtime.store)
    restarted.mapping_cache = runtime.mapping_cache
    await restarted.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "station_preview", "station": identifier})
    result = restarted.load(house, music.conn)["profiles"]["person:one"]
    assert len(result["station_history"]) == 10
    assert not original_keys & {r["key"] for r in result["station_history"][5:]}
    assert set(result["station_recipes"][identifier]) == {"recipe", "runs"}
    assert result["station_recipes"][identifier]["runs"] == 2
    other = await restarted.view("admin", "panel", "two")
    assert other["stations"]["recipes"] == []
    with pytest.raises(ValueError, match="profile's saved stations"):
        await action(catalogue, "station_preview", "two", station=identifier)
    assert all(r["providers"] == ["fixture_catalogue"] and r["media_types"] == ["track"] for r in searches)
    assert not music.calls


async def test_feedback_persists_and_session_refinement_does_not_become_profile_tuning(catalogue):
    runtime, music, house, _ = catalogue[0]
    identifier = await saved(catalogue)
    await action(catalogue, "station_preview", station=identifier)
    value = await runtime.view("admin", "panel", "one")
    preview = value["stations"]["preview"]
    await action(catalogue, "station_feedback", preview=preview["id"], entry=preview["items"][0]["entry"], value="never", settings={"scope": "station"})
    await action(catalogue, "station_feedback", preview=preview["id"], entry=preview["items"][1]["entry"], value="more", settings={"scope": "session"})
    await action(catalogue, "station_refine", station=identifier, preview=preview["id"])
    refined = await runtime.view("admin", "panel", "one")
    assert refined["stations"]["preview"]["id"] == preview["id"]
    persisted = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert persisted["station_feedback"]["station:" + identifier][0]["never"]
    assert "profile" not in persisted["station_feedback"]
    with pytest.raises(ValueError, match="fresh station preview"):
        await action(
            catalogue, "station_feedback", "two", preview=preview["id"], entry=preview["items"][0]["entry"], value="never", settings={"scope": "profile"}
        )
    assert not music.calls


async def test_provider_failure_preserves_recipe_history_and_hides_upstream_detail(catalogue, monkeypatch):
    runtime, music, house, _ = catalogue[0]
    identifier = await saved(catalogue)
    await action(catalogue, "station_preview", station=identifier)
    original = deepcopy(runtime.load(house, music.conn)["profiles"]["person:one"])
    native = music.command

    async def fail(endpoint, connection, name, **args):
        if name == "music/search":
            raise MusicRuntimeError("Synthetic private upstream detail")
        return await native(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", fail)
    await action(catalogue, "station_preview", station=identifier)
    result = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert result["station_history"] == original["station_history"] and result["station_recipes"] == original["station_recipes"]
    public = await runtime.view("admin", "panel", "one")
    assert public["stations"]["preview"]["state"] == "provider_unavailable"
    assert "private upstream detail" not in str(public)
    assert "fixture_catalogue://" not in str(public["stations"])
    assert not music.calls


async def test_spotify_only_sources_and_children_cannot_bypass_guard_or_expand_catalogue(catalogue, monkeypatch):
    runtime, music, _, saved_state = catalogue[0]
    identifier = await saved(catalogue)
    snapshot = await music.snapshot()
    snapshot["providers"] = [
        {"id": "fixture_" + n, "domain": "spotify", "name": n, "available": True, "features": ["search", "similar_tracks"]}
        for n in ("Grant", "Renae", "House", "House #2")
    ]
    monkeypatch.setattr(music, "account_guard", AsyncMock(side_effect=MusicRuntimeError("Protection unavailable")), raising=False)
    with pytest.raises(ValueError, match="no personal-library fallback"):
        await action(catalogue, "station_preview", station=identifier)
    saved_state["members"]["two"] = {"kind": "child", "rooms": [], "devices": []}
    with pytest.raises(PermissionError, match="parent configures"):
        await action(catalogue, "station_save", "two", settings=SPEC)
    assert not catalogue[2] and not music.calls


async def test_keep_it_going_requires_pinned_session_source_capability_and_fresh_guard(setup, monkeypatch):
    runtime, music, house, _ = setup
    providers = [{"id": "fixture_spotify", "domain": "spotify", "available": True, "features": ["similar_tracks"]}]
    lease = {"kind": "track", "native_session": "pinned"}
    guard = AsyncMock(return_value={"isolated": True})
    monkeypatch.setattr(music, "account_guard", guard, raising=False)
    monkeypatch.setattr(music, "command", AsyncMock(return_value={"sessions": [{"queue": "a", "provider": "fixture_spotify"}]}))
    assert await runtime.continuation_supported({}, music.conn, providers, "a", lease)
    providers[0]["features"] = []
    assert not await runtime.continuation_supported({}, music.conn, providers, "a", lease)
    providers[0]["features"] = ["similar_tracks"]
    guard.side_effect = MusicRuntimeError("Guard missing")
    assert not await runtime.continuation_supported({}, music.conn, providers, "a", lease)
    assert not await runtime.continuation_supported({}, music.conn, providers, "a", {"kind": "audiobook"})
    assert not music.calls


@pytest.mark.parametrize("missing", ["tracks", "enabled", "version"])
async def test_preview_requires_declared_track_search_and_reviewed_version(catalogue, monkeypatch, missing):
    runtime, music, _, _ = catalogue[0]
    identifier = await saved(catalogue)
    snapshot = await music.snapshot()
    if missing == "tracks":
        snapshot["providers"][0]["features"] = ["search"]
    elif missing == "enabled":
        snapshot["providers"][0]["enabled"] = False
    else:
        monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.11.0"}))
    with pytest.raises(ValueError, match="No supported station catalogue"):
        await action(catalogue, "station_preview", station=identifier)
    assert not catalogue[2] and not music.calls


async def test_feedback_reset_changes_only_explicit_scope_and_keeps_recipe_restrictions(catalogue):
    runtime, music, house, _ = catalogue[0]
    identifier = await saved(catalogue)
    await action(catalogue, "station_preview", station=identifier)
    preview = (await runtime.view("admin", "panel", "one"))["stations"]["preview"]
    for scope in ("profile", "station"):
        await action(catalogue, "station_feedback", preview=preview["id"], entry=preview["items"][0]["entry"], value="never", settings={"scope": scope})
    await action(catalogue, "station_reset", station=identifier, preview=preview["id"], settings={"scope": "station"})
    profile = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert "station:" + identifier not in profile["station_feedback"]
    assert profile["station_feedback"]["profile"][0]["never"]
    assert profile["station_recipes"][identifier]["recipe"]["artist_gap"] == SPEC["artist_gap"]
    assert not music.calls


@pytest.mark.parametrize("change_recipe", [False, True])
async def test_slow_catalogue_does_not_block_controls_or_overwrite_newer_profile_state(catalogue, monkeypatch, change_recipe):
    runtime, music, house, _ = catalogue[0]
    identifier = await saved(catalogue)
    entered, release = asyncio.Event(), asyncio.Event()
    original = music.command

    async def slow(endpoint, connection, name, **args):
        if name == "music/search":
            entered.set()
            await release.wait()
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", slow)
    pending = asyncio.create_task(action(catalogue, "station_preview", station=identifier))
    await asyncio.wait_for(entered.wait(), 2)
    try:
        await asyncio.wait_for(
            runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "volume", "player": "media_player.a", "value": 25}), 2
        )
        assert music.calls[-1] == ("players/cmd/volume_set", {"player_id": "a", "volume_level": 25})
        data = runtime.load(house, music.conn)
        data["profiles"]["person:one"]["books"] = {"preserved-book": {"position": 123}}
        runtime.save(data)
        if change_recipe:
            await action(catalogue, "station_save", station=identifier, settings={**SPEC, "name": "Changed while searching"})
    finally:
        release.set()
    if change_recipe:
        with pytest.raises(ValueError, match="newer choices were kept"):
            await pending
    else:
        await pending
    result = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert result["books"]["preserved-book"]["position"] == 123
    if change_recipe:
        assert result["station_recipes"][identifier]["recipe"]["name"] == "Changed while searching"
        assert not result.get("station_history")
