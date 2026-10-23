"""Synthetic native membership changes, never real speaker or playback access."""

import asyncio
import time
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup
from test_shared_transport import shared as shared


@pytest.fixture
def native(shared, monkeypatch):
    runtime, music, house, saved = shared
    original_snapshot, original_control, original_command = music.snapshot, music.control, music.command
    for pid, raw in music.raw.items():
        raw.update(
            player_id=pid,
            type="player",
            available=True,
            can_group_with=[p for p in music.raw if p != pid],
            supported_features=["set_members", "pause", "volume_set", "play_media"],
            group_members=[],
            synced_to=None,
        )
    data = runtime.load(house, music.conn)
    data["leases"]["a"].update(user="admin", surface="panel")
    runtime.save(data)

    async def snapshot():
        value = await original_snapshot()
        for p in value["players"]:
            raw = music.raw[p["id"]]
            p.update(
                available=raw["available"],
                single=not raw["synced_to"] and not (set(raw["group_members"]) - {p["id"]}),
                group_members=raw["group_members"],
                synced_to=raw["synced_to"],
                can_group_with=raw["can_group_with"],
                features=raw["supported_features"],
            )
        return value

    async def command(endpoint, connection, name, **args):
        if name == "player_queues/get_active_queue" and music.raw[args["player_id"]].get("synced_to"):
            return deepcopy(music.queues[music.raw[args["player_id"]]["synced_to"]])
        return await original_command(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        if name == "players/cmd/set_members":
            music.calls.append((name, args))
            leader = args["target_player"]
            members = ({leader} | set(music.raw[leader]["group_members"]) | set(args["player_ids_to_add"])) - set(args["player_ids_to_remove"])
            music.raw[leader]["group_members"] = sorted(members) if len(members) > 1 else []
            for pid in args["player_ids_to_add"]:
                music.raw[pid].update(
                    synced_to=leader, active_source=leader, playback_state=music.raw[leader]["playback_state"], current_media=music.raw[leader]["current_media"]
                )
            for pid in args["player_ids_to_remove"]:
                music.raw[pid].update(synced_to=None, active_source=pid, playback_state="idle")
            return
        if name == "players/cmd/group_volume":
            music.calls.append((name, args))
            for pid in {args["player_id"], *music.raw[args["player_id"]]["group_members"]}:
                music.raw[pid]["volume_level"] = args["volume_level"]
            return
        await original_control(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "snapshot", snapshot)
    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    monkeypatch.setattr(music, "account_guard", AsyncMock(), raising=False)
    return shared


async def act(native, name, person="two", **extra):
    runtime, _, house, _ = native
    return await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": name, "player": "media_player.a", **extra})


async def prepare(native, selected=("a", "b"), person="two"):
    await act(native, "group_prepare", person, settings={"members": ["media_player." + pid for pid in selected]})
    data = native[0].load(native[2], native[1].conn)
    return data["group_changes"]["a"]["confirmation"]


async def confirm(native, person="two", replace=False):
    nonce = native[0].load(native[2], native[1].conn)["group_changes"]["a"]["confirmation"]
    await act(native, "group_confirm", person, confirmation=nonce, **({"value": "replace"} if replace else {}))


def occupy_child(native):
    runtime, music, house, _ = native
    data = runtime.load(house, music.conn)
    lease = deepcopy(data["leases"]["a"])
    lease.update(scope="person:two", session="fixture-second-session", queue_item_id="second", queue_items=["second"])
    data["leases"]["b"] = lease
    data["profiles"]["person:two"]["sleep"] = {"at": time.time() + 900, "player_id": "b", "session": lease["session"]}
    runtime.save(data)
    music.raw["b"].update(playback_state="playing", current_media={"queue_item_id": "second"}, elapsed_time=907, elapsed_time_last_updated=time.time())
    music.queues["b"].update(state="playing", current_item={"queue_item_id": "second", "duration": 3600, "media_item": music.book})


async def test_group_keeps_single_queue_owner_account_timer_and_personal_progress(native):
    runtime, music, house, _ = native
    before = runtime.load(house, music.conn)
    await prepare(native)
    assert not music.calls
    await confirm(native)
    data = runtime.load(house, music.conn)
    assert data["groups"]["a"]["members"] == ["a", "b"]
    assert data["leases"]["a"]["scope"] == "person:one"
    assert data["leases"]["a"]["account_lease"] == before["leases"]["a"]["account_lease"]
    assert data["profiles"]["person:one"]["sleep"] == before["profiles"]["person:one"]["sleep"]
    assert data["profiles"]["person:two"] == before["profiles"]["person:two"]
    assert set(data["leases"]) == {"a"}
    assert [n for n, _ in music.calls] == ["players/cmd/set_members"]


async def test_member_leave_dissolves_temporary_group_without_restart_or_new_play(native):
    await prepare(native)
    await confirm(native)
    await prepare(native, ("a",))
    await confirm(native)
    assert not native[0].load(native[2], native[1].conn)["groups"]
    assert native[1].raw["b"]["synced_to"] is None
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"] * 2


async def test_occupied_child_requires_separate_replacement_intent_and_saves_its_owner_progress(native):
    occupy_child(native)
    await prepare(native, person=None)
    with pytest.raises(ValueError, match="Explicitly confirm"):
        await confirm(native, person=None)
    assert not native[1].calls
    await confirm(native, person=None, replace=True)
    data = native[0].load(native[2], native[1].conn)
    assert "b" not in data["leases"]
    assert next(iter(data["profiles"]["person:two"]["books"].values()))["position"] == 907
    assert data["leases"]["a"]["scope"] == "person:one"
    assert [n for n, _ in native[1].calls] == ["player_queues/pause", "players/cmd/set_members"]


@pytest.mark.parametrize("case", ["incompatible", "unavailable", "unmanaged", "capability", "missing-leader"])
async def test_unsafe_combinations_never_send_native_commands(native, case):
    music = native[1]
    selected = ("a", "b")
    if case == "incompatible":
        music.raw["b"]["can_group_with"] = []
    if case == "unavailable":
        music.raw["b"]["available"] = False
    if case == "unmanaged":
        music.raw["b"]["playback_state"] = "playing"
    if case == "capability":
        music.raw["a"]["supported_features"] = []
    if case == "missing-leader":
        selected = ("b",)
    with pytest.raises(ValueError):
        await prepare(native, selected)
    assert not music.calls


@pytest.mark.parametrize("case", ["queue", "owner", "permission", "expired", "profile"])
async def test_stale_or_other_profile_confirmation_is_rejected(native, case):
    nonce = await prepare(native)
    runtime, music, house, saved = native
    actor = "two"
    if case == "queue":
        music.queues["a"]["current_item"]["queue_item_id"] = "external"
    if case == "permission":
        saved["choices"]["music"]["sources"] = ["media_player.a"]
    if case in {"owner", "expired"}:
        data = runtime.load(house, music.conn)
        if case == "owner":
            data["leases"]["a"]["scope"] = "house"
        else:
            data["group_changes"]["a"]["expires"] = 0
        runtime.save(data)
    if case == "profile":
        actor = None
    with pytest.raises(ValueError):
        await act(native, "group_confirm", actor, confirmation=nonce)
    assert not music.calls


async def test_lost_success_response_is_reconciled_without_replaying_membership(native, monkeypatch):
    await prepare(native)
    original = native[1].control

    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        raise MusicRuntimeError("Synthetic lost response")

    monkeypatch.setattr(native[1], "control", lost)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    with pytest.raises(ValueError, match="not confirmed"):
        await confirm(native)
    await act(native, "group_recheck")
    assert len(native[1].calls) == 1
    assert native[0].load(native[2], native[1].conn)["groups"]["a"]["members"] == ["a", "b"]


async def test_partial_membership_stays_blocked_and_timers_do_not_touch_uncertain_rooms(native, monkeypatch):
    await prepare(native)

    async def partial(*args, **kwargs):
        native[1].calls.append((args[2], kwargs))
        native[1].raw["a"]["group_members"] = ["a", "b"]
        raise MusicRuntimeError("Synthetic partial result")

    monkeypatch.setattr(native[1], "control", partial)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    with pytest.raises(ValueError, match="not confirmed"):
        await act(native, "group_recheck")
    data = native[0].load(native[2], native[1].conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    native[0].save(data)
    await native[0].tick()
    assert len(native[1].calls) == 1
    assert native[0].load(native[2], native[1].conn)["group_changes"]["a"]["phase"] == "uncertain"


async def test_verified_group_transport_and_expired_timer_target_only_the_leader_queue(native):
    await prepare(native)
    await confirm(native)
    runtime, music, house, _ = native
    view = await runtime.view("admin", "panel", "two")
    current = next(r for r in view["transport"] if r["player_id"] == "a")
    await act(native, "volume", session=current["revision"], value=30)
    assert music.calls[-1] == ("players/cmd/group_volume", {"player_id": "a", "volume_level": 30})
    data = runtime.load(house, music.conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    await runtime.tick()
    assert music.calls[-1] == ("player_queues/pause", {"queue_id": "a"})
    assert not any(n == "player_queues/play_media" for n, _ in music.calls)


async def test_concurrent_confirmations_execute_one_membership_command(native):
    nonce = await prepare(native)
    results = await asyncio.gather(act(native, "group_confirm", confirmation=nonce), act(native, "group_confirm", confirmation=nonce), return_exceptions=True)
    assert results[0] is None and isinstance(results[1], ValueError)
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"]


async def test_prepared_group_can_be_cancelled_without_commands_and_old_confirmation_is_invalid(native):
    nonce = await prepare(native)
    await act(native, "group_cancel")
    with pytest.raises(ValueError, match="fresh"):
        await act(native, "group_confirm", confirmation=nonce)
    assert not native[1].calls


async def test_other_profile_cannot_overwrite_a_pending_review(native):
    nonce = await prepare(native)
    with pytest.raises(ValueError, match="Another profile"):
        await prepare(native, person=None)
    assert native[0].load(native[2], native[1].conn)["group_changes"]["a"]["confirmation"] == nonce


async def test_reconnect_after_uncertain_join_can_be_reconciled_by_another_authorised_profile(native, monkeypatch):
    await prepare(native)
    original = native[1].control

    async def disconnect(*args, **kwargs):
        await original(*args, **kwargs)
        native[1].raw["b"]["available"] = False
        raise MusicRuntimeError("Synthetic disconnected member")

    monkeypatch.setattr(native[1], "control", disconnect)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    with pytest.raises(ValueError, match="not confirmed"):
        await act(native, "group_recheck", person=None)
    native[1].raw["b"]["available"] = True
    await act(native, "group_recheck", person=None)
    assert len(native[1].calls) == 1


async def test_leader_disconnect_after_native_change_keeps_owner_and_timer_pending(native, monkeypatch):
    await prepare(native)
    original = native[1].control

    async def disconnect(*args, **kwargs):
        await original(*args, **kwargs)
        native[1].raw["a"]["available"] = False

    monkeypatch.setattr(native[1], "control", disconnect)
    with pytest.raises(MusicRuntimeError):
        await confirm(native)
    data = native[0].load(native[2], native[1].conn)
    assert data["leases"]["a"]["scope"] == "person:one" and data["profiles"]["person:one"]["sleep"]
    assert data["group_changes"]["a"]["phase"] == "uncertain"


async def test_permission_revoked_while_pausing_displaced_room_prevents_native_group_change(native, monkeypatch):
    occupy_child(native)
    await prepare(native, person=None)
    original = native[1].control

    async def revoke(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "player_queues/pause":
            native[3]["choices"]["music"]["sources"] = ["media_player.a"]

    monkeypatch.setattr(native[1], "control", revoke)
    with pytest.raises(MusicRuntimeError, match="access changed"):
        await confirm(native, person=None, replace=True)
    assert [n for n, _ in native[1].calls] == ["player_queues/pause"]


async def test_native_queue_replaced_during_child_pause_does_not_group_new_content(native, monkeypatch):
    occupy_child(native)
    await prepare(native, person=None)
    original = native[1].control

    async def replace(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "player_queues/pause":
            native[1].queues["a"]["current_item"]["queue_item_id"] = "external"

    monkeypatch.setattr(native[1], "control", replace)
    with pytest.raises(MusicRuntimeError, match="leader session"):
        await confirm(native, person=None, replace=True)
    assert [n for n, _ in native[1].calls] == ["player_queues/pause"]


async def test_child_permission_does_not_expand_when_grouping_into_new_rooms(native):
    native[3]["members"]["two"] = {"kind": "child", "rooms": [], "devices": ["a", "b"]}
    await prepare(native)
    with pytest.raises(PermissionError, match="parent"):
        await confirm(native)
    assert not native[1].calls


async def test_group_source_protection_is_checked_before_pausing_any_occupied_room(native, monkeypatch):
    occupy_child(native)
    runtime, music, house, _ = native
    data = runtime.load(house, music.conn)
    data["leases"]["a"].update(native_session="fixture-native", kind="track")
    runtime.save(data)
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "homestarter/queue_context":
            return {"session": "fixture-native", "item": "old"}
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    music.account_guard.side_effect = MusicRuntimeError("Synthetic unavailable protection")
    await prepare(native, person=None)
    with pytest.raises(MusicRuntimeError, match="protection"):
        await confirm(native, person=None, replace=True)
    assert not music.calls


async def test_external_member_change_blocks_timer_and_transport_without_losing_owner_progress(native):
    await prepare(native)
    await confirm(native)
    runtime, music, house, _ = native
    data = runtime.load(house, music.conn)
    before = deepcopy(data["profiles"]["person:one"]["books"])
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    music.raw["a"]["group_members"] = ["a", "b", "external-room"]
    count = len(music.calls)
    await runtime.tick()
    data = runtime.load(house, music.conn)
    assert len(music.calls) == count and data["profiles"]["person:one"]["books"] == before
    assert data["profiles"]["person:one"]["sleep"] and data["leases"]["a"]["scope"] == "person:one"


async def test_paused_leader_is_never_resumed_by_grouping(native):
    native[1].raw["a"]["playback_state"] = "paused"
    native[1].queues["a"]["state"] = "paused"
    await prepare(native)
    await confirm(native)
    assert native[1].raw["a"]["playback_state"] == "paused"
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"]


async def test_unexpected_native_resume_is_not_silently_accepted_or_replayed(native, monkeypatch):
    native[1].raw["a"]["playback_state"] = "paused"
    native[1].queues["a"]["state"] = "paused"
    await prepare(native)
    original = native[1].control

    async def resume(*args, **kwargs):
        await original(*args, **kwargs)
        native[1].raw["a"]["playback_state"] = "playing"

    monkeypatch.setattr(native[1], "control", resume)
    with pytest.raises(MusicRuntimeError, match="not confirmed"):
        await confirm(native)
    assert [n for n, _ in native[1].calls] == ["players/cmd/set_members"]
    assert native[0].load(native[2], native[1].conn)["group_changes"]["a"]["phase"] == "uncertain"


async def test_lost_member_link_blocks_group_transport_and_timer_even_if_leader_list_is_stale(native):
    await prepare(native)
    await confirm(native)
    runtime, music, house, _ = native
    current = next(r for r in (await runtime.view("admin", "panel", "two"))["transport"] if r["player_id"] == "a")
    music.raw["b"]["synced_to"] = None
    count = len(music.calls)
    with pytest.raises(ValueError, match="group member"):
        await act(native, "pause", session=current["revision"])
    data = runtime.load(house, music.conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    await runtime.tick()
    assert len(music.calls) == count
    assert runtime.load(house, music.conn)["profiles"]["person:one"]["sleep"]


async def test_owner_progress_mapping_change_while_displacing_room_prevents_membership_command(native, monkeypatch):
    occupy_child(native)
    runtime, music, house, _ = native
    data = runtime.load(house, music.conn)
    data["leases"]["a"]["progress_route"] = {"fixture": "owner-one"}
    runtime.save(data)
    route = AsyncMock(return_value={"fixture": "owner-one"})
    monkeypatch.setattr(runtime, "book_route", route)
    await prepare(native, person=None)
    original = music.control

    async def change(*args, **kwargs):
        await original(*args, **kwargs)
        route.return_value = {"fixture": "different-owner"}

    monkeypatch.setattr(music, "control", change)
    with pytest.raises(MusicRuntimeError, match="progress source changed"):
        await confirm(native, person=None, replace=True)
    assert [n for n, _ in music.calls] == ["player_queues/pause"]
