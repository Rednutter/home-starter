import json
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import media_preview
from homestarter.music_runtime import MusicRuntimeError
from homestarter.server import K_STATE, create_app
from test_media_preview import preview_state as state_fixture


@pytest.fixture
def preview_state(tmp_path, monkeypatch):
    return state_fixture.__wrapped__(tmp_path, monkeypatch)


async def open_known(state, surface):
    service = media_preview.PreviewService(state)
    identity, bootstrap = await service.open("example-admin", surface["id"])
    assert bootstrap["compatibility"]["features"]["profile_filter_contract"]
    return service, identity


@pytest.mark.asyncio
async def test_known_identity_checkpoint_survives_restart_for_unknown_read_contract(preview_state):
    state, surface, _ = preview_state
    await open_known(state, surface)
    checkpoint = state.household.path.parent / "music-read-bindings.json"
    before = checkpoint.read_bytes()
    assert set(json.loads(before)) == {"protocol", "binding", "profiles"}
    assert "token" not in before.decode() and "Example One" not in before.decode()
    state.music_runtime.endpoint.return_value["version"] = "2.10.8"
    service = media_preview.PreviewService(state)
    identity, bootstrap = await service.open("example-admin", surface["id"])
    assert not bootstrap["compatibility"]["reviewed_version"]
    assert bootstrap["compatibility"]["features"]["catalogue_read_contract"]
    assert not bootstrap["compatibility"]["features"]["protected_spotify"]
    assert bootstrap["compatibility"]["control_review_required"]
    with pytest.raises(ValueError, match="playback controls need compatibility review"):
        await service.selection(identity, "example-admin", {"profile": "house", "selection": "not-offered"})
    assert checkpoint.read_bytes() == before
    assert service.sessions[identity]["metadata"].user_bindings == {"house": "house", "one": "one"}
    state.music_runtime.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_release_without_checkpoint_is_probed_but_not_admitted(preview_state):
    state, surface, _ = preview_state
    state.music_runtime.endpoint.return_value["version"] = "3.0.0"
    with pytest.raises(MusicRuntimeError, match="verified profile identities"):
        await media_preview.PreviewService(state).open("example-admin", surface["id"])
    assert "auth/users" in state.calls and "music/artists/library_items" in state.calls
    assert not (state.household.path.parent / "music-read-bindings.json").exists()
    state.music_runtime.control.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["renamed", "replaced", "empty-filter"])
async def test_ids_not_names_control_identity_and_empty_filters_do_not_expand(preview_state, change):
    state, surface, _ = preview_state
    await open_known(state, surface)
    original = state.music_runtime.command

    async def command(endpoint, connection, name, **args):
        rows = await original(endpoint, connection, name, **args)
        if name == "auth/users":
            rows[1] = {**rows[1]}
            if change == "renamed":
                rows[1]["display_name"] = "Renamed native user"
            elif change == "replaced":
                rows[1]["user_id"] = "different-native-user"
            else:
                rows[1]["provider_filter"] = []
        return rows

    state.music_runtime.command = command
    state.music_runtime.endpoint.return_value["version"] = "2.10.8"
    service, identity = await open_known(state, surface)
    body = {"profile": "one", "generation": 1, "command": "music/artists/library_items", "args": {}}
    if change == "renamed":
        assert await service.read(identity, "example-admin", body) == []
    else:
        with pytest.raises(PermissionError):
            await service.read(identity, "example-admin", body)
    state.music_runtime.control.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["version", "schema_version", "server_id"])
async def test_changed_server_contract_revokes_old_context_without_replaying(preview_state, change):
    state, surface, _ = preview_state
    service, identity = await open_known(state, surface)
    state.music_runtime.endpoint.return_value[change] = 32 if change == "schema_version" else "changed"
    before = len(state.calls)
    with pytest.raises(PermissionError):
        await service.read(identity, "example-admin", {"profile": "house", "generation": 1, "command": "household/recent", "args": {}})
    assert identity not in service.sessions and len(state.calls) == before
    state.music_runtime.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_corrupt_checkpoint_is_not_silently_recreated(preview_state):
    state, surface, _ = preview_state
    checkpoint = state.household.path.parent / "music-read-bindings.json"
    checkpoint.write_text('{"protocol":true,"binding":"wrong","profiles":{}}')
    before = checkpoint.read_bytes()
    with pytest.raises(MusicRuntimeError, match="administrator review"):
        await media_preview.PreviewService(state).open("example-admin", surface["id"])
    assert checkpoint.read_bytes() == before


@pytest.mark.asyncio
async def test_library_failure_does_not_block_independent_discovery(preview_state):
    state, surface, _ = preview_state
    original = state.music_runtime.command

    async def command(endpoint, connection, name, **args):
        if name == "music/artists/library_items":
            raise RuntimeError("Synthetic library unavailable")
        return await original(endpoint, connection, name, **args)

    state.music_runtime.command = command
    service = media_preview.PreviewService(state)
    identity, bootstrap = await service.open("example-admin", surface["id"])
    assert bootstrap["compatibility"]["features"]["profile_filter_contract"]
    assert not bootstrap["compatibility"]["features"]["catalogue_read_contract"]
    body = {"profile": "house", "generation": 1, "command": "household/discovery", "args": {"category": "radio", "query": ""}}
    assert (await service.read(identity, "example-admin", body))["items"] == []
    with pytest.raises(ValueError, match="Library format"):
        await service.read(identity, "example-admin", {**body, "command": "music/artists/library_items", "args": {}})


async def test_diagnostics_use_existing_admin_boundary_without_snapshot_or_controls(make_env, monkeypatch):
    env = await make_env("ready", fresh=True)
    async with TestClient(TestServer(create_app(env.settings, env.session))) as client:
        runtime = client.app[K_STATE].music_runtime
        diagnostic = AsyncMock(return_value={"protocol": 1, "authorizes_playback": False})
        monkeypatch.setattr(runtime, "read_compatibility", diagnostic)
        monkeypatch.setattr(runtime, "snapshot", AsyncMock(side_effect=AssertionError("No unrelated snapshot")))
        monkeypatch.setattr(runtime, "control", AsyncMock(side_effect=AssertionError("No controls")))
        assert (await client.get("/api/music/runtime?compatibility=1")).status == 403
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        response = await client.get("/api/music/runtime?compatibility=1", headers=headers)
        assert response.status == 200 and not (await response.json())["authorizes_playback"]
        diagnostic.assert_awaited_once()
        runtime.control.assert_not_awaited()
