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
            self.raw[p].update(playback_state="playing", current_media={"queue_item_id": item}, elapsed_time=0, elapsed_time_last_updated=time.time())
        if command == "player_queues/seek":
            self.raw[p].update(elapsed_time=args["position"], elapsed_time_last_updated=time.time())
            self.queues[p].update(elapsed_time=args["position"], elapsed_time_last_updated=time.time())
        if command in {"player_queues/pause", "player_queues/stop"}:
            self.raw[p]["playback_state"] = "paused"
            self.queues[p].update(state="paused", elapsed_time=self.raw[p]["elapsed_time"], elapsed_time_last_updated=time.time())


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
    assert music.calls[-1][0] == "player_queues/play_media" and music.calls[-1][1]["start_from_beginning"] is True
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


async def test_play_waits_for_physical_feedback_and_buffering_does_not_lose_owned_session(setup, monkeypatch):
    item = await book(setup)
    runtime, music, house, _ = setup
    original, samples = music.command, []

    async def command(endpoint, connection, name, **args):
        value = await original(endpoint, connection, name, **args)
        if name == "players/get" and music.calls and music.calls[0][0] == "player_queues/play_media":
            samples.append(name)
            if len(samples) == 1:
                value["playback_state"] = "buffering"
        return value

    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(listening.asyncio, "sleep", AsyncMock())
    await act(setup, "one", "play_item", item=item)
    assert len(samples) >= 2
    data = runtime.load(house, music.conn)
    music.raw["a"].update(playback_state="buffering", elapsed_time=999, elapsed_time_last_updated=time.time())
    assert not await runtime.sample({}, music.conn, data, "a", data["leases"]["a"])
    assert data["leases"]["a"]["scope"] == "person:one"
    assert not data["profiles"]["person:one"]["books"]


async def test_only_explicit_device_acknowledged_pause_can_capture_frozen_queue_position(setup):
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    runtime, music, house, _ = setup
    data = runtime.load(house, music.conn)
    lease = data["leases"]["a"]
    lease["last_sample"] = time.time() - 2
    music.raw["a"].update(elapsed_time=0, elapsed_time_last_updated=time.time() - 300)
    music.queues["a"].update(elapsed_time=120, elapsed_time_last_updated=time.time() - 0.1)
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    music.raw["a"]["playback_state"] = "paused"
    music.queues["a"]["state"] = "paused"
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    lease["pause_requested_at"] = time.time() - 0.2
    assert await runtime.sample({}, music.conn, data, "a", lease)
    record = data["profiles"]["person:one"]["books"][item]
    assert record["position"] == 120 and record["position_source"] == "ma_paused_queue"
    music.queues["a"].update(elapsed_time=900, elapsed_time_last_updated=time.time())
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    assert record["position"] == 120


async def test_reused_native_episode_queue_is_explicitly_reset_for_a_different_listener(setup, monkeypatch):
    item = await book(setup)
    music = setup[1]
    original = music.control

    async def control(endpoint, connection, command, **args):
        await original(endpoint, connection, command, **args)
        if command == "player_queues/play_media":
            music.queues["a"]["current_item"]["queue_item_id"] = "reused-item"
            music.raw["a"]["current_media"]["queue_item_id"] = "reused-item"

    monkeypatch.setattr(music, "control", control)
    await act(setup, "one", "play_item", item=item)
    await act(setup, "one", "pause")
    await act(setup, "two", "play_item", item=item)
    assert music.calls[-1] == ("player_queues/seek", {"queue_id": "a", "position": 0})


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


async def test_podcast_show_opens_native_episodes_and_does_not_become_progress_item(setup, monkeypatch):
    runtime, music, _, _ = setup
    show = {"uri": "fixture://podcast/show", "media_type": "podcast", "name": "Example podcast", "item_id": "show", "provider": "fixture-podcasts"}
    episode = {"uri": "fixture://podcast_episode/one", "media_type": "podcast_episode", "name": "Example episode"}
    calls = []

    async def command(endpoint, connection, name, **args):
        calls.append((name, args))
        return show if name == "music/item_by_uri" else [episode] if name == "music/podcasts/podcast_episodes" else {"podcasts": [show]}

    monkeypatch.setattr(music, "command", command)
    rows = await runtime.catalog_items({}, {}, query="Example")
    assert rows[0]["folder"] and rows[0]["kind"] == "podcast"
    with pytest.raises(ValueError, match="Choose an item"):
        await runtime.item(rows[0]["id"], {"favorites": [], "recent": [], "books": {}})
    episodes = await runtime.catalog_items({}, {}, folder=rows[0]["id"])
    assert not episodes[0]["folder"] and episodes[0]["kind"] == "podcast_episode"
    assert calls[-1] == ("music/podcasts/podcast_episodes", {"item_id": "show", "provider_instance_id_or_domain": "fixture-podcasts"})


async def test_regional_radio_uses_configured_terms_and_cached_native_items(setup, monkeypatch):
    runtime, music, _, _ = setup
    calls = []

    async def command(endpoint, connection, name, **args):
        calls.append((name, args))
        return {"radio": [{"uri": "fixture://radio/one", "media_type": "radio", "name": "Example local station", "stream_url": "fixture://private"}]}

    monkeypatch.setattr(music, "command", command)
    region = {"name": "Example region", "country_code": "AU", "search_terms": ["Example town", "Example valley"]}
    rows = await runtime.regional_radio({}, music.conn, region)
    assert len(rows) == 1 and rows[0]["id"] in runtime.catalog and "stream_url" not in rows[0]
    assert [args["search_query"] for _, args in calls] == region["search_terms"]
    assert all(args["media_types"] == ["radio"] for _, args in calls)
    await runtime.regional_radio({}, music.conn, region)
    assert len(calls) == 2


async def test_child_can_play_shared_favourites_without_search_or_mutating_house(setup):
    item = await book(setup)
    await act(setup, None, "favorite", item=item)
    setup[3]["members"]["two"] = {"kind": "child", "rooms": [], "devices": ["a"]}
    view = await setup[0].view("admin", "panel", "two")
    assert [row["id"] for row in view["shared"]] == [item]
    assert not view["browse"] and not view["library"]
    await act(setup, "two", "favorite", item=item)
    await act(setup, "two", "unfavorite", item=item)
    assert (await setup[0].view("admin", "panel", None))["favorites"][0]["id"] == item
    await act(setup, "two", "play_item", item=item)
    assert setup[1].calls[0][1]["queue_id"] == "a"
    assert setup[1].calls[-1][0] == "player_queues/play_media" and setup[1].calls[-1][1]["start_from_beginning"] is True


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


async def test_stopped_player_cannot_reset_saved_book_progress(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    data = runtime.load(house, music.conn)
    profile = data["profiles"]["person:one"]
    profile["books"][item] = {**data["leases"]["a"]["item"], "position": 600, "duration": 3600, "updated_at": time.time()}
    runtime.save(data)
    music.raw["a"].update(playback_state="idle", elapsed_time=0, elapsed_time_last_updated=time.time())
    view = await runtime.view("admin", "panel", "one")
    assert view["books"][0]["position"] == 600
    assert view["session"] is None
