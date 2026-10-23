"""Isolated transfer adapter contract; no native adapter is installed by these tests."""

import asyncio
import time
from copy import deepcopy

import pytest
from homestarter.listening_transfer import fingerprint
from homestarter.music_runtime import MusicRuntimeError, digest
from test_listening import setup as setup
from test_listening_sessions import queued as queued


@pytest.fixture
def handoff(queued, monkeypatch):
    base, snapshot, _, source_rows = queued
    runtime, music, house, _ = base
    rows = {"a": source_rows, "b": []}
    users = {"a": "native-owner", "b": "native-former-listener"}
    mode = {"value": "success"}
    for pid, raw in music.raw.items():
        raw.update(player_id=pid, type="player", available=True, active_source=pid, group_members=[], elapsed_time=42)
    music.queues["a"].update(autoplay_enabled=False, is_dynamic=False, repeat_mode="off", elapsed_time=42, resume_pos=42)
    music.queues["b"].update(active=False, state="idle", current_item=None, shuffle_enabled=False, repeat_mode="off", autoplay_enabled=False, is_dynamic=False)
    data = runtime.load(house, music.conn)
    data["leases"]["a"].update(user="admin", surface="panel")
    data["profiles"]["person:one"].update(sleep={"at": time.time() + 3600, "player_id": "a", "session": "fixture-session"}, books={"one": {"position": 123}})
    runtime.profile(data, "two")["books"] = {"one": {"position": 907}}
    runtime.save(data)
    original = music.command

    def native(pid):
        value = {"protocol": 1, "player": deepcopy(music.raw[pid]), "queue": deepcopy(music.queues[pid]), "rows": deepcopy(rows[pid]), "userid": users[pid]}
        value["revision"] = digest([value["player"], value["queue"], value["rows"], users[pid]])
        return value

    async def command(endpoint, connection, name, **args):
        if name == "homestarter/transfer_status":
            return {"protocol": 1, "version": "2.10.7", "pinned": mode["value"] != "no_adapter", "native_user_preserved": True}
        if name == "homestarter/transfer_snapshot":
            return native(args["queue_id"])
        if name == "player_queues/items":
            return deepcopy(rows[args["queue_id"]])
        return await original(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        if name == "player_queues/pause":
            pid = args["queue_id"]
            music.calls.append((name, deepcopy(args)))
            music.raw[pid].update(playback_state="paused", elapsed_time_last_updated=time.time())
            music.queues[pid].update(state="paused", elapsed_time=42, elapsed_time_last_updated=time.time())
            return
        assert name == "homestarter/transfer"
        music.calls.append((name, deepcopy(args)))
        assert args["source_revision"] == native("a")["revision"]
        assert args["target_revision"] == native("b")["revision"]
        if mode["value"] == "timeout_before":
            raise MusicRuntimeError("Uncertain request")
        target = deepcopy(music.queues["a"])
        target.update(queue_id="b", active=args["auto_play"], state="playing" if args["auto_play"] else "idle")
        music.queues["b"] = target
        rows["b"] = deepcopy(rows["a"])
        rows["a"].clear()
        users["b"] = users["a"]
        music.queues["a"].update(state="idle", active=False, current_item=None)
        music.raw["a"].update(playback_state="idle", current_media={})
        music.raw["b"].update(playback_state=target["state"], current_media={"queue_item_id": "old"} if args["auto_play"] else {})
        if mode["value"] == "position_lost":
            music.raw["b"]["elapsed_time"] = 0
        if mode["value"] == "wrong_user":
            users["b"] = "native-former-listener"
        if mode["value"] == "partial":
            rows["b"].clear()
        if mode["value"] in {"source_disconnect", "target_disconnect"}:
            music.raw["a" if mode["value"] == "source_disconnect" else "b"]["available"] = False
        if mode["value"] == "cancel_after":
            raise asyncio.CancelledError
        if mode["value"] == "timeout_after":
            raise MusicRuntimeError("Reply lost after native move")

    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    return base, snapshot, rows, users, mode


async def action(handoff, name, person="one", **extra):
    runtime, _, house, _ = handoff[0]
    return await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": name, "player": "media_player.a", **extra})


def saved(handoff):
    runtime, music, house, _ = handoff[0]
    return runtime.load(house, music.conn)


async def prepare(handoff):
    await action(handoff, "transfer_prepare", target="media_player.b")
    return saved(handoff)["profiles"]["person:one"]["transfer_plan"]["confirmation"]


async def test_confirm_preserves_queue_native_user_owner_timer_and_other_profile_progress(handoff):
    runtime, music, _, _ = handoff[0]
    before = saved(handoff)
    timer = deepcopy(before["profiles"]["person:one"]["sleep"])
    token = await prepare(handoff)
    assert music.calls == []
    await action(handoff, "transfer_confirm", confirmation=token)
    data = saved(handoff)
    assert list(data["leases"]) == ["b"]
    assert data["leases"]["b"]["session"] == "fixture-session" and data["leases"]["b"]["scope"] == "person:one"
    assert data["profiles"]["person:one"]["sleep"] == {**timer, "player_id": "b"}
    assert data["profiles"]["person:two"] == before["profiles"]["person:two"]
    assert data["profiles"]["person:one"]["books"] == before["profiles"]["person:one"]["books"]
    assert handoff[3]["b"] == "native-owner" and len(music.calls) == 1
    assert data["handoffs"] == {}
    with pytest.raises((ValueError, PermissionError)):
        await action(handoff, "transfer_confirm", confirmation=token)
    assert len(music.calls) == 1
    assert runtime.transfers is not None


async def test_destination_occupation_between_review_and_confirm_blocks_transport(handoff):
    token = await prepare(handoff)
    music = handoff[0][1]
    music.raw["b"]["playback_state"] = "paused"
    with pytest.raises(ValueError, match="saved queue"):
        await action(handoff, "transfer_confirm", confirmation=token)
    assert music.calls == []


@pytest.mark.parametrize("change", ["source", "target", "queue", "expires"])
async def test_disconnect_concurrent_queue_or_expired_confirmation_rejects_before_command(handoff, change):
    token = await prepare(handoff)
    runtime, music, _, _ = handoff[0]
    if change in {"source", "target"}:
        music.raw["a" if change == "source" else "b"]["available"] = False
    elif change == "queue":
        handoff[2]["a"].append({**deepcopy(handoff[2]["a"][0]), "queue_item_id": "concurrent"})
    else:
        data = saved(handoff)
        data["profiles"]["person:one"]["transfer_plan"]["expires"] = 0
        runtime.save(data)
    with pytest.raises(ValueError):
        await action(handoff, "transfer_confirm", confirmation=token)
    assert music.calls == []


@pytest.mark.parametrize("mode", ["timeout_before", "partial", "wrong_user", "position_lost", "source_disconnect", "target_disconnect"])
async def test_uncertain_partial_or_disconnect_freezes_pair_and_never_replays(handoff, mode):
    token = await prepare(handoff)
    handoff[4]["value"] = mode
    await action(handoff, "transfer_confirm", confirmation=token)
    assert saved(handoff)["handoffs"]
    await action(handoff, "transfer_recheck")
    assert len(handoff[0][1].calls) == 1
    with pytest.raises(ValueError, match="not confirmed"):
        await action(handoff, "volume", value=10)
    assert len(handoff[0][1].calls) == 1


async def test_lost_reply_after_complete_move_is_reconciled_without_retry(handoff):
    token = await prepare(handoff)
    handoff[4]["value"] = "timeout_after"
    await action(handoff, "transfer_confirm", confirmation=token)
    assert not saved(handoff)["handoffs"] and "b" in saved(handoff)["leases"]
    assert len(handoff[0][1].calls) == 1


async def test_disconnected_target_reconciles_when_available_again(handoff):
    token = await prepare(handoff)
    handoff[4]["value"] = "target_disconnect"
    await action(handoff, "transfer_confirm", confirmation=token)
    handoff[0][1].raw["b"]["available"] = True
    await action(handoff, "transfer_recheck")
    assert not saved(handoff)["handoffs"] and "b" in saved(handoff)["leases"]
    assert len(handoff[0][1].calls) == 1


async def test_paused_queue_moves_quietly_and_keeps_a_verified_staged_owner(handoff):
    runtime, music, _, _ = handoff[0]
    music.raw["a"]["playback_state"] = music.queues["a"]["state"] = "paused"
    token = await prepare(handoff)
    await action(handoff, "transfer_confirm", confirmation=token)
    data = saved(handoff)
    assert music.calls[0][1]["auto_play"] is False
    assert data["leases"]["b"]["transfer_staged"]["current"] == "old"
    await runtime.sample(await music.endpoint(), music.conn, data, "b", data["leases"]["b"])
    assert "b" in data["leases"]
    assert music.queues["b"]["resume_pos"] == 42


@pytest.mark.parametrize("kind", ["audiobook", "podcast_episode", "spotify", "scoped", "no_adapter"])
async def test_unsupported_progress_account_or_missing_adapter_stays_unavailable(handoff, kind):
    runtime = handoff[0][0]
    data = saved(handoff)
    if kind in {"audiobook", "podcast_episode"}:
        data["leases"]["a"]["kind"] = kind
    elif kind == "spotify":
        data["leases"]["a"]["native_session"] = "protected"
    elif kind == "scoped":
        data["leases"]["a"]["item"]["catalogue_access"] = "scoped"
    else:
        handoff[4]["value"] = "no_adapter"
    runtime.save(data)
    before = deepcopy(data["profiles"])
    with pytest.raises(ValueError, match="unavailable|not available|not supported"):
        await prepare(handoff)
    assert saved(handoff)["profiles"] == before and handoff[0][1].calls == []


async def test_another_profile_cannot_confirm_or_race_the_owners_move(handoff):
    token = await prepare(handoff)
    result = await asyncio.gather(
        action(handoff, "transfer_confirm", confirmation=token), action(handoff, "transfer_confirm", person="two", confirmation=token), return_exceptions=True
    )
    assert result[0] is None and isinstance(result[1], (ValueError, PermissionError))
    assert len(handoff[0][1].calls) == 1


def test_revision_detects_native_user_change(handoff):
    value = {"player": {}, "queue": {}, "rows": [], "userid": "one", "native_revision": "same"}
    assert fingerprint(value) != fingerprint({**value, "userid": "two"})


async def test_concurrent_other_profile_play_cannot_replace_the_completed_transfer(handoff):
    token = await prepare(handoff)
    runtime, music, house, _ = handoff[0]
    item_id = saved(handoff)["leases"]["a"]["item"]["id"]
    result = await asyncio.gather(
        action(handoff, "transfer_confirm", confirmation=token),
        runtime.action("admin", "panel", "two", {"epoch": house["epoch"], "action": "play_item", "player": "media_player.b", "item": item_id}),
        return_exceptions=True,
    )
    assert result[0] is None and isinstance(result[1], (ValueError, MusicRuntimeError))
    assert saved(handoff)["leases"]["b"]["scope"] == "person:one" and len(music.calls) == 1


async def test_timer_waits_during_uncertainty_then_follows_the_verified_room(handoff):
    token = await prepare(handoff)
    runtime, music, _, _ = handoff[0]
    handoff[4]["value"] = "target_disconnect"
    await action(handoff, "transfer_confirm", confirmation=token)
    data = saved(handoff)
    data["profiles"]["person:one"]["sleep"]["at"] = time.time() - 1
    runtime.save(data)
    await runtime.tick()
    assert len(music.calls) == 1 and saved(handoff)["profiles"]["person:one"]["sleep"]
    music.raw["b"]["available"] = True
    await runtime.tick()
    assert not saved(handoff)["handoffs"] and saved(handoff)["profiles"]["person:one"].get("sleep") is None
    assert music.calls[-1] == ("player_queues/pause", {"queue_id": "b"})


async def test_cancelled_response_survives_service_recreation_and_reconciles_without_replay(handoff):
    from homestarter.listening import ListeningRuntime

    token = await prepare(handoff)
    runtime, music, _, _ = handoff[0]
    handoff[4]["value"] = "cancel_after"
    with pytest.raises(asyncio.CancelledError):
        await action(handoff, "transfer_confirm", confirmation=token)
    assert saved(handoff)["handoffs"]
    resumed = ListeningRuntime(music, runtime.core, runtime.store)
    resumed.mapping_cache = runtime.mapping_cache
    await resumed.tick()
    assert not saved(handoff)["handoffs"] and saved(handoff)["leases"]["b"]["scope"] == "person:one"
    assert len(music.calls) == 1
