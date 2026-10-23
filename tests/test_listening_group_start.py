"""Idle multi-speaker starts use fictional native devices and one leader command."""

import asyncio
import time
from copy import deepcopy

import pytest
from homestarter.listening import media_record
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup
from test_listening_groups import act, confirm
from test_listening_groups import native as native
from test_shared_transport import shared as shared


@pytest.fixture
def idle(native):
    runtime, music, house, _ = native
    data = runtime.load(house, music.conn)
    data["leases"].clear()
    for profile in data["profiles"].values():
        profile["sleep"] = None
    runtime.save(data)
    for pid in music.raw:
        music.raw[pid].update(playback_state="idle", current_media={})
        music.queues[pid].update(state="idle", current_item={"queue_item_id": "old"})
    music.book = {"uri": "fixture://radio/example", "media_type": "radio", "name": "Example radio"}
    item = media_record(music.book)
    runtime.catalog[item["id"]] = item
    return native, item


async def review(idle, **settings):
    native, item = idle
    await act(native, "group_prepare", "two", item=item["id"], settings={"members": ["media_player.a", "media_player.b"], **settings})


async def test_idle_start_has_one_native_group_one_queue_owner_history_and_timer(idle):
    native, item = idle
    runtime, music, house, _ = native
    await review(idle, sleep=900)
    assert not music.calls
    await confirm(native)
    data = runtime.load(house, music.conn)
    assert [n for n, _ in music.calls] == ["players/cmd/set_members", "player_queues/play_media"]
    assert music.calls[-1][1]["queue_id"] == "a"
    assert set(data["leases"]) == {"a"}
    assert data["groups"]["a"]["owner"] == "person:two"
    assert data["leases"]["a"]["scope"] == "person:two"
    assert data["profiles"]["person:two"]["recent"] == [item]
    assert not data["profiles"]["person:one"]["recent"]
    assert data["profiles"]["person:two"]["sleep"]["session"] == data["leases"]["a"]["session"]
    assert 895 < data["profiles"]["person:two"]["sleep"]["at"] - time.time() <= 900
    assert not data["group_changes"]


@pytest.mark.parametrize("phase", ["before_review", "before_confirm", "after_group"])
async def test_new_occupancy_never_gets_replaced(idle, monkeypatch, phase):
    native, _ = idle
    music = native[1]
    if phase == "before_review":
        music.raw["b"]["playback_state"] = "paused"
        with pytest.raises(ValueError):
            await review(idle)
    else:
        await review(idle)
        if phase == "before_confirm":
            music.queues["b"]["state"] = "buffering"
        else:
            original = music.control

            async def raced(*args, **kwargs):
                await original(*args, **kwargs)
                if args[2] == "players/cmd/set_members":
                    music.raw["b"]["playback_state"] = "playing"

            monkeypatch.setattr(music, "control", raced)
        with pytest.raises((ValueError, MusicRuntimeError)):
            await confirm(native)
    assert not any(n == "player_queues/play_media" for n, _ in music.calls)


async def test_partial_group_and_recheck_never_start_or_replay(idle, monkeypatch):
    native, _ = idle
    runtime, music, house, _ = native
    await review(idle)
    original = music.control

    async def partial(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members":
            music.raw["b"]["synced_to"] = None

    monkeypatch.setattr(music, "control", partial)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    for _ in range(2):
        with pytest.raises(ValueError):
            await act(native, "group_recheck")
    assert [n for n, _ in music.calls] == ["players/cmd/set_members"]
    assert runtime.load(house, music.conn)["group_changes"]["a"]["phase"] == "uncertain"


async def test_lost_play_ack_is_journalled_and_never_retried(idle, monkeypatch):
    native, _ = idle
    runtime, music, house, _ = native
    await review(idle)
    original = music.control

    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "player_queues/play_media":
            raise MusicRuntimeError("Synthetic response lost")

    monkeypatch.setattr(music, "control", lost)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    before = deepcopy(music.calls)
    with pytest.raises(ValueError):
        await act(native, "group_recheck")
    with pytest.raises(ValueError):
        await confirm(native)
    with pytest.raises(ValueError):
        await review(idle)
    assert music.calls == before
    data = runtime.load(house, music.conn)
    assert data["group_changes"]["a"]["phase"] == "uncertain"
    assert not data["leases"]
    assert not data["profiles"]["person:two"]["recent"]


async def test_cancel_before_confirm_sends_nothing(idle):
    native, _ = idle
    await review(idle)
    await act(native, "group_cancel")
    with pytest.raises(KeyError):
        await confirm(native)
    assert not native[1].calls


async def test_concurrent_confirms_send_one_start(idle):
    native, _ = idle
    await review(idle)
    results = await asyncio.gather(confirm(native), confirm(native), return_exceptions=True)
    assert sum(r is None for r in results) == 1
    assert [n for n, _ in native[1].calls].count("player_queues/play_media") == 1


@pytest.mark.parametrize("case", ["disconnect", "queue_change", "permission"])
async def test_changes_after_group_prevent_start(idle, monkeypatch, case):
    native, _ = idle
    runtime, music, _, saved = native
    await review(idle)
    original = music.control

    async def changed(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members":
            if case == "disconnect":
                music.raw["b"]["available"] = False
            elif case == "queue_change":
                music.queues["a"]["current_item"] = {"queue_item_id": "someone-else"}
            else:
                saved["choices"]["music"]["sources"] = []

    monkeypatch.setattr(music, "control", changed)
    with pytest.raises((MusicRuntimeError, PermissionError)):
        await confirm(native)
    assert not any(n == "player_queues/play_media" for n, _ in music.calls)


async def test_spotify_missing_guard_fails_before_group(idle, monkeypatch):
    native, item = idle
    item["sources"] = ["fixture_house"]
    original_snapshot = native[1].snapshot

    async def snapshot():
        value = await original_snapshot()
        value["providers"] = [{"id": "fixture_house", "domain": "spotify", "name": "House", "available": True}]
        return value

    monkeypatch.setattr(native[1], "snapshot", snapshot)
    native[0].catalog[item["id"]] = item

    async def denied(*args):
        raise MusicRuntimeError("Synthetic unavailable pin")

    monkeypatch.setattr(native[1], "account_guard", denied)
    with pytest.raises(MusicRuntimeError):
        await review(idle)
    assert not native[1].calls


async def test_cancelled_native_group_operation_is_uncertain_and_not_replayed(idle, monkeypatch):
    native, _ = idle
    await review(idle)
    original = native[1].control

    async def cancelled(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members":
            raise asyncio.CancelledError()

    monkeypatch.setattr(native[1], "control", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await confirm(native)
    with pytest.raises(ValueError):
        await act(native, "group_recheck")
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"]


async def test_uncertain_membership_never_proceeds_to_start_even_if_native_join_succeeded(idle, monkeypatch):
    native, _ = idle
    await review(idle)
    original = native[1].control

    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members":
            raise MusicRuntimeError("Synthetic lost join ack")

    monkeypatch.setattr(native[1], "control", lost)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    with pytest.raises(ValueError):
        await act(native, "group_recheck")
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"]


async def test_other_profile_cannot_confirm_or_start_review(idle):
    native, _ = idle
    await review(idle)
    nonce = native[0].load(native[2], native[1].conn)["group_changes"]["a"]["confirmation"]
    with pytest.raises(ValueError):
        await act(native, "group_confirm", person="one", confirmation=nonce)
    assert not native[1].calls


async def test_spotify_uses_only_leader_guarded_start_and_native_account_session(idle, monkeypatch):
    native, item = idle
    runtime, music, house, _ = native
    item.update(sources=["fixture_house"], kind="track", uri="fixture_house://track/example")
    runtime.catalog[item["id"]] = item
    original_snapshot, original_command, original_control = music.snapshot, music.command, music.control

    async def snapshot():
        value = await original_snapshot()
        value["providers"] = [{"id": "fixture_house", "domain": "spotify", "name": "House", "available": True}]
        return value

    async def command(endpoint, connection, name, **args):
        if name == "homestarter/queue_context":
            return {"item": music.queues["a"]["current_item"]["queue_item_id"], "session": "fixture-native-account-lease", "logical_session": "fixture-logical"}
        return await original_command(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        if name == "homestarter/play":
            assert args["queue_id"] == "a" and args["listener"] == "Example two"
            music.calls.append((name, args))
            music.queues["a"].update(state="playing", current_item={"queue_item_id": "spotify-new", "media_item": music.book})
            music.raw["a"].update(playback_state="playing", current_media={"queue_item_id": "spotify-new"})
            return
        await original_control(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "snapshot", snapshot)
    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    await review(idle)
    await confirm(native)
    data = runtime.load(house, music.conn)
    assert [n for n, _ in music.calls] == ["players/cmd/set_members", "homestarter/play"]
    assert set(data["leases"]) == {"a"}
    assert data["leases"]["a"]["native_session"] == "fixture-native-account-lease"
    assert music.account_guard.await_count >= 2


async def test_same_book_start_uses_only_selected_person_progress(idle):
    native, _ = idle
    runtime, music, house, _ = native
    music.book = {"uri": "fixture://book/one", "media_type": "audiobook", "name": "Example book"}
    record = media_record(music.book)
    runtime.catalog[record["id"]] = record
    await act(native, "group_prepare", "two", item=record["id"], settings={"members": ["media_player.a", "media_player.b"]})
    await confirm(native)
    data = runtime.load(house, music.conn)
    assert data["leases"]["a"]["scope"] == "person:two"
    assert data["leases"]["a"]["awaiting_position"] == 907
    assert [args for n, args in music.calls if n == "player_queues/seek"] == [{"queue_id": "a", "position": 907}]
    assert not data["profiles"]["person:one"]["books"]
    assert [n for n, _ in music.calls].count("player_queues/play_media") == 1


async def test_selection_changed_after_review_never_groups(idle):
    native, item = idle
    await review(idle)
    native[0].catalog[item["id"]] = {**item, "uri": "fixture://other/new-selection"}
    with pytest.raises(ValueError, match="content or progress source changed"):
        await confirm(native)
    assert not native[1].calls


async def test_confirmed_start_member_disconnect_recovers_by_reads_only(idle, monkeypatch):
    native, _ = idle
    runtime, music, house, _ = native
    await review(idle, sleep=900)
    original = runtime.play

    async def disconnected(*args, **kwargs):
        await original(*args, **kwargs)
        music.raw["b"]["available"] = False

    monkeypatch.setattr(runtime, "play", disconnected)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    before = deepcopy(music.calls)
    lease = deepcopy(runtime.load(house, music.conn)["leases"]["a"])
    music.raw["b"]["available"] = True
    await act(native, "group_recheck")
    data = runtime.load(house, music.conn)
    assert data["groups"]["a"]["members"] == ["a", "b"]
    assert music.calls == before
    assert data["leases"]["a"] == lease
    assert data["profiles"]["person:two"]["sleep"]["session"] == lease["session"]
