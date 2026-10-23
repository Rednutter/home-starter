"""Shared controls use fictional sessions; never connect to household devices."""

import asyncio
import time
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter.listening import media_record
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup


@pytest.fixture
def shared(setup, monkeypatch):
    runtime, music, house, _ = setup
    original_snapshot, original_control = music.snapshot, music.control

    async def snapshot():
        value = await original_snapshot()
        for player in value["players"]:
            player["features"] = ["pause", "volume_set", "next_previous", "play_media"]
        return value

    async def control(endpoint, connection, name, **args):
        await original_control(endpoint, connection, name, **args)
        if name == "players/cmd/volume_set":
            music.raw[args["player_id"]]["volume_level"] = args["volume_level"]
        if name == "player_queues/play":
            music.raw[args["queue_id"]]["playback_state"] = "playing"
            music.queues[args["queue_id"]]["state"] = "playing"

    monkeypatch.setattr(music, "snapshot", snapshot)
    monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.10.7"}))
    monkeypatch.setattr(music, "control", control)
    record = media_record(music.book)
    data = runtime.load(house, music.conn)
    for person in (None, "one", "two"):
        runtime.profile(data, person)
    data["profiles"]["person:two"]["books"][record["id"]] = {**record, "position": 907, "duration": 3600}
    data["profiles"]["person:one"]["sleep"] = {"at": time.time() + 900, "player_id": "a", "session": "fixture-shared"}
    data["leases"]["a"] = {
        "scope": "person:one",
        "session": "fixture-shared",
        "generation": 1,
        "kind": "audiobook",
        "item": record,
        "queue_item_id": "old",
        "queue_items": ["old"],
        "last_sample": 0,
        "account_lease": {"provider": "fixture_provider", "identity": "fixture-allocation"},
    }
    music.raw["a"].update(
        playback_state="playing", current_media={"queue_item_id": "old"}, elapsed_time=123, elapsed_time_last_updated=time.time(), volume_level=25
    )
    music.queues["a"].update(state="playing", current_item={"queue_item_id": "old", "name": "Example book", "duration": 3600, "media_item": music.book})
    runtime.save(data)
    return setup


async def token(shared, person="two"):
    view = await shared[0].view("admin", "panel", person)
    row = next(v for v in view["transport"] if v["player_id"] == "a")
    return row["revision"]


async def control(shared, name, revision, person="two", **extra):
    runtime, _, house, _ = shared
    await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": name, "player": "media_player.a", "session": revision, **extra})


@pytest.mark.parametrize("name", ["pause", "stop", "volume"])
async def test_cross_profile_controls_keep_owner_progress_account_queue_and_timer(shared, name):
    runtime, music, house, _ = shared
    revision = await token(shared)
    before = runtime.load(house, music.conn)
    queued = deepcopy(music.queues["a"]["current_item"])
    await control(shared, name, revision, **({"value": 35} if name == "volume" else {}))
    data = runtime.load(house, music.conn)
    assert data["leases"]["a"]["scope"] == "person:one"
    assert data["leases"]["a"]["session"] == "fixture-shared"
    assert data["leases"]["a"]["account_lease"] == before["leases"]["a"]["account_lease"]
    assert data["profiles"]["person:two"] == before["profiles"]["person:two"]
    assert data["profiles"]["person:one"]["sleep"] == before["profiles"]["person:one"]["sleep"]
    assert next(iter(data["profiles"]["person:one"]["books"].values()))["position"] == 123
    assert music.queues["a"]["current_item"] == queued
    assert all(n not in {"player_queues/play_media", "homestarter/play", "homestarter/media_play"} for n, _ in music.calls)


async def test_house_can_resume_person_without_taking_ownership(shared):
    await control(shared, "pause", await token(shared), person="two")
    await control(shared, "play", await token(shared, None), person=None)
    data = shared[0].load(shared[2], shared[1].conn)
    assert data["leases"]["a"]["scope"] == "person:one"
    assert data["profiles"]["house"]["books"] == {}


async def test_native_progress_route_is_always_the_owner(shared, monkeypatch):
    runtime, music, house, _ = shared
    data = runtime.load(house, music.conn)
    route = {"fixture_user": "owner-one", "provider": "fixture_books"}
    data["leases"]["a"]["progress_route"] = route
    runtime.save(data)
    check = AsyncMock(return_value=route)
    monkeypatch.setattr(runtime, "book_route", check)
    await control(shared, "pause", await token(shared))
    assert check.await_count >= 2
    assert all(call.args[2] == "person:one" for call in check.await_args_list)
    assert next(iter(runtime.load(house, music.conn)["profiles"]["person:two"]["books"].values()))["position"] == 907


async def test_two_profiles_using_same_revision_send_one_pause(shared):
    revision = await token(shared)
    result = await asyncio.gather(control(shared, "pause", revision), control(shared, "pause", revision, person=None), return_exceptions=True)
    assert result[0] is None and isinstance(result[1], ValueError)
    assert sum(n == "player_queues/pause" for n, _ in shared[1].calls) == 1


async def test_stale_revision_and_unmanaged_session_send_nothing(shared):
    runtime, music, house, _ = shared
    revision = await token(shared)
    with pytest.raises(ValueError, match="Refresh"):
        await control(shared, "pause", "old-revision")
    data = runtime.load(house, music.conn)
    data["leases"].clear()
    runtime.save(data)
    with pytest.raises(ValueError, match="outside a verified"):
        await control(shared, "volume", revision, value=25)
    assert not music.calls


@pytest.mark.parametrize("change", ["unavailable", "forbidden", "grouped"])
async def test_unavailable_unpermitted_and_group_changed_players_are_rejected(shared, change):
    revision = await token(shared)
    runtime, music, _, saved = shared
    if change == "unavailable":
        music.raw["a"]["available"] = False
    elif change == "forbidden":
        saved["choices"]["music"]["sources"] = []
    else:
        music.raw["a"]["group_members"] = ["a", "b"]
    with pytest.raises(ValueError):
        await control(shared, "stop", revision)
    assert not music.calls


async def test_native_queue_change_between_reads_is_rejected(shared, monkeypatch):
    revision = await token(shared)
    music = shared[1]
    original, reads = music.command, 0

    async def command(*args, **kwargs):
        nonlocal reads
        if args[2] == "players/get":
            reads += 1
            if reads == 3:
                music.raw["a"]["current_media"] = {"queue_item_id": "external"}
                music.queues["a"]["current_item"]["queue_item_id"] = "external"
        return await original(*args, **kwargs)

    monkeypatch.setattr(music, "command", command)
    with pytest.raises(ValueError):
        await control(shared, "pause", revision)
    assert not music.calls


async def test_lost_pause_response_is_reconciled_by_read_without_retry(shared, monkeypatch):
    revision = await token(shared)
    runtime, music, _, _ = shared
    original = music.control

    async def control_lost(*args, **kwargs):
        await original(*args, **kwargs)
        raise MusicRuntimeError("Fixture lost response")

    monkeypatch.setattr(music, "control", control_lost)
    with pytest.raises(MusicRuntimeError):
        await control(shared, "pause", revision)
    refreshed = await token(shared)
    assert refreshed != revision
    with pytest.raises(ValueError):
        await control(shared, "pause", revision)
    assert len(music.calls) == 1


async def test_unknown_unchanged_volume_outcome_blocks_replay_including_owner_legacy_path(shared, monkeypatch):
    revision = await token(shared)
    runtime, music, house, _ = shared
    original = music.control

    async def no_ack(*args, **kwargs):
        music.calls.append((args[2], kwargs))
        raise MusicRuntimeError("Fixture unavailable acknowledgement")

    monkeypatch.setattr(music, "control", no_ack)
    with pytest.raises(MusicRuntimeError):
        await control(shared, "volume", revision, value=40)
    for person in ("two", "one"):
        with pytest.raises(ValueError, match="not confirmed"):
            await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": "volume", "player": "media_player.a", "value": 40})
    assert len(music.calls) == 1
    monkeypatch.setattr(music, "control", original)
    music.raw["a"]["volume_level"] = 40
    assert await token(shared)


async def test_shared_controls_do_not_grant_queue_replacement_or_takeover(shared):
    runtime, music, house, _ = shared
    data = runtime.load(house, music.conn)
    item = data["leases"]["a"]["item"]
    runtime.catalog[item["id"]] = item
    with pytest.raises(ValueError, match="already in use"):
        await runtime.action("admin", "panel", "two", {"epoch": house["epoch"], "action": "play_item", "player": "media_player.a", "item": item["id"]})
    assert not music.calls


async def test_permissions_revoked_during_check_are_rechecked_before_command(shared, monkeypatch):
    revision = await token(shared)
    _, music, _, saved = shared
    original = music.command

    async def revoke(*args, **kwargs):
        if args[2] == "players/get":
            saved["choices"]["music"]["sources"] = []
        return await original(*args, **kwargs)

    monkeypatch.setattr(music, "command", revoke)
    with pytest.raises(ValueError, match="no longer permitted"):
        await control(shared, "pause", revision)
    assert not music.calls


async def test_spotify_resume_uses_existing_enforcement_without_allocating_for_actor(shared, monkeypatch):
    runtime, music, house, _ = shared
    data = runtime.load(house, music.conn)
    data["leases"]["a"].update(kind="track", native_session="fixture-native", logical_session="fixture-logical")
    runtime.save(data)
    music.raw["a"]["playback_state"] = "paused"
    music.queues["a"]["state"] = "paused"
    original = music.command

    async def command(*args, **kwargs):
        if args[2] == "homestarter/queue_context":
            return {"session": "fixture-native", "logical_session": "fixture-logical", "item": "old"}
        return await original(*args, **kwargs)

    guard = AsyncMock(side_effect=MusicRuntimeError("Fixture missing native pin"))
    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "account_guard", guard, raising=False)
    revision = await token(shared)
    with pytest.raises(MusicRuntimeError, match="native pin"):
        await control(shared, "play", revision)
    assert not music.calls
    guard.side_effect = None
    await control(shared, "play", revision)
    assert guard.await_count == 2
    assert music.calls == [("player_queues/play", {"queue_id": "a"})]
    assert runtime.load(house, music.conn)["leases"]["a"]["scope"] == "person:one"


@pytest.mark.parametrize("value", [True, -1, 101, float("nan"), float("inf"), "35"])
async def test_invalid_shared_volume_never_reaches_native_player(shared, value):
    with pytest.raises(ValueError, match="volume"):
        await control(shared, "volume", await token(shared), value=value)
    assert not shared[1].calls


async def test_missing_player_capability_has_a_friendly_unavailable_control(shared, monkeypatch):
    revision = await token(shared)
    original = shared[1].snapshot

    async def no_volume():
        data = await original()
        data["players"][0]["features"] = ["play_media"]
        return data

    monkeypatch.setattr(shared[1], "snapshot", no_volume)
    with pytest.raises(ValueError, match="unavailable"):
        await control(shared, "volume", revision, value=30)
    assert not shared[1].calls
