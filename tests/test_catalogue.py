"""Synthetic native-source aggregation and profile-bound discovery contracts."""

import asyncio
from copy import deepcopy

import pytest
from homestarter import catalogue as discovery
from homestarter.music_runtime import MusicRuntimeError
from test_listening import setup as setup
from test_listening_stations import catalogue as catalogue
from test_stations import track


@pytest.fixture
async def scoped(catalogue, monkeypatch):
    runtime, music, house, _ = catalogue[0]
    snapshot = await music.snapshot()
    snapshot["providers"][0]["domain"] = "qobuz"
    snapshot["providers"].append({"id": "fixture_second", "domain": "qobuz", "available": True, "features": ["search", "library_tracks"]})
    for player in snapshot["players"]:
        player["features"] = ["play_media"]
    users = [
        {"user_id": "native-" + p, "display_name": n, "provider_filter": ids}
        for p, n, ids in (
            ("one", "Example one", ["fixture_catalogue", "fixture_second"]),
            ("two", "Example two", ["fixture_second"]),
            ("house", "House", ["fixture_catalogue", "fixture_second"]),
        )
    ]
    rows = {"fixture_catalogue": [track("shared"), track("one")], "fixture_second": [track("shared"), track("two")]}
    calls = []
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "auth/users":
            return deepcopy(users)
        if name == "music/search":
            calls.append(deepcopy(args))
            assert len(args["providers"]) == 1 and args["providers"] != ["library"]
            actor = next(u for u in users if u["user_id"] == args["user"]["user_id"])
            assert args["user"]["required"] is True
            source = args["providers"][0]
            if source not in actor["provider_filter"]:
                raise MusicRuntimeError("Forbidden native source")
            values = []
            for value in rows[source]:
                value = deepcopy(value)
                value["provider"] = source
                value["provider_mappings"][0]["provider_instance"] = source
                values.append(value)
            return {"tracks": values}
        if name == "music/item_by_uri":
            source, rest = args["uri"].split("://", 1)
            return {"provider": source, "item_id": rest.split("/", 1)[1], "media_type": "track"}
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    return catalogue, snapshot, users, rows, calls


async def access(scoped, person="one"):
    runtime, music, house, _ = scoped[0][0]
    return await discovery.policy(music, await music.endpoint(), music.conn, house, person, scoped[1]["providers"])


async def test_aggregates_only_assigned_sources_deduplicates_ids_not_titles(scoped):
    runtime, music, _, _ = scoped[0][0]
    for values in scoped[3].values():
        for row in values:
            row["name"] = "Same title"
    result = await discovery.search(music, await music.endpoint(), music.conn, "Example", scoped[1]["providers"], await access(scoped))
    assert len(result["items"]) == 3
    shared = next(r for r in result["items"] if r["item_id"] == "shared")
    assert {m["provider_instance"] for m in shared["provider_mappings"]} == {"fixture_catalogue", "fixture_second"}
    assert len(scoped[4]) == 2 and not music.calls
    second = await runtime.view("admin", "panel", "two", query="Example")
    assert len(second["library"]) == 2
    assert all(c["providers"] == ["fixture_second"] for c in scoped[4] if c["user"]["user_id"] == "native-two")


@pytest.mark.parametrize("failure", ["slow", "offline", "denied"])
async def test_one_bad_source_does_not_hide_healthy_results_or_fall_back(scoped, monkeypatch, failure):
    music = scoped[0][0][1]
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "music/search" and args["providers"] == ["fixture_catalogue"]:
            if failure == "slow":
                await asyncio.sleep(0.2)
            else:
                raise MusicRuntimeError("Synthetic private upstream detail")
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    result = await discovery.search(music, await music.endpoint(), music.conn, "Example", scoped[1]["providers"], await access(scoped), timeout=0.02)
    assert len(result["items"]) == 2 and result["incomplete"]
    assert any(s["state"] == ("timed_out" if failure == "slow" else "unavailable") for s in result["sources"])
    assert "private upstream detail" not in str(result)
    assert not music.calls


@pytest.mark.parametrize("failure", ["empty", "missing", "deleted", "duplicate", "disabled"])
async def test_bad_profile_assignments_fail_closed_before_any_source_search(scoped, failure):
    runtime, _, _, _ = scoped[0][0]
    if failure == "empty":
        scoped[2][0]["provider_filter"] = []
    elif failure == "missing":
        scoped[2][0].pop("provider_filter")
    elif failure == "deleted":
        scoped[2][0]["provider_filter"] = ["removed-source"]
    elif failure == "duplicate":
        scoped[2].append(deepcopy(scoped[2][0]))
    else:
        scoped[2][0]["enabled"] = False
    with pytest.raises(MusicRuntimeError, match="assignments need review"):
        await access(scoped)
    value = await runtime.view("admin", "panel", "one", query="Example")
    assert not value["library"] and value["search"]["incomplete"]
    assert not scoped[4]


async def test_profile_switch_and_source_change_during_search_cannot_publish_old_results(scoped, monkeypatch):
    runtime, music, _, _ = scoped[0][0]
    entered, release = asyncio.Event(), asyncio.Event()
    original = music.command

    async def command(endpoint, connection, name, **args):
        if name == "music/search" and args["providers"] == ["fixture_catalogue"]:
            entered.set()
            await release.wait()
        return await original(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    pending = asyncio.create_task(runtime.view("admin", "panel", "one", query="Example"))
    await asyncio.wait_for(entered.wait(), 2)
    second = await asyncio.wait_for(runtime.view("admin", "panel", "two", query="Example"), 2)
    assert second["person_id"] == "two" and len(second["library"]) == 2
    scoped[2][0]["provider_filter"] = ["fixture_second"]
    release.set()
    first = await pending
    assert not first["library"] and "changed" in first["search"]["issue"]


async def test_profile_bound_result_ids_and_pages_cannot_be_reused_across_profiles(scoped):
    runtime, music, house, _ = scoped[0][0]
    scoped[2][0]["provider_filter"] = ["fixture_second"]
    scoped[3]["fixture_second"] = [track(str(i)) for i in range(75)]
    first = await runtime.view("admin", "panel", "one", query="Example")
    second = await runtime.view("admin", "panel", "two", query="Example")
    assert first["library"][0]["id"] != second["library"][0]["id"]
    more = next(r for r in first["library"] if r.get("continuation"))
    with pytest.raises(PermissionError, match="different or changed profile"):
        await runtime.view("admin", "panel", "two", folder=more["id"])
    with pytest.raises(PermissionError, match="different or changed profile"):
        await runtime.action("admin", "panel", "two", {"epoch": house["epoch"], "action": "favorite", "item": first["library"][0]["id"]})
    assert not music.calls


async def test_scoped_play_requires_native_user_and_filter_revocation_prevents_transport(scoped):
    runtime, music, house, _ = scoped[0][0]
    result = await runtime.view("admin", "panel", "one", query="Example")
    item = result["library"][0]["id"]
    await runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "play_item", "item": item, "player": "media_player.a"})
    assert music.calls[0][1]["user"] == {"provider": "builtin", "user_id": "native-one", "required": True}
    scoped[2][0]["provider_filter"] = []
    music.calls.clear()
    with pytest.raises(MusicRuntimeError):
        await runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "play_item", "item": item, "player": "media_player.b"})
    assert not music.calls


async def test_spotify_and_raw_forbidden_mappings_never_become_fallback_sources(scoped):
    music = scoped[0][0][1]
    for name in ("Grant", "Renae", "House", "House #2"):
        scoped[1]["providers"].append({"id": "fixture_spotify_" + name, "domain": "spotify", "available": True, "features": ["search"]})
        scoped[2][0]["provider_filter"].append("fixture_spotify_" + name)
    scoped[3]["fixture_catalogue"][0]["provider_mappings"].append(
        {"provider_instance": "forbidden-source", "provider_domain": "private", "item_id": "leak", "available": True}
    )
    result = await discovery.search(music, await music.endpoint(), music.conn, "Example", scoped[1]["providers"], await access(scoped))
    assert result["incomplete"] and "Spotify" in result["issue"]
    assert "forbidden-source" not in str(result["items"])
    assert all(not c["providers"][0].startswith("fixture_spotify") for c in scoped[4])


async def test_station_proposals_use_multiple_assigned_sources_without_play_history(scoped):
    runtime, music, house, _ = scoped[0][0]
    await runtime.action(
        "admin", "panel", "one", {"epoch": house["epoch"], "action": "station_save", "settings": {"name": "Example", "seeds": ["Example"], "artist_gap": 0}}
    )
    identifier = (await runtime.view("admin", "panel", "one"))["stations"]["recipes"][0]["id"]
    await runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "station_preview", "station": identifier})
    result = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert len(result["station_history"]) == 3 and all(r["kind"] == "proposed" for r in result["station_history"])
    assert not result["recent"] and not result["books"] and not music.calls
    assert {c["providers"][0] for c in scoped[4]} == {"fixture_catalogue", "fixture_second"}


async def test_instance_local_ids_are_not_mistaken_for_global_catalogue_identity(scoped):
    music = scoped[0][0][1]
    for p in scoped[1]["providers"]:
        p["domain"] = "filesystem_local"
    result = await discovery.search(music, await music.endpoint(), music.conn, "Example", scoped[1]["providers"], await access(scoped))
    assert len(result["items"]) == 4


@pytest.mark.parametrize("state", ["offline", "unsupported"])
async def test_unqueried_sources_are_reported_incomplete_without_blocking_others(scoped, state):
    music = scoped[0][0][1]
    if state == "offline":
        scoped[1]["providers"][0]["available"] = False
    else:
        scoped[1]["providers"][0]["features"] = []
    result = await discovery.search(music, await music.endpoint(), music.conn, "Example", scoped[1]["providers"], await access(scoped))
    assert len(result["items"]) == 2 and result["incomplete"]
    assert len(scoped[4]) == 1 and scoped[4][0]["providers"] == ["fixture_second"]


async def test_person_bound_screen_cannot_escape_to_house_or_another_profile(scoped):
    runtime, _, house, _ = scoped[0][0]
    house["surfaces"][0]["person_id"] = "two"
    runtime.store.save(house)
    bootstrap = await runtime.bootstrap("admin")
    assert bootstrap["surfaces"][0]["person_id"] == "two"
    for person in (None, "one"):
        with pytest.raises(PermissionError, match="specific listening profile"):
            await runtime.view("admin", "panel", person, query="Example")
    assert not scoped[4]
    result = await runtime.view("admin", "panel", "two", query="Example")
    assert result["bound_profile"] == "two" and len(result["profiles"]) == 1


async def test_revoked_mapping_hides_saved_discovery_and_preview_without_deleting_state(scoped):
    runtime, music, house, _ = scoped[0][0]
    result = await runtime.view("admin", "panel", "one", query="Example")
    await runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "favorite", "item": result["library"][0]["id"]})
    await runtime.action(
        "admin", "panel", "one", {"epoch": house["epoch"], "action": "station_save", "settings": {"name": "Example", "seeds": ["Example"], "artist_gap": 0}}
    )
    identifier = (await runtime.view("admin", "panel", "one"))["stations"]["recipes"][0]["id"]
    await runtime.action("admin", "panel", "one", {"epoch": house["epoch"], "action": "station_preview", "station": identifier})
    scoped[2][0]["provider_filter"] = []
    hidden = await runtime.view("admin", "panel", "one")
    assert not hidden["favorites"] and hidden["stations"]["preview"] is None
    stored = runtime.load(house, music.conn)["profiles"]["person:one"]
    assert stored["favorites"] and stored["station_previews"] and not music.calls


async def test_joined_append_retains_owner_native_context_and_scoped_takeover_stays_unavailable(scoped, monkeypatch):
    runtime, music, house, _ = scoped[0][0]
    first = await runtime.view("admin", "panel", "one", query="Example")
    await runtime.action(
        "admin", "panel", "one", {"epoch": house["epoch"], "action": "play_item", "player": "media_player.a", "item": first["library"][0]["id"]}
    )
    rows = [deepcopy(music.queues["a"]["current_item"])]
    original_command, original_control = music.command, music.control

    async def command(endpoint, connection, name, **args):
        if name == "player_queues/items":
            return deepcopy(rows)
        return await original_command(endpoint, connection, name, **args)

    async def control(endpoint, connection, name, **args):
        if name == "player_queues/play_media" and args.get("option") == "add":
            music.calls.append((name, args))
            rows.append({"queue_item_id": "new-scoped-item", "name": "New scoped song"})
            return
        await original_control(endpoint, connection, name, **args)

    monkeypatch.setattr(music, "command", command)
    monkeypatch.setattr(music, "control", control)
    second = await runtime.view("admin", "panel", "two", query="Example")
    target = next(s for s in second["sessions"] if s["player_id"] == "a")
    assert target["source_scoped"] and not target["can_takeover"]
    with pytest.raises(ValueError, match="profile-scoped"):
        await runtime.action(
            "admin", "panel", "two", {"epoch": house["epoch"], "action": "queue_takeover_prepare", "player": "media_player.a", "session": target["revision"]}
        )
    await runtime.action("admin", "panel", "two", {"epoch": house["epoch"], "action": "queue_join", "player": "media_player.a", "session": target["revision"]})
    await runtime.action(
        "admin",
        "panel",
        "two",
        {"epoch": house["epoch"], "action": "queue_add", "player": "media_player.a", "session": target["revision"], "item": second["library"][0]["id"]},
    )
    assert music.calls[-1][1]["user"] == {"provider": "builtin", "user_id": "native-one", "required": True}
    assert runtime.load(house, music.conn)["leases"]["a"]["scope"] == "person:one"
