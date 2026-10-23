"""Synthetic combined metadata never grants a personal playback identity."""

from unittest.mock import AsyncMock

import pytest
from homestarter.household_music import collection_access, reconcile, source_access, visible
from homestarter.listening import ListeningRuntime, media_record
from homestarter.listening_collections import Collections, folder, merge, selection

PROVIDERS = [
    {"id": "fixture_" + key, "domain": "spotify", "name": name, "available": True, "enabled": True}
    for key, name in (("grant", "Grant"), ("house", "House"), ("house2", "House #2"))
]
CONNECTION = {"server_id": "fictional", "generation": 1}


def item(key, provider="fixture_house", title="Same title", kind="playlist"):
    return {
        "item_id": key,
        "provider": provider,
        "media_type": kind,
        "name": title,
        "uri": provider + "://" + kind + "/" + key,
        "provider_mappings": [{"provider_domain": "spotify", "provider_instance": provider, "item_id": key, "available": True}],
    }


def test_exact_spotify_identity_merges_accounts_without_merging_titles():
    rows = merge([item("shared"), item("shared", "fixture_grant"), item("different")], "playlist")
    assert len(rows) == 2
    shared = next(r for r in rows if r["item_id"] == "shared")
    assert {m["provider_instance"] for m in shared["provider_mappings"]} == {"fixture_house", "fixture_grant"}
    assert shared["household_collection"]


def test_shared_collection_metadata_does_not_change_personal_playback_access():
    private = media_record(item("private", "fixture_grant"))
    assert not visible(private, "House", PROVIDERS)
    combined = media_record({**item("private", "fixture_grant"), "household_collection": True})
    assert visible(combined, "House", PROVIDERS)
    assert visible(combined, "Edie", PROVIDERS)
    assert "fixture_grant" not in source_access("House", PROVIDERS)
    assert "fixture_grant" not in source_access("Edie", PROVIDERS)
    assert source_access("Grant", PROVIDERS) == ["fixture_grant"]
    unknown = {"id": "unknown_account", "name": "Unrecognised", "domain": "spotify", "available": True}
    assert not visible({**combined, "sources": ["unknown_account"]}, "House", [*PROVIDERS, unknown])
    assert set(collection_access(PROVIDERS)) == {p["id"] for p in PROVIDERS}


@pytest.mark.asyncio
async def test_native_collection_sharing_preserves_users_and_is_idempotent():
    from copy import deepcopy

    users = [{"user_id": name.lower(), "display_name": name, "provider_filter": []} for name in ("Grant", "Renae", "Edie", "Maddie", "Flynn", "House")]
    updates = []

    async def command(name, **args):
        if name == "auth/users":
            return deepcopy(users)
        assert name == "auth/user/update"
        next(u for u in users if u["user_id"] == args["user_id"])["provider_filter"] = args["provider_filter"]
        updates.append(args["user_id"])

    status = await reconcile(command, PROVIDERS, share_collections=True)
    assert status["users"] == 6 and status["connected"] == 3 and status["pending"] == 1
    assert all(set(u["provider_filter"]) == {p["id"] for p in PROVIDERS} for u in users)
    assert len(updates) == 6
    await reconcile(command, PROVIDERS, share_collections=True)
    assert len(updates) == 6
    assert source_access("Grant", PROVIDERS) == ["fixture_grant"]
    assert "fixture_grant" not in source_access("House", PROVIDERS)


@pytest.mark.asyncio
async def test_all_connected_accounts_contribute_and_pages_preserve_every_item():
    async def command(endpoint, connection, name, **args):
        if name.endswith("library_items"):
            return [item(str(n)) for n in range(86)]
        if args["path"].endswith("://"):
            return [{"media_type": "folder", "item_id": "playlists", "path": args["path"] + "playlists"}]
        provider = args["path"].split("://")[0]
        return [item("shared", provider), item(provider + "-only", provider)]

    runtime = type("Runtime", (), {"command": AsyncMock(side_effect=command)})()
    collections = Collections(runtime)
    first, incomplete, count = await collections.page("endpoint", CONNECTION, folder("playlists")["path"], PROVIDERS)
    assert not incomplete and count == 90
    assert len(first) == 61 and first[-1]["continuation"]
    second, incomplete, same_count = await collections.page("endpoint", CONNECTION, first[-1]["path"], PROVIDERS)
    assert not incomplete and same_count == count and len(second) == 30
    assert len({r["uri"] for r in [*first[:-1], *second]}) == 90
    paths = [c.kwargs.get("path", "") for c in runtime.command.call_args_list]
    assert all(provider["id"] + "://playlists" in paths for provider in PROVIDERS)
    assert not any("renae" in path for path in paths)


@pytest.mark.asyncio
async def test_failed_account_is_explicitly_incomplete_and_search_is_media_scoped():
    async def command(endpoint, connection, name, **args):
        if name == "music/search":
            pytest.fail("Saved collection filtering must not use unqualified provider/library search")
        if name.endswith("library_items"):
            return [item("saved", kind="podcast")]
        raise RuntimeError("Synthetic upstream failure")

    collections = Collections(type("Runtime", (), {"command": AsyncMock(side_effect=command)})())
    rows, incomplete, count = await collections.page("endpoint", CONNECTION, folder("podcasts")["path"], PROVIDERS)
    assert incomplete and count == 1
    rows, incomplete, count = await collections.page("endpoint", CONNECTION, folder("podcasts")["path"], PROVIDERS, "Same title")
    assert incomplete and count == 1 and rows[0]["media_type"] == "podcast"


@pytest.mark.asyncio
async def test_listening_root_uses_buckets_instead_of_spotify_account_folders(tmp_path):
    runtime = type(
        "Runtime",
        (),
        {
            "command": AsyncMock(
                return_value=[
                    {"media_type": "folder", "name": "Grant", "provider": "spotify", "path": "fixture_grant://"},
                    {"media_type": "folder", "name": "Radio source", "provider": "fictional_radio", "path": "fictional_radio://"},
                ]
            )
        },
    )()
    store = type("Store", (), {"path": str(tmp_path / "house.json")})()
    listening = ListeningRuntime(runtime, None, store)
    rows = await listening.catalog_items("endpoint", CONNECTION, providers=PROVIDERS)
    assert "Playlists" in {r["title"] for r in rows} and "Podcasts" in {r["title"] for r in rows}
    assert "Grant" not in {r["title"] for r in rows}
    assert "Radio source" in {r["title"] for r in rows}
    assert selection(folder("playlists", 60)["path"]) == ("playlists", 60)
    assert selection("https://untrusted.example") is None


@pytest.mark.asyncio
async def test_long_episode_lists_are_paged_without_losing_or_persisting_payloads(tmp_path):
    episodes = [item(str(n), kind="podcast_episode") for n in range(157)]
    runtime = type("Runtime", (), {"command": AsyncMock(return_value=episodes)})()
    store = type("Store", (), {"path": str(tmp_path / "house.json")})()
    listening = ListeningRuntime(runtime, None, store)
    rows = await listening.catalog_items("endpoint", CONNECTION)
    seen = [r["id"] for r in rows if not r["folder"]]
    while rows[-1].get("continuation"):
        rows = await listening.catalog_items("endpoint", CONNECTION, folder=rows[-1]["id"])
        seen.extend(r["id"] for r in rows if not r["folder"])
    assert len(seen) == len(set(seen)) == 157
    runtime.command.assert_awaited_once()
    assert not list(tmp_path.iterdir())
