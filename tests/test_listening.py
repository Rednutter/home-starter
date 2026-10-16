"""Listener state uses fictional people, exact registry IDs and queue feedback."""

import time
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter import listening
from homestarter.household import HouseholdStore, empty_household
from homestarter.listening import ListeningRuntime, media_record


class Music:
    def __init__(self):
        self.calls = []
        self.conn = {"server_id": "fixture-server", "app": "fixture_ma", "generation": 1}
        self.raw = {
            p: {"playback_state": "idle", "active_source": p, "current_media": {}, "elapsed_time": 0, "elapsed_time_last_updated": 0} for p in ("a", "b")
        }
        self.queues = {p: {"queue_id": p, "active": True, "state": "idle", "current_item": {"queue_item_id": "old"}} for p in self.raw}
        self.book = {"uri": "fixture://book/one", "media_type": "audiobook", "name": "Example book"}

    def connection(self):
        return self.conn

    async def endpoint(self):
        return "fixture"

    async def snapshot(self):
        return {
            "connected": True,
            "players": [{"id": p, "name": "Example " + p, "available": True, "single": True, "state": self.raw[p]["playback_state"]} for p in self.raw],
        }

    async def command(self, endpoint, connection, command, **args):
        if command == "music/browse":
            return [self.book]
        if command == "player_queues/items":
            return [deepcopy(self.queues[args["queue_id"]]["current_item"]), {"queue_item_id": "next-fixture"}]
        p = args["player_id"]
        return deepcopy(self.raw[p] if command == "players/get" else self.queues[p])

    async def control(self, endpoint, connection, command, **args):
        self.calls.append((command, args))
        p = args.get("queue_id", args.get("player_id"))
        if command == "player_queues/play_media":
            item = "item-" + str(len(self.calls))
            self.queues[p].update(state="playing", current_item={"queue_item_id": item, "duration": 3600, "media_item": self.book})
            self.raw[p].update(playback_state="playing", current_media={"queue_item_id": item})
        if command in {"player_queues/pause", "player_queues/stop"}:
            self.raw[p]["playback_state"] = "paused"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = HouseholdStore(str(tmp_path))
    house = empty_household()
    house["people"] = [{"id": p, "name": "Example " + p, "audience": "adult"} for p in ("one", "two")]
    house["surfaces"] = [{"id": "panel", "name": "Example panel", "profile": "specialist", "person_id": None, "area_id": None, "audience": "everyone"}]
    house = store.save(house)
    saved = {"choices": {"music": {"intent": "wanted", "sources": ["media_player.a", "media_player.b"], "screens": ["panel"]}}, "members": {}, "devices": {}}
    monkeypatch.setattr(listening.readiness, "load", lambda *args: saved)
    core = type("Core", (), {"is_admin": AsyncMock(return_value=True)})()
    music = Music()
    runtime = ListeningRuntime(music, core, store)
    runtime.mapping_cache = (
        time.monotonic(),
        [{"entity_id": "media_player." + p, "unique_id": p, "platform": "music_assistant", "device_id": p} for p in ("a", "b")],
        {},
    )
    return runtime, music, house, saved


async def act(setup, person, action, **extra):
    runtime, _, house, _ = setup
    return await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": action, "player": "media_player.a", **extra})


async def book(setup):
    view = await setup[0].view("admin", "panel", "one")
    return view["library"][0]["id"]


async def test_listener_progress_survives_restart_and_does_not_follow_speaker(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    stamp = time.time() + 0.01
    music.raw["a"].update(elapsed_time=615, elapsed_time_last_updated=stamp)
    # Simulate a subsequent real raw feedback event without extrapolating time.
    data = runtime.load(house, music.conn)
    data["leases"]["a"]["last_sample"] = stamp - 1
    data["leases"]["a"].pop("awaiting_position")
    runtime.save(data)
    music.raw["a"]["elapsed_time_last_updated"] = time.time()
    await runtime.view("admin", "panel", "one")
    await act(setup, "one", "pause")
    await act(setup, "two", "play_item", item=item)
    assert music.calls[-1] == ("player_queues/seek", {"queue_id": "a", "position": 0})
    assert runtime.load(house, music.conn)["profiles"]["person:one"]["books"][item]["position"] == 615
    assert not runtime.load(house, music.conn)["profiles"]["person:two"]["books"]
    await act(setup, "two", "pause")
    restarted = ListeningRuntime(music, runtime.core, runtime.store)
    restarted.mapping_cache = runtime.mapping_cache
    setup = restarted, music, house, setup[3]
    await act(setup, "one", "resume", item=item, player="media_player.b")
    assert music.calls[-1] == ("player_queues/seek", {"queue_id": "b", "position": 615})


async def test_destination_delay_and_cancel_do_not_play_or_advance_progress(setup):
    item = await book(setup)
    await act(setup, "one", "destination")
    await act(setup, "one", "delay", item=item, value=300)
    assert not setup[1].calls
    job = deepcopy(setup[0].load(setup[2], setup[1].conn)["profiles"]["person:one"]["delayed"])
    await act(setup, "one", "cancel_delay")
    await setup[0].action("admin", "panel", "one", {"epoch": setup[2]["epoch"], "action": "play_item"}, expected_job=job)
    assert not setup[1].calls


async def test_start_now_uses_saved_destination_after_restart(setup):
    item = await book(setup)
    await act(setup, "one", "delay", item=item, value=300, player="media_player.b")
    setup[0].catalog.clear()
    await act(setup, "one", "start_now")
    assert setup[1].calls[0][1]["queue_id"] == "b"


async def test_external_queue_replacement_cannot_update_progress_or_pause(setup):
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    await act(setup, "one", "sleep", value=900)
    runtime, music, house, _ = setup
    data = runtime.load(house, music.conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    music.raw["a"].update(current_media={"queue_item_id": "external"}, elapsed_time=999, elapsed_time_last_updated=time.time())
    count = len(music.calls)
    await runtime.tick()
    assert len(music.calls) == count
    assert not runtime.load(house, music.conn)["profiles"]["person:one"]["books"]
    with pytest.raises(ValueError, match="another listening"):
        await act(setup, "one", "pause")


async def test_revoked_music_opt_in_disarms_timer_and_commands(setup):
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    await act(setup, "one", "sleep", value=900)
    runtime, music, house, saved = setup
    data = runtime.load(house, music.conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    saved["choices"]["music"]["intent"] = "later"
    count = len(music.calls)
    await runtime.tick()
    assert len(music.calls) == count
    assert not runtime.load(house, music.conn)["leases"]
    with pytest.raises(ValueError, match="Readiness"):
        await act(setup, "one", "play_item", item=item)


async def test_busy_speaker_and_child_permissions_fail_closed(setup):
    item = await book(setup)
    setup[1].raw["a"]["playback_state"] = "playing"
    with pytest.raises(ValueError, match="already in use"):
        await act(setup, "one", "play_item", item=item)
    setup[3]["members"]["two"] = {"kind": "child", "rooms": [], "devices": []}
    view = await setup[0].view("admin", "panel", "two")
    assert not view["players"] and not view["browse"]
    with pytest.raises(PermissionError):
        await setup[0].view("admin", "panel", "two", query="book")
    assert not setup[1].calls


def test_catalog_records_expose_no_stream_or_credentials():
    assert media_record({"uri": "fixture://one", "name": "Example", "media_type": "track", "streamdetails": {"url": "fixture://stream"}}) == {
        "id": listening.digest("fixture://one")[:24],
        "title": "Example",
        "kind": "track",
        "uri": "fixture://one",
        "folder": False,
    }


async def test_only_current_bound_control_account_can_use_ingress(setup, monkeypatch):
    runtime, _, house, _ = setup
    runtime.core.is_admin.return_value = False
    surface = house["surfaces"][0]
    account = {"id": "display", "issue": None, "permission": "control", "signature": "current"}
    row = {"user_id": "display", "user_signature": "current", "surface_signature": listening.screen_identity.signature(surface)}
    monkeypatch.setattr(listening.screen_identity, "load", lambda *args: {"screens": {"panel": row}})
    monkeypatch.setattr(listening.screen_identity, "accounts", AsyncMock(return_value=[account]))
    await runtime.authorize("display", "panel", "one")
    for user in (None, "other"):
        with pytest.raises(PermissionError):
            await runtime.authorize(user, "panel", "one")
    account["signature"] = "changed"
    with pytest.raises(PermissionError):
        await runtime.authorize("display", "panel", "one")
    account.update(signature="current", permission="read_only")
    with pytest.raises(PermissionError):
        await runtime.authorize("display", "panel", "one")


async def test_stale_player_feedback_and_epoch_cannot_write_progress(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    music.raw["a"].update(elapsed_time=999, elapsed_time_last_updated=time.time() - 60)
    view = await runtime.view("admin", "panel", "one")
    assert view["books"] == []
    with pytest.raises(ValueError, match="Refresh"):
        await runtime.action("admin", "panel", "one", {"action": "pause", "epoch": -1})
    assert "uri" not in view["library"][0]
    assert "user" not in str(view)


async def test_provider_resume_feedback_is_not_imported_into_listener_progress(setup):
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    runtime, music, house, _ = setup
    data = runtime.load(house, music.conn)
    data["leases"]["a"]["last_sample"] = time.time() - 1
    runtime.save(data)
    music.raw["a"].update(elapsed_time=1800, elapsed_time_last_updated=time.time())
    assert not (await runtime.view("admin", "panel", "one"))["books"]
    music.raw["a"].update(elapsed_time=1, elapsed_time_last_updated=time.time())
    assert (await runtime.view("admin", "panel", "one"))["books"][0]["position"] == 1


async def test_house_cannot_resume_personal_queue(setup):
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    await act(setup, "one", "pause")
    count = len(setup[1].calls)
    with pytest.raises(ValueError, match="another listening"):
        await act(setup, None, "play")
    assert len(setup[1].calls) == count


async def test_playlist_advancement_keeps_owned_transport_and_sleep_timer(setup):
    runtime, music, house, _ = setup
    music.book["media_type"] = "playlist"
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    await act(setup, "one", "sleep", value=900)
    music.queues["a"]["current_item"]["queue_item_id"] = "next-fixture"
    music.raw["a"]["current_media"]["queue_item_id"] = "next-fixture"
    assert (await runtime.view("admin", "panel", "one"))["session"]
    data = runtime.load(house, music.conn)
    data["profiles"]["person:one"]["sleep"]["at"] = 0
    runtime.save(data)
    await runtime.tick()
    assert music.calls[-1] == ("player_queues/pause", {"queue_id": "a"})
