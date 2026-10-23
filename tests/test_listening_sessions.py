"""Synthetic household queue conflicts; no live playback commands."""

import asyncio
import time
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter.listening import media_record
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup


@pytest.fixture
def queued(setup, monkeypatch):
    runtime, music, house, _ = setup
    snapshot = {
        "connected": True,
        "providers": [{"id": "fixture_local", "domain": "filesystem", "available": True}],
        "players": [
            {"id": p, "name": "Example " + p, "available": True, "single": True, "state": "playing" if p == "a" else "idle", "features": ["play_media"]}
            for p in ("a", "b")
        ],
    }
    monkeypatch.setattr(music, "snapshot", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.10.7"}))
    item = media_record({"uri": "fixture_local://track/one", "media_type": "track", "name": "Synthetic song"})
    data = runtime.load(house, music.conn)
    runtime.profile(data, "one")
    data["leases"]["a"] = {
        "scope": "person:one",
        "kind": "track",
        "item": item,
        "queue_item_id": "old",
        "queue_items": ["old"],
        "generation": 1,
        "session": "fixture-session",
        "last_sample": time.time(),
    }
    music.raw["a"].update(playback_state="playing", current_media={"queue_item_id": "old"})
    media = {"uri": item["uri"], "media_type": "track", "provider": "fixture_local"}
    music.queues["a"].update(
        state="playing",
        current_index=0,
        index_in_buffer=0,
        shuffle_enabled=False,
        current_item={"queue_item_id": "old", "name": "Synthetic song", "media_item": media},
    )
    rows = [{"queue_item_id": "old", "name": "Synthetic song", "media_item": media}]
    original_command = music.command

    async def command(endpoint, connection, name, **args):
        if name == "player_queues/items":
            return deepcopy(rows)
        if name == "homestarter/queue_context":
            return {"session": "native-owned", "item": "old"}
        if name == "music/item_by_uri":
            return {"media_type": "track", "provider": "fixture_local", "item_id": "one"}
        return await original_command(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        music.calls.append((name, args))
        if name == "player_queues/play_media":
            assert args["option"] in {"add", "next"}
            row = {"queue_item_id": "added-" + str(len(rows)), "name": "Added synthetic song", "media_item": media}
            if args["option"] == "next":
                rows.insert(music.queues["a"]["index_in_buffer"] + 1, row)
            else:
                rows.append(row)
        elif name == "player_queues/move_item":
            i = next(i for i, r in enumerate(rows) if r["queue_item_id"] == args["queue_item_id"])
            rows.insert(i + args["pos_shift"], rows.pop(i))
        elif name == "player_queues/delete_item":
            rows[:] = [r for r in rows if r["queue_item_id"] != args["item_id_or_index"]]
        else:
            pytest.fail("Unexpected native command")

    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    runtime.catalog[item["id"]] = item
    runtime.save(data)
    return setup, snapshot, item, rows


async def view(queued, person="two"):
    return await queued[0][0].view("admin", "panel", person)


async def action(queued, action, person="two", **extra):
    runtime, _, house, _ = queued[0]
    return await runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": action, "player": "media_player.a", **extra})


def session(value):
    return next(s for s in value["sessions"] if s["player_id"] == "a")


async def test_join_and_append_keep_owner_controls_queue_and_progress(queued):
    setup, _, item, _ = queued
    runtime, music, house, _ = setup
    before = deepcopy(music.queues["a"])
    current = session(await view(queued))
    assert current["owner"] == "Example one" and current["can_join"] and not current["can_add"]
    await action(queued, "queue_join", session=current["revision"])
    assert not music.calls and music.queues["a"] == before
    joined = session(await view(queued))
    assert joined["joined"] and joined["can_add"] and not joined["owned"]
    await action(queued, "queue_add", session=joined["revision"], item=item["id"])
    assert music.calls == [("player_queues/play_media", {"queue_id": "a", "media": item["uri"], "option": "add"})]
    data = runtime.load(house, music.conn)
    assert data["leases"]["a"]["scope"] == "person:one"
    assert data["profiles"]["person:two"]["books"] == {}
    assert music.queues["a"] == before
    with pytest.raises(ValueError, match="Refresh"):
        await action(queued, "stop")
    assert len(music.calls) == 1
    await action(queued, "queue_leave")
    assert not session(await view(queued))["joined"]


async def test_stale_join_and_add_are_rejected_without_transport(queued):
    _, _, item, rows = queued
    current = session(await view(queued))
    rows.append({"queue_item_id": "external-add", "name": "Existing addition"})
    with pytest.raises(ValueError, match="session changed"):
        await action(queued, "queue_join", session=current["revision"])
    current = session(await view(queued))
    await action(queued, "queue_join", session=current["revision"])
    with pytest.raises(ValueError, match="session changed"):
        await action(queued, "queue_add", session="stale", item=item["id"])
    assert not queued[0][1].calls


async def test_concurrent_profiles_starting_idle_speaker_preserve_first_queue(setup):
    runtime, music, house, _ = setup
    item = media_record(music.book)
    runtime.catalog[item["id"]] = item
    results = await asyncio.gather(
        *(
            runtime.action("admin", "panel", person, {"epoch": house["epoch"], "action": "play_item", "player": "media_player.a", "item": item["id"]})
            for person in ("one", "two")
        ),
        return_exceptions=True,
    )
    assert results[0] is None and isinstance(results[1], ValueError)
    assert "already in use" in str(results[1])
    assert sum(name == "player_queues/play_media" for name, _ in music.calls) == 1


async def test_join_does_not_expand_child_content_or_speaker_permission(queued):
    runtime, music, _, saved = queued[0]
    saved["members"]["two"] = {"kind": "child", "rooms": [], "devices": ["a"]}
    current = session(await view(queued))
    await action(queued, "queue_join", session=current["revision"])
    with pytest.raises(PermissionError, match="permitted listening content"):
        await action(queued, "queue_add", session=current["revision"], item=queued[2]["id"])
    saved["members"]["two"]["devices"] = []
    with pytest.raises(ValueError, match="available permitted"):
        await action(queued, "queue_join", session=current["revision"])
    assert not music.calls


async def test_two_simultaneous_profiles_cannot_append_using_the_same_stale_revision(queued):
    current = session(await view(queued))
    for person in ("two", None):
        await action(queued, "queue_join", person, session=current["revision"])
    results = await asyncio.gather(
        *(action(queued, "queue_add", person, session=current["revision"], item=queued[2]["id"]) for person in ("two", None)), return_exceptions=True
    )
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, ValueError) and "session changed" in str(result) for result in results) == 1
    assert len(queued[0][1].calls) == 1


@pytest.mark.parametrize("state", ["playing", "paused", "buffering"])
async def test_other_profiles_never_replace_occupied_queue_even_after_join(queued, state):
    music = queued[0][1]
    music.raw["a"]["playback_state"] = state
    music.queues["a"]["state"] = state
    await action(queued, "queue_join", session=session(await view(queued))["revision"])
    with pytest.raises(ValueError, match="already in use"):
        await action(queued, "play_item", item=queued[2]["id"])
    assert not music.calls


@pytest.mark.parametrize("state", ["paused", "buffering"])
async def test_unmanaged_occupied_playback_is_preserved(queued, state):
    runtime, music, house, _ = queued[0]
    data = runtime.load(house, music.conn)
    data["leases"].clear()
    runtime.save(data)
    music.raw["a"]["playback_state"] = state
    music.queues["a"]["state"] = state
    public = session(await view(queued))
    assert not public["can_join"] and not public["can_add"]
    with pytest.raises(ValueError, match="already in use"):
        await action(queued, "play_item", item=queued[2]["id"])
    assert not music.calls


@pytest.mark.parametrize("failure", ["feature", "version", "spotify_session", "progress_session", "spotify_item", "unavailable_source"])
async def test_unsupported_queue_actions_are_capability_checked_in_service(queued, monkeypatch, failure):
    runtime, music, house, _ = queued[0]
    snapshot = queued[1]
    item = queued[2]
    if failure == "feature":
        snapshot["players"][0]["features"] = []
    elif failure == "version":
        monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.10.6"}))
    elif failure in {"spotify_session", "progress_session"}:
        data = runtime.load(house, music.conn)
        if failure == "spotify_session":
            data["leases"]["a"]["native_session"] = "native-owned"
        else:
            data["leases"]["a"]["kind"] = "podcast_episode"
        runtime.save(data)
    elif failure == "spotify_item":
        item["sources"].append("spotify")
    elif failure == "unavailable_source":
        snapshot["providers"][0]["available"] = False
    current = session(await view(queued, "one"))
    if failure not in {"spotify_item", "unavailable_source"}:
        assert not current["can_add"]
    with pytest.raises((ValueError, PermissionError), match="not supported|cannot be added safely|source is private"):
        await action(queued, "queue_add", "one", session=current["revision"], item=item["id"])
    assert not music.calls


async def test_provider_read_failure_isolated_and_external_race_is_not_retried(queued, monkeypatch):
    runtime, music, _, _ = queued[0]
    original = music.command

    async def broken(endpoint, connection, name, **args):
        if name == "player_queues/items":
            raise MusicRuntimeError("Synthetic private provider detail")
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", broken)
    value = await view(queued)
    assert "private provider detail" not in str(value)
    assert "could not be checked" in session(value)["issue"]
    monkeypatch.setattr(music, "command", original)
    current = session(await view(queued, "one"))
    control = music.control

    async def racing(endpoint, connection, name, **args):
        await control(endpoint, connection, name, **args)
        queued[3].pop(0)  # native writer changed the queue while ADD was in flight

    monkeypatch.setattr(music, "control", racing)
    with pytest.raises(MusicRuntimeError):
        await action(queued, "queue_add", "one", session=current["revision"], item=queued[2]["id"])
    assert len(music.calls) == 1  # no automatic retry or rollback/replace


@pytest.mark.parametrize("change", ["source", "queue"])
async def test_fresh_metadata_cannot_redirect_append_or_hide_a_queue_change(queued, monkeypatch, change):
    music = queued[0][1]
    current = session(await view(queued, "one"))
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "music/item_by_uri":
            if change == "source":
                return {"media_type": "track", "provider": "spotify--unmapped", "item_id": "unexpected"}
            queued[3].append({"queue_item_id": "concurrent-item", "name": "Other addition"})
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    with pytest.raises(ValueError, match="source changed|session changed"):
        await action(queued, "queue_add", "one", session=current["revision"], item=queued[2]["id"])
    assert not music.calls


async def test_library_selection_is_pinned_to_non_spotify_source_before_append(queued):
    queued[2]["uri"] = "library://track/logical-selection"
    current = session(await view(queued, "one"))
    await action(queued, "queue_add", "one", session=current["revision"], item=queued[2]["id"])
    assert queued[0][1].calls[0][1]["media"] == "fixture_local://track/one"


async def test_queue_view_never_publishes_delivery_urls_or_native_payload(queued):
    queued[3].append(
        {"queue_item_id": "private-native-id", "name": "https://fixture.invalid/delivery", "streamdetails": {"url": "https://fixture.invalid/audio"}}
    )
    public = session(await view(queued))
    assert public["queue"][-1]["title"] == "Queued audio" and public["queue"][-1]["current"] is False
    assert "fixture.invalid" not in str(public) and "private-native-id" not in str(public)


def upcoming(queued):
    runtime, music, house, _ = queued[0]
    rows = queued[3]
    for key in ("upcoming-one", "upcoming-two"):
        rows.append({"queue_item_id": key, "name": key, "media_item": deepcopy(rows[0]["media_item"])})
    data = runtime.load(house, music.conn)
    data["leases"]["a"]["queue_items"] = [r["queue_item_id"] for r in rows]
    runtime.save(data)


async def test_owner_move_remove_and_play_next_preserve_current_and_profile(queued):
    upcoming(queued)
    music = queued[0][1]
    initial = deepcopy(music.raw["a"])
    current = session(await view(queued, "one"))
    assert current["can_edit"] and current["can_next"]
    assert not current["queue"][0]["remove"] and not current["queue"][1]["up"]
    await action(queued, "queue_move", "one", session=current["revision"], entry=current["queue"][2]["entry"], value=-1)
    assert [r["queue_item_id"] for r in queued[3]] == ["old", "upcoming-two", "upcoming-one"]
    current = session(await view(queued, "one"))
    await action(queued, "queue_remove", "one", session=current["revision"], entry=current["queue"][2]["entry"])
    current = session(await view(queued, "one"))
    await action(queued, "queue_next", "one", session=current["revision"], item=queued[2]["id"])
    assert [r["queue_item_id"] for r in queued[3]] == ["old", "added-2", "upcoming-two"]
    assert music.raw["a"] == initial
    assert session(await view(queued, "one"))["owner"] == "Example one"


@pytest.mark.parametrize("failure", ["current", "buffered", "stale", "participant", "version", "buffering", "unknown-buffer", "shuffle"])
async def test_queue_edits_fail_closed_on_ownership_version_or_committed_items(queued, monkeypatch, failure):
    upcoming(queued)
    music = queued[0][1]
    person = "one"
    if failure == "participant":
        person = "two"
        current = session(await view(queued))
        await action(queued, "queue_join", session=current["revision"])
    elif failure == "version":
        monkeypatch.setattr(music, "endpoint", AsyncMock(return_value={"version": "2.11.0"}))
    elif failure == "buffering":
        music.queues["a"]["state"] = "buffering"
    elif failure == "unknown-buffer":
        music.queues["a"].pop("index_in_buffer")
    elif failure == "shuffle":
        music.queues["a"]["shuffle_enabled"] = True
    elif failure == "buffered":
        music.queues["a"]["index_in_buffer"] = 1
    current = session(await view(queued, person))
    selected = current["queue"][0 if failure == "current" else 1]
    revision = "stale" if failure == "stale" else current["revision"]
    with pytest.raises((ValueError, MusicRuntimeError)):
        await action(queued, "queue_remove", person, session=revision, entry=selected["entry"])
    assert not music.calls


async def test_takeover_requires_fresh_explicit_confirmation_and_never_copies_progress(queued):
    upcoming(queued)
    runtime, music, house, _ = queued[0]
    data = runtime.load(house, music.conn)
    saved_book = {"id": "fictional-book", "title": "Synthetic book", "kind": "audiobook", "duration": 3600}
    data["profiles"]["person:one"]["books"] = {"fictional-book": {**saved_book, "position": 123}}
    data["profiles"]["person:one"]["sleep"] = {"player_id": "a", "session": "fixture-session", "at": time.time() + 500}
    runtime.profile(data, "two")["books"] = {"fictional-book": {**saved_book, "position": 907}}
    runtime.save(data)
    current = session(await view(queued))
    with pytest.raises(ValueError, match="confirm takeover"):
        await action(queued, "queue_takeover", session=current["revision"])
    await action(queued, "queue_takeover_prepare", session=current["revision"])
    prepared = await view(queued)
    confirmation = prepared["takeover"]["confirmation"]
    assert session(prepared)["owner"] == "Example one" and not music.calls
    await action(queued, "queue_takeover", session=current["revision"], confirmation=confirmation)
    result = runtime.load(house, music.conn)
    assert result["leases"]["a"]["scope"] == "person:two"
    assert result["leases"]["a"]["session"] != "fixture-session"
    assert "sleep" not in result["profiles"]["person:one"]
    assert result["profiles"]["person:one"]["books"]["fictional-book"]["position"] == 123
    assert result["profiles"]["person:two"]["books"]["fictional-book"]["position"] == 907
    assert not music.calls


@pytest.mark.parametrize("change", ["queue", "expired", "owner", "progress", "spotify", "child"])
async def test_takeover_rejects_stale_or_unsupported_targets(queued, change):
    upcoming(queued)
    runtime, music, house, saved = queued[0]
    current = session(await view(queued))
    await action(queued, "queue_takeover_prepare", session=current["revision"])
    data = runtime.load(house, music.conn)
    confirmation = data["profiles"]["person:two"]["takeover"]["confirmation"]
    if change == "queue":
        queued[3].reverse()
    elif change == "expired":
        data["profiles"]["person:two"]["takeover"]["expires"] = 0
    elif change == "owner":
        data["leases"]["a"]["session"] = "new-owner-session"
    elif change == "progress":
        data["leases"]["a"]["kind"] = "podcast_episode"
    elif change == "spotify":
        data["leases"]["a"]["native_session"] = "native-owned"
    elif change == "child":
        saved["members"]["two"] = {"kind": "child", "rooms": [], "devices": ["a"]}
    runtime.save(data)
    with pytest.raises((ValueError, PermissionError, MusicRuntimeError)):
        await action(queued, "queue_takeover", session=current["revision"], confirmation=confirmation)
    assert not music.calls


async def test_concurrent_takeover_confirmations_change_only_one_household_owner(queued):
    upcoming(queued)
    confirmations = {}
    current = session(await view(queued))
    for person in ("two", None):
        await action(queued, "queue_takeover_prepare", person, session=current["revision"])
        confirmations[person] = (await view(queued, person))["takeover"]["confirmation"]
    results = await asyncio.gather(
        *(action(queued, "queue_takeover", person, session=current["revision"], confirmation=confirmations[person]) for person in ("two", None)),
        return_exceptions=True,
    )
    assert sum(r is None for r in results) == 1
    assert sum(isinstance(r, ValueError) for r in results) == 1
    assert not queued[0][1].calls


@pytest.mark.parametrize("operation", ["queue_next", "queue_move", "queue_remove"])
async def test_uncertain_queue_edit_is_not_retried_and_stale_retry_cannot_repeat_it(queued, monkeypatch, operation):
    upcoming(queued)
    music = queued[0][1]
    current = session(await view(queued, "one"))
    extra = (
        {"item": queued[2]["id"]}
        if operation == "queue_next"
        else {"entry": current["queue"][1]["entry"], **({"value": 1} if operation == "queue_move" else {})}
    )
    original = music.control

    async def uncertain(*args, **kwargs):
        await original(*args, **kwargs)
        raise MusicRuntimeError("Queue result could not be confirmed. Refresh before retrying.")

    monkeypatch.setattr(music, "control", uncertain)
    with pytest.raises(MusicRuntimeError, match="not be confirmed"):
        await action(queued, operation, "one", session=current["revision"], **extra)
    with pytest.raises(ValueError, match="session changed"):
        await action(queued, operation, "one", session=current["revision"], **extra)
    assert len(music.calls) == 1


async def test_takeover_selects_new_owned_room_without_moving_another_room_timer(queued):
    upcoming(queued)
    runtime, music, house, _ = queued[0]
    data = runtime.load(house, music.conn)
    data["leases"]["b"] = {**deepcopy(data["leases"]["a"]), "scope": "person:two", "session": "other-room"}
    runtime.profile(data, "two")["sleep"] = {"player_id": "b", "session": "other-room", "at": time.time() + 500}
    music.raw["b"].update(playback_state="playing", current_media={"queue_item_id": "old"})
    music.queues["b"].update(state="playing", current_item=deepcopy(music.queues["a"]["current_item"]))
    runtime.save(data)
    current = session(await view(queued))
    await action(queued, "queue_takeover_prepare", session=current["revision"])
    confirmation = (await view(queued))["takeover"]["confirmation"]
    await action(queued, "queue_takeover", session=current["revision"], confirmation=confirmation)
    result = await view(queued)
    assert result["session"]["player_id"] == "a" and result["sleep"] is None
    assert runtime.load(house, music.conn)["profiles"]["person:two"]["sleep"]["player_id"] == "b"
    assert not music.calls


async def test_queue_view_and_now_playing_follow_native_current_item_without_title_deduplication(queued):
    upcoming(queued)
    runtime, music, house, _ = queued[0]
    queued[3][1]["name"] = "Another synthetic song"
    queued[3][2]["name"] = "Another synthetic song"
    music.raw["a"]["current_media"] = {"queue_item_id": "upcoming-one"}
    music.queues["a"].update(current_index=1, index_in_buffer=1, current_item=deepcopy(queued[3][1]))
    result = await view(queued, "one")
    assert result["session"]["title"] == "Another synthetic song"
    assert len(session(result)["queue"]) == 3
    assert sum(row["title"] == "Another synthetic song" for row in session(result)["queue"]) == 2
    assert runtime.load(house, music.conn)["profiles"]["person:one"]["books"] == {}
