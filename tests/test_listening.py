"""Listener state uses fictional people, exact registry IDs and queue feedback."""

import time
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter import listening
from homestarter.household import HouseholdStore, empty_household
from homestarter.listening import ListeningRuntime, media_record
from homestarter.music_runtime import MusicRuntimeError


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
            state = "paused" if command == "player_queues/pause" else "idle"
            self.raw[p]["playback_state"] = state
            self.queues[p].update(state=state, elapsed_time=self.raw[p]["elapsed_time"], elapsed_time_last_updated=time.time())


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


async def test_native_books_propagate_person_and_resume_same_title_independently(setup, monkeypatch):
    from test_listening_books import setup as book_setup

    runtime, music, house, _ = setup
    _, config, providers, users = book_setup()
    providers.append({"id": "fixture_house", "domain": "spotify", "name": "House", "available": True})
    monkeypatch.setattr(listening.household_services, "load", lambda *_: config)
    original_command, original_control = music.command, music.control
    native_positions = {"user_one": 123, "user_two": 907}
    native = {
        "uri": "library://audiobook/same-book",
        "media_type": "audiobook",
        "name": "Same synthetic book",
        "provider_mappings": [{"provider_domain": "audiobookshelf", "provider_instance": "books_" + p, "item_id": "same-book"} for p in ("one", "two")],
    }
    native["provider_mappings"].append({"provider_domain": "spotify", "provider_instance": "fixture_house", "item_id": "same-book"})
    snapshot = await music.snapshot()
    snapshot["providers"] = providers
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))

    async def command(endpoint, connection, name, **args):
        if name == "auth/users":
            return deepcopy(users)
        if name == "music/item_by_uri":
            return deepcopy(native)
        return await original_command(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        if name == "player_queues/play_media":
            assert args["user"]["required"] is True
            assert args["start_from_beginning"] is False
            person = args["user"]["user_id"].removeprefix("user_")
            assert args["media"] == "books_" + person + "://audiobook/same-book"
            music.book = {**native, "uri": args["media"]}
            await original_control(endpoint, connection, name, **args)
            pid = args["queue_id"]
            position = native_positions[args["user"]["user_id"]]
            music.raw[pid].update(elapsed_time=position, elapsed_time_last_updated=time.time())
            music.queues[pid].update(elapsed_time=position, elapsed_time_last_updated=time.time())
            return
        await original_control(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    endpoint = {"version": "2.10.7"}
    item = media_record(native)
    data = runtime.load(house, music.conn)
    for person, pid in (("one", "a"), ("two", "b")):
        profile = runtime.profile(data, person)
        profile["books"][item["id"]] = {**item, "position": 9999}  # stale UI history must not overwrite native progress
        await runtime.play(endpoint, music.conn, data, profile, "person:" + person, {"player_id": pid}, item, "admin", "panel")
        music.raw[pid]["elapsed_time_last_updated"] = time.time()
        assert await runtime.sample(endpoint, music.conn, data, pid, data["leases"][pid])
        assert profile["books"][item["id"]]["position"] == native_positions["user_" + person]
    assert not any(name == "player_queues/seek" for name, _ in music.calls)
    before = deepcopy(data["profiles"])
    users[0]["provider_filter"] = []  # native source deletion / reconnect must not become unrestricted fallback
    assert not await runtime.sample(endpoint, music.conn, data, "a", data["leases"]["a"])
    assert "a" not in data["leases"] and data["profiles"] == before
    music.calls.clear()
    with pytest.raises(MusicRuntimeError, match="administrator review"):
        await runtime.play(endpoint, music.conn, data, runtime.profile(data, "one"), "person:one", {"player_id": "a"}, item, "admin", "panel")
    assert not music.calls  # no pause or queue replacement before isolation checks


async def test_spotify_never_uses_unprotected_playback_or_pauses_when_guard_missing(setup, monkeypatch):
    runtime, music, house, _ = setup
    item = media_record({"uri": "fixture_spotify://track/example", "media_type": "track", "name": "Synthetic track"})
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value={"providers": [{"id": "fixture_spotify", "domain": "spotify"}]}))
    monkeypatch.setattr(music, "account_guard", AsyncMock(side_effect=MusicRuntimeError("Protection unavailable")), raising=False)
    data = runtime.load(house, music.conn)
    with pytest.raises(MusicRuntimeError, match="Protection unavailable"):
        await runtime.play("fixture", music.conn, data, runtime.profile(data, "one"), "person:one", {"player_id": "a"}, item, "admin", "panel")
    assert not music.calls


async def test_discovery_view_hides_unprotected_controls_and_recovers_without_transport(setup, monkeypatch):
    runtime, music, _, _ = setup
    snapshot = await music.snapshot()
    snapshot["providers"] = [{"id": "fixture_spotify", "domain": "spotify", "name": "House", "available": True}]
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))
    guard = AsyncMock(side_effect=MusicRuntimeError("Private upstream error"))
    monkeypatch.setattr(music, "account_guard", guard, raising=False)
    view = await runtime.view("admin", "panel")
    assert view["discovery"] is False
    assert "temporarily unavailable" in view["discovery_issue"]
    assert "Private upstream error" not in str(view)
    assert view["browse"] and view["library"]
    assert not music.calls
    guard.side_effect = None
    guard.return_value = {"isolated": True}
    recovered = await runtime.view("admin", "panel")
    assert recovered["discovery"] is True
    assert recovered["discovery_issue"] is None
    assert not music.calls


async def test_pending_personal_account_never_advertises_shared_discovery(setup, monkeypatch):
    runtime, music, house, _ = setup
    house["people"][0]["name"] = "Renae"
    runtime.store.save(house)
    snapshot = await music.snapshot()
    snapshot["providers"] = [{"id": "fixture_spotify", "domain": "spotify", "name": "House", "available": True}]
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))
    guard = AsyncMock(return_value={"isolated": True})
    monkeypatch.setattr(music, "account_guard", guard, raising=False)
    view = await runtime.view("admin", "panel", "one")
    assert view["discovery"] is False
    assert view["discovery_issue"] == "Your music account is not connected yet."
    guard.assert_not_awaited()
    assert view["browse"]
    assert not music.calls


def test_audiobook_status_requires_person_binding_and_does_not_claim_provider_sync():
    config = {"libraries": [{"provider_id": "example-books", "people": ["one"]}]}
    providers = [{"id": "example-books", "domain": "audiobookshelf", "available": True}]
    assert listening.audiobook_status(config, providers, None)["state"] == "choose_listener"
    assert listening.audiobook_status(config, providers, "two")["state"] == "not_connected"
    assert listening.audiobook_status(config, [], "one")["state"] == "unavailable"
    assert listening.audiobook_status(config, providers, "one")["state"] == "needs_verification"
    providers[0]["enabled"] = False
    assert listening.audiobook_status(config, providers, "one")["state"] == "unavailable"


async def test_missing_audiobook_source_is_honest_and_does_not_start_audio(setup):
    runtime, music, _, _ = setup
    house = await runtime.view("admin", "panel")
    assert house["audiobooks"]["state"] == "choose_listener"
    personal = await runtime.view("admin", "panel", "one")
    assert personal["audiobooks"]["state"] == "not_connected"
    assert personal["audiobooks"]["message"] == "Your audiobook library is not connected yet."
    assert not music.calls


async def test_media_app_bootstrap_requires_existing_display_authorization(setup):
    runtime, music, _, _ = setup
    with pytest.raises(PermissionError):
        await runtime.bootstrap(None)
    boot = await runtime.bootstrap("admin")
    assert boot == {"surfaces": [{"id": "panel", "name": "Example panel", "person_id": None}]}
    view = await runtime.view("admin", "panel")
    assert view["profiles"] == [{"id": "one", "name": "Example one"}, {"id": "two", "name": "Example two"}]
    assert not music.calls


async def test_failed_catalogue_reseed_preserves_controls_for_unchanged_owned_playback(setup, monkeypatch):
    runtime, music, house, _ = setup
    snapshot = await music.snapshot()
    snapshot["providers"] = [{"id": "fixture_spotify", "domain": "spotify"}]
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(music, "account_guard", AsyncMock(return_value={"isolated": True}), raising=False)
    monkeypatch.setattr(runtime, "sample", AsyncMock(return_value=True))
    item = media_record({"uri": "fixture_spotify://track/example", "media_type": "track", "name": "Synthetic track"})
    data = runtime.load(house, music.conn)
    lease = {"scope": "house", "kind": "track", "item": item, "queue_item_id": "old", "generation": 1, "native_session": "owned"}
    data["leases"]["a"] = deepcopy(lease)
    music.raw["a"].update(playback_state="playing", current_media={"queue_item_id": "old"})
    music.queues["a"]["state"] = "playing"
    original = music.control

    async def control(endpoint, connection, name, **args):
        if name == "homestarter/media_play":
            raise MusicRuntimeError("Catalogue temporarily unavailable")
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "control", control)
    with pytest.raises(MusicRuntimeError, match="temporarily unavailable"):
        await runtime.play("fixture", music.conn, data, runtime.profile(data, None), "house", {"player_id": "a"}, item, "admin", "panel", discovery={})
    assert runtime.load(house, music.conn)["leases"]["a"] == lease
    assert music.raw["a"]["playback_state"] == "playing"
    await act(setup, None, "stop")
    assert any(name == "player_queues/stop" for name, _ in music.calls)


async def test_provider_continuation_keeps_listener_lease_but_foreign_session_drops_it(setup, monkeypatch):
    runtime, music, house, _ = setup
    data = runtime.load(house, music.conn)
    lease = {"scope": "house", "kind": "track", "queue_item_id": "old", "queue_items": ["old"], "generation": 1, "native_session": "owned"}
    data["leases"]["a"] = lease
    music.queues["a"].update(state="playing", current_item={"queue_item_id": "continued"})
    music.raw["a"].update(playback_state="playing", current_media={"queue_item_id": "continued"})
    original = music.command
    context = {"session": "owned", "item": "continued"}

    async def command(endpoint, connection, name, **args):
        return context if name == "homestarter/queue_context" else await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    await runtime.sample("fixture", music.conn, data, "a", lease)
    assert data["leases"]["a"]["queue_item_id"] == "continued"
    lease["logical_session"] = "logical-owned"
    context.update(session="reseeded-native", logical_session="logical-owned")
    await runtime.sample("fixture", music.conn, data, "a", lease)
    assert data["leases"]["a"]["native_session"] == "reseeded-native"
    context["session"] = "someone-else"
    context["logical_session"] = None
    await runtime.sample("fixture", music.conn, data, "a", lease)
    assert not data["leases"]


async def test_ambient_playback_uses_no_spotify_account_and_loops_native_audio(setup):
    runtime, music, house, _ = setup
    item = media_record({"uri": "fixture_ambient://sound_effect/rain", "media_type": "sound_effect", "name": "Rain"})
    item["category"] = "ambient"
    data = runtime.load(house, music.conn)
    await runtime.play("fixture", music.conn, data, runtime.profile(data, None), "house", {"player_id": "a"}, item, "admin", "panel")
    assert not any(name.startswith("homestarter/") for name, _ in music.calls)
    assert ("player_queues/repeat", {"queue_id": "a", "repeat_mode": "one"}) in music.calls


async def test_pending_personal_identity_does_not_claim_busy_or_touch_other_playback(setup, monkeypatch):
    runtime, music, house, _ = setup
    house["people"][0]["name"] = "Renae"
    monkeypatch.setattr(runtime.store, "load", lambda: house)
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value={"providers": [{"id": "shared", "domain": "spotify", "name": "House"}]}))
    monkeypatch.setattr(music, "account_guard", AsyncMock(return_value={}), raising=False)
    item = media_record({"uri": "spotify://track/example", "media_type": "track", "name": "Example catalogue track"})
    data = runtime.load(house, music.conn)
    with pytest.raises(MusicRuntimeError, match="Connect Spotify — Renae"):
        await runtime.play("fixture", music.conn, data, runtime.profile(data, "one"), "person:one", {"player_id": "a"}, item, "admin", "panel")
    assert not music.calls


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
    with pytest.raises(ValueError, match="already in use"):
        await act(setup, "two", "play_item", item=item)
    await act(setup, "one", "stop")  # owner explicitly releases the paused session
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


async def test_sendspin_idle_pause_keeps_only_explicit_unchanged_owned_evidence(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    original = music.control

    async def idle_pause(endpoint, connection, command, **args):
        await original(endpoint, connection, command, **args)
        if command == "player_queues/pause":
            music.raw["a"].update(
                playback_state="idle",
                active_output_protocol="fixture-sendspin",
                output_protocols=[{"protocol_domain": "sendspin", "output_protocol_id": "fixture-sendspin"}],
            )
            music.raw["a"]["current_media"]["elapsed_time_last_updated"] = time.time() - 1
            music.queues["a"].update(state="idle", elapsed_time=12, elapsed_time_last_updated=time.time())

    music.control = idle_pause
    await act(setup, "one", "pause")
    data = runtime.load(house, music.conn)
    assert data["leases"]["a"]["idle_pause_ack"]
    assert data["profiles"]["person:one"]["books"][item]["position"] == 12
    assert (await runtime.view("admin", "panel", "one"))["session"]
    count = len(music.calls)
    with pytest.raises(ValueError, match="another listening"):
        await act(setup, "two", "play")
    assert len(music.calls) == count
    # Metadata-only feedback does not transfer ownership or update progress.
    music.queues["a"]["elapsed_time_last_updated"] += 1
    assert (await runtime.view("admin", "panel", "one"))["session"]
    music.raw["a"]["output_protocols"][0]["output_protocol_id"] = "external-transport"
    assert (await runtime.view("admin", "panel", "one"))["session"] is None
    assert runtime.load(house, music.conn)["profiles"]["person:one"]["books"][item]["position"] == 12


async def test_sendspin_idle_without_pause_intent_never_owns_progress(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    music.raw["a"].update(
        playback_state="idle",
        active_output_protocol="fixture-sendspin",
        output_protocols=[{"protocol_domain": "sendspin", "output_protocol_id": "fixture-sendspin"}],
    )
    music.raw["a"]["current_media"]["elapsed_time_last_updated"] = time.time()
    music.queues["a"].update(state="idle", elapsed_time=120, elapsed_time_last_updated=time.time())
    assert (await runtime.view("admin", "panel", "one"))["session"] is None
    assert not runtime.load(house, music.conn)["profiles"]["person:one"]["books"]


async def test_sendspin_pause_waits_for_both_acknowledgements_without_importing_progress(setup):
    runtime, music, house, _ = setup
    item = await book(setup)
    await act(setup, "one", "play_item", item=item)
    data = runtime.load(house, music.conn)
    lease = data["leases"]["a"]
    lease["pause_requested_at"] = time.time()
    music.raw["a"].update(
        playback_state="idle",
        active_output_protocol=None,
        output_protocols=[{"protocol_domain": "sendspin", "output_protocol_id": "fixture-sendspin", "available": True}],
    )
    music.raw["a"]["current_media"]["elapsed_time_last_updated"] = time.time()
    music.queues["a"].update(state="playing", elapsed_time=600, elapsed_time_last_updated=time.time())
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    assert "a" in data["leases"] and "idle_pause_ack" not in lease
    assert not data["profiles"]["person:one"]["books"]
    music.queues["a"].update(state="idle", elapsed_time_last_updated=lease["pause_requested_at"] - 1)
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    assert "a" in data["leases"] and "idle_pause_ack" not in lease
    lease["pause_requested_at"] -= 4
    music.queues["a"]["state"] = "playing"
    assert not await runtime.sample({}, music.conn, data, "a", lease)
    assert "a" not in data["leases"]


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
    await act(setup, "one", "stop")
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
        "sources": ["fixture"],
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
    rows = [media_record(show)]
    runtime.catalog[rows[0]["id"]] = rows[0]
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
