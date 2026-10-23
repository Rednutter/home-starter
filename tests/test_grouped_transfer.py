"""Fictional finite-queue group transfers. No live native bridge is installed."""

import asyncio
from copy import deepcopy

import pytest
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup
from test_listening_sessions import queued as queued
from test_listening_transfer import handoff as handoff


@pytest.fixture
def grouped(handoff, monkeypatch):
    base, snapshot, rows, users, mode = handoff
    runtime, music, house, saved = base
    for pid in ("c", "d"):
        music.raw[pid] = deepcopy(music.raw["b"])
        music.raw[pid]["player_id"] = pid
        music.raw[pid]["active_source"] = pid
        music.queues[pid] = deepcopy(music.queues["b"])
        music.queues[pid]["queue_id"] = pid
        rows[pid] = []
        users[pid] = "native-former-listener"
        saved["choices"]["music"]["sources"].append("media_player." + pid)
        runtime.mapping_cache[1].append({"entity_id": "media_player." + pid, "unique_id": pid, "platform": "music_assistant", "device_id": pid})
    for pid in music.raw:
        music.raw[pid].update(
            available=True,
            type="player",
            synced_to=None,
            can_group_with=[p for p in music.raw if p != pid],
            supported_features=["set_members", "play_media", "pause", "volume_set"],
        )
    music.raw["a"]["group_members"] = ["a", "c"]
    music.raw["c"].update(synced_to="a", active_source="a", playback_state="playing")
    data = runtime.load(house, music.conn)
    lease = data["leases"]["a"]
    data["groups"] = {"a": {"members": ["a", "c"], "owner": lease["scope"], "session": lease["session"], "generation": 1}}
    for profile in data["profiles"].values():
        for row in profile.get("books", {}).values():
            row.update(id="fixture-book", title="Example book", kind="audiobook", uri="fixture://book/one", duration=3600)
    runtime.save(data)
    original_command = music.command

    async def command(endpoint, connection, name, **args):
        if name == "auth/users":
            return [{"user_id": "native-owner", "enabled": True, "player_filter": mode.get("player_filter", list(music.raw))}]
        return await original_command(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    original_control = music.control

    async def get_snapshot():
        return {
            "connected": True,
            "providers": snapshot["providers"],
            "players": [
                {
                    "id": pid,
                    "name": "Example " + pid,
                    "available": raw["available"],
                    "single": not raw.get("synced_to") and not raw.get("group_members"),
                    "state": raw["playback_state"],
                    "features": raw["supported_features"],
                    "can_group_with": raw["can_group_with"],
                    "group_members": raw.get("group_members", []),
                    "synced_to": raw.get("synced_to"),
                }
                for pid, raw in music.raw.items()
            ],
        }

    async def control(endpoint, connection, name, **args):
        if name == "players/cmd/set_members":
            music.calls.append((name, deepcopy(args)))
            leader = args["target_player"]
            cohort = ({leader} | set(music.raw[leader].get("group_members", [])) | set(args["player_ids_to_add"])) - set(args["player_ids_to_remove"])
            music.raw[leader]["group_members"] = sorted(cohort) if len(cohort) > 1 else []
            for pid in args["player_ids_to_remove"]:
                music.raw[pid].update(synced_to=None, active_source=pid, playback_state="idle")
            for pid in args["player_ids_to_add"]:
                music.raw[pid].update(synced_to=leader, active_source=leader, playback_state=music.raw[leader]["playback_state"])
            return
        await original_control(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "snapshot", get_snapshot)
    monkeypatch.setattr(music, "control", control)
    return handoff


async def action(grouped, name, person="one", **extra):
    runtime, _, house, _ = grouped[0]
    await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": name, "player": "media_player.a", **extra})


def data(grouped):
    runtime, music, house, _ = grouped[0]
    return runtime.load(house, music.conn)


async def prepare(grouped):
    await action(grouped, "group_transfer_prepare", target="media_player.b", settings={"members": ["media_player.b", "media_player.d"]})
    return data(grouped)["group_handoffs"]["a"]["confirmation"]


async def confirm(grouped):
    await action(grouped, "group_transfer_confirm", confirmation=data(grouped)["group_handoffs"]["a"]["confirmation"])


async def test_grouped_move_keeps_queue_position_user_owner_history_and_timer(grouped):
    before = data(grouped)
    await prepare(grouped)
    assert not grouped[0][1].calls
    await confirm(grouped)
    after = data(grouped)
    assert [n for n, _ in grouped[0][1].calls] == ["players/cmd/set_members", "homestarter/transfer", "players/cmd/set_members"]
    assert set(after["leases"]) == {"b"}
    assert after["leases"]["b"]["session"] == before["leases"]["a"]["session"]
    assert after["groups"] == {"b": {"members": ["b", "d"], "owner": "person:one", "session": "fixture-session", "generation": 1}}
    assert after["profiles"]["person:one"]["sleep"] == {**before["profiles"]["person:one"]["sleep"], "player_id": "b"}
    assert after["profiles"]["person:one"]["books"] == before["profiles"]["person:one"]["books"]
    assert after["profiles"]["person:two"] == before["profiles"]["person:two"]
    assert grouped[3]["b"] == "native-owner"
    assert grouped[0][1].raw["b"]["elapsed_time"] == 42
    assert not after["group_handoffs"] and not after["handoffs"]


async def test_cancel_and_duplicate_confirmation_do_not_replay(grouped):
    nonce = await prepare(grouped)
    await action(grouped, "group_transfer_cancel")
    with pytest.raises(ValueError):
        await action(grouped, "group_transfer_confirm", confirmation=nonce)
    assert not grouped[0][1].calls
    await prepare(grouped)
    results = await asyncio.gather(confirm(grouped), confirm(grouped), return_exceptions=True)
    assert sum(r is None for r in results) == 1
    assert [n for n, _ in grouped[0][1].calls].count("homestarter/transfer") == 1


@pytest.mark.parametrize("case", ["occupied", "saved_queue", "spotify", "book", "no_adapter", "incompatible", "member_offline", "other_owner"])
async def test_unsupported_or_unsafe_move_sends_nothing(grouped, case):
    runtime, music, house, _ = grouped[0]
    if case == "occupied":
        music.raw["b"]["playback_state"] = "paused"
    elif case == "saved_queue":
        grouped[2]["d"].append(deepcopy(grouped[2]["a"][0]))
    elif case in {"spotify", "book"}:
        value = data(grouped)
        value["leases"]["a"]["native_session"] = "fixture-protected" if case == "spotify" else None
        if case == "book":
            value["leases"]["a"]["kind"] = "audiobook"
        runtime.save(value)
    elif case == "no_adapter":
        grouped[4]["value"] = "no_adapter"
    elif case == "incompatible":
        music.raw["d"]["can_group_with"] = []
    elif case == "member_offline":
        music.raw["c"]["available"] = False
    if case == "other_owner":
        with pytest.raises(PermissionError):
            await action(grouped, "group_transfer_prepare", person="two", target="media_player.b", settings={"members": ["media_player.b", "media_player.d"]})
    else:
        with pytest.raises((ValueError, PermissionError)):
            await prepare(grouped)
    assert not music.calls


@pytest.mark.parametrize("case", ["source_queue", "target_busy", "member_busy", "source_offline", "target_offline", "expires"])
async def test_review_changes_prevent_any_mutation(grouped, case):
    await prepare(grouped)
    runtime, music, house, _ = grouped[0]
    if case == "source_queue":
        grouped[2]["a"].append({**deepcopy(grouped[2]["a"][0]), "queue_item_id": "changed"})
    elif case == "target_busy":
        music.raw["b"]["playback_state"] = "buffering"
    elif case == "member_busy":
        music.raw["d"]["playback_state"] = "playing"
    elif case in {"source_offline", "target_offline"}:
        music.raw["c" if case == "source_offline" else "d"]["available"] = False
    else:
        value = data(grouped)
        value["group_handoffs"]["a"]["expires"] = 0
        runtime.save(value)
    with pytest.raises((ValueError, PermissionError)):
        await confirm(grouped)
    assert not music.calls


@pytest.mark.parametrize("point", ["dissolve", "transfer", "form"])
async def test_lost_response_is_never_replayed_or_advanced_by_recheck(grouped, monkeypatch, point):
    runtime, music, _, _ = grouped[0]
    await prepare(grouped)
    original = music.control

    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        if (
            (point == "dissolve" and args[2] == "players/cmd/set_members" and kwargs["target_player"] == "a")
            or (point == "transfer" and args[2] == "homestarter/transfer")
            or (point == "form" and args[2] == "players/cmd/set_members" and kwargs["target_player"] == "b")
        ):
            raise MusicRuntimeError("Synthetic lost reply")

    monkeypatch.setattr(music, "control", lost)
    with pytest.raises(MusicRuntimeError):
        await confirm(grouped)
    before = deepcopy(music.calls)
    if point == "form":
        await action(grouped, "group_transfer_recheck")
    else:
        with pytest.raises(ValueError):
            await action(grouped, "group_transfer_recheck")
    assert music.calls == before
    if point == "form":
        assert not data(grouped)["group_handoffs"]
    else:
        assert data(grouped)["group_handoffs"]["a"]["phase"] == "uncertain"
        with pytest.raises(ValueError):
            await confirm(grouped)


@pytest.mark.parametrize("phase", ["dissolve", "transfer", "form"])
async def test_cancellation_keeps_durable_uncertainty(grouped, monkeypatch, phase):
    await prepare(grouped)
    music = grouped[0][1]
    original = music.control

    async def cancelled(*args, **kwargs):
        await original(*args, **kwargs)
        if (
            (phase == "dissolve" and args[2] == "players/cmd/set_members" and kwargs["target_player"] == "a")
            or (phase == "transfer" and args[2] == "homestarter/transfer")
            or (phase == "form" and args[2] == "players/cmd/set_members" and kwargs["target_player"] == "b")
        ):
            raise asyncio.CancelledError()

    monkeypatch.setattr(music, "control", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await confirm(grouped)
    assert data(grouped)["group_handoffs"]["a"]["phase"] == "uncertain"
    assert [n for n, _ in music.calls].count("homestarter/transfer") <= 1


async def test_paused_group_remains_paused_and_unmoved(grouped):
    music = grouped[0][1]
    music.raw["a"]["playback_state"] = "paused"
    music.queues["a"]["state"] = "paused"
    with pytest.raises(ValueError, match="Paused grouped moves"):
        await prepare(grouped)
    assert not music.calls


async def test_explicit_replace_cannot_bypass_native_empty_destination_contract(grouped):
    grouped[0][1].raw["b"]["playback_state"] = "playing"
    with pytest.raises(ValueError, match="destination|speaker"):
        await action(grouped, "group_transfer_prepare", target="media_player.b", settings={"members": ["media_player.b", "media_player.d"]}, value="replace")
    assert not grouped[0][1].calls


@pytest.mark.parametrize("point", ["dissolve", "transfer"])
@pytest.mark.parametrize("change", ["member_disconnect", "member_occupied", "permissions"])
async def test_interrupted_phase_never_overwrites_new_destination_or_repeats(grouped, monkeypatch, point, change):
    runtime, music, _, saved = grouped[0]
    await prepare(grouped)
    original = music.control

    async def changed(*args, **kwargs):
        await original(*args, **kwargs)
        matches = (point == "dissolve" and args[2] == "players/cmd/set_members" and kwargs["target_player"] == "a") or (
            point == "transfer" and args[2] == "homestarter/transfer"
        )
        if matches:
            if change == "member_disconnect":
                music.raw["d"]["available"] = False
            elif change == "member_occupied":
                music.raw["d"]["playback_state"] = "playing"
            else:
                saved["choices"]["music"]["sources"].remove("media_player.d")

    monkeypatch.setattr(music, "control", changed)
    with pytest.raises((MusicRuntimeError, ValueError, PermissionError)):
        await confirm(grouped)
    before = deepcopy(music.calls)
    await runtime.tick()
    assert music.calls == before
    assert not any(n == "players/cmd/set_members" and a["target_player"] == "b" for n, a in music.calls)
    assert data(grouped)["group_handoffs"]["a"]["phase"] == "uncertain"


async def test_unconfirmed_move_hides_queue_mutations_and_preserves_owner_through_reads(grouped, monkeypatch):
    await prepare(grouped)
    runtime, music, _, _ = grouped[0]
    original = music.control

    async def partial(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members" and kwargs["target_player"] == "a":
            music.raw["c"]["synced_to"] = "a"

    monkeypatch.setattr(music, "control", partial)
    with pytest.raises(MusicRuntimeError):
        await confirm(grouped)
    before = deepcopy(music.calls)
    view = await runtime.view("admin", "panel", "one")
    assert not any(p.get("can_edit") or p.get("can_add") for p in view["sessions"])
    assert data(grouped)["leases"]["a"]["scope"] == "person:one"
    await runtime.tick()
    assert music.calls == before


async def test_reconnect_cannot_adopt_an_old_uncertain_group_move(grouped, monkeypatch):
    await prepare(grouped)
    music = grouped[0][1]
    original = music.control

    async def lost(*args, **kwargs):
        await original(*args, **kwargs)
        if args[2] == "players/cmd/set_members" and kwargs["target_player"] == "b":
            raise MusicRuntimeError("Synthetic lost group ack")

    monkeypatch.setattr(music, "control", lost)
    with pytest.raises(MusicRuntimeError):
        await confirm(grouped)
    before = deepcopy(music.calls)
    music.conn["generation"] = 2
    with pytest.raises(ValueError):
        await action(grouped, "group_transfer_recheck")
    assert music.calls == before
    assert data(grouped)["group_handoffs"]["a"]["generation"] == 1


@pytest.mark.parametrize("phase", ["review", "transfer"])
async def test_native_owner_member_permissions_are_never_expanded(grouped, monkeypatch, phase):
    music = grouped[0][1]
    if phase == "review":
        grouped[4]["player_filter"] = ["a", "b", "c"]
        with pytest.raises(PermissionError):
            await prepare(grouped)
        assert not music.calls
    else:
        await prepare(grouped)
        original = music.control

        async def revoked(*args, **kwargs):
            await original(*args, **kwargs)
            if args[2] == "homestarter/transfer":
                grouped[4]["player_filter"] = ["a", "b", "c"]

        monkeypatch.setattr(music, "control", revoked)
        with pytest.raises(PermissionError):
            await confirm(grouped)
        assert not any(n == "players/cmd/set_members" and a["target_player"] == "b" for n, a in music.calls)
