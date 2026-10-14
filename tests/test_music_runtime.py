"""Real HTTP read contracts, credential preservation and honest scoped proof."""

import copy
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter.music_runtime import READ_COMMANDS, MusicRuntime, MusicRuntimeError, private_write
from homestarter.server import K_STATE, create_app
from mock_music_runtime import TOKEN


async def runtime_for(make_env):
    env = await make_env("ready")
    runtime = MusicRuntime(env.supervisor, env.session, env.settings.data_dir, env.ma_port)
    runtime.interval, runtime.samples = 0.01, 2
    await runtime.connect(TOKEN)
    return runtime, env


async def test_discovery_distinguishes_library_plugins_disabled_and_builtin(make_env):
    runtime, env = await runtime_for(make_env)
    result = await runtime.snapshot()
    providers = {p["id"]: p for p in result["providers"]}
    assert set(providers) == {"fixture_radio", "fixture_urls", "fixture_disabled"}
    assert providers["fixture_radio"]["status"] == "connected"
    assert providers["fixture_disabled"]["status"] == "disabled"
    assert providers["fixture_urls"]["builtin"]
    assert result["proof"] is None
    assert TOKEN not in json.dumps(result)
    assert all(command in READ_COMMANDS for command, _ in env.mock.music_api.calls)
    assert "Secret" in repr(runtime.connection()["token"]) and TOKEN not in repr(runtime.connection())


async def test_failed_connection_preserves_existing_token_and_no_identity_leak(make_env):
    runtime, env = await runtime_for(make_env)
    saved = runtime.connection_path.read_bytes()
    with pytest.raises(MusicRuntimeError, match="denied"):
        await runtime.connect("invalid-fixture-token")
    assert runtime.connection_path.read_bytes() == saved
    env.mock.server_info["server_id"] = "fixture-replacement-server"
    before = len(env.mock.music_api.calls)
    with pytest.raises(MusicRuntimeError, match="identity changed"):
        await runtime.snapshot()
    assert len(env.mock.music_api.calls) == before
    with pytest.raises(ValueError, match="only permits read"):
        await runtime.command({}, {}, "players/cmd/play")


async def test_configuration_denied_is_unknown_not_absent(make_env):
    runtime, env = await runtime_for(make_env)
    env.mock.music_api.config_status = 403
    result = await runtime.snapshot()
    assert result["configuration_known"] is False
    assert "fixture_radio" in {p["id"] for p in result["providers"]}
    assert "fixture_disabled" not in {p["id"] for p in result["providers"]}


async def test_decline_and_failed_recheck_preserve_prior_scoped_proof(make_env):
    runtime, env = await runtime_for(make_env)
    runtime.interval = 0.01
    original = runtime.sample

    async def advance(*args):
        value = await original(*args)
        env.mock.music_api.started -= 3
        return value

    runtime.sample = advance
    observed = await runtime.observe("fixture_radio", "fixture_speaker", "fixture-admin")
    await runtime.heard(observed["id"], "fixture-admin")
    saved = runtime.evidence()["verified"]
    pending = await runtime.observe("fixture_radio", "fixture_speaker", "fixture-admin")
    await runtime.decline(pending["id"], "fixture-admin")
    assert "pending" not in runtime.evidence()
    assert runtime.evidence()["verified"] == saved
    env.mock.music_api.progress = False
    with pytest.raises(MusicRuntimeError):
        await runtime.observe("fixture_radio", "fixture_speaker", "fixture-admin")
    assert runtime.evidence()["verified"] == saved
    await runtime.connect(TOKEN)
    assert (await runtime.snapshot())["proof"] is None


async def test_fresh_progress_and_hearing_required_then_expiry_health_and_reset_invalidate(make_env):
    runtime, env = await runtime_for(make_env)
    # Advance genuine raw feedback between reads without waiting in the suite.
    original = runtime.sample

    async def advance(*args):
        value = await original(*args)
        env.mock.music_api.started -= 3
        return value

    runtime.sample = advance
    observed = await runtime.observe("fixture_radio", "fixture_speaker", "fixture-admin")
    assert (await runtime.snapshot())["proof"] is None
    with pytest.raises(ValueError):
        await runtime.heard(observed["id"], "different-admin")
    await runtime.heard(observed["id"], "fixture-admin")
    assert (await runtime.snapshot())["proof"]["player_id"] == "fixture_speaker"
    saved = runtime.evidence()
    env.mock.music_api.player["available"] = False
    assert (await runtime.snapshot())["proof"] is None
    env.mock.music_api.player["available"] = True
    expired = copy.deepcopy(saved)
    expired["verified"]["at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    private_write(runtime.proof_path, expired)
    assert (await runtime.snapshot())["proof"] is None
    private_write(runtime.proof_path, saved)
    house = runtime.store.load()
    house["epoch"] += 1
    runtime.store.write(runtime.store.path, house)
    assert (await runtime.snapshot())["proof"] is None
    assert runtime.connection_path.exists()


@pytest.mark.parametrize("failure", ["static", "stale", "wrong_provider", "group", "wrong_item", "paused", "wrong_queue", "builtin"])
async def test_playing_labels_and_wrong_paths_cannot_pass(make_env, failure):
    runtime, env = await runtime_for(make_env)
    api = env.mock.music_api
    if failure in ("static", "stale"):
        api.progress = False
        if failure == "stale":
            api.timestamp = time.time() - 60
    if failure == "wrong_provider":
        api.queue["current_item"]["streamdetails"]["provider"] = "fixture_connect"
    if failure == "group":
        api.player["group_members"] = ["fixture_other"]
    if failure == "wrong_item":
        api.player["current_media"]["queue_item_id"] = "fixture_other_item"
    if failure == "paused":
        api.player["playback_state"] = "paused"
    if failure == "wrong_queue":
        api.queue["queue_id"] = "fixture_other"
    with pytest.raises(MusicRuntimeError):
        await runtime.observe("fixture_urls" if failure == "builtin" else "fixture_radio", "fixture_speaker", "fixture-admin")
    assert (await runtime.snapshot())["proof"] is None
    assert not runtime.proof_path.exists()


async def test_api_admin_pre_go_connection_and_secret_response_guard(make_env):
    env = await make_env("ready", fresh=True)
    async with TestClient(TestServer(create_app(env.settings, env.session))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/music/runtime")).status == 403
        response = await client.post("/api/music/runtime/connect", headers=headers, json={"token": TOKEN})
        assert response.status == 200, await response.text()
        assert TOKEN not in await response.text()
        assert not client.app[K_STATE].household.load()["configured"]
        env.mock.music_api.providers[0]["name"] = TOKEN
        env.mock.music_api.configured[0]["name"] = TOKEN
        response = await client.get("/api/music/runtime", headers=headers)
        assert response.status == 500
        assert TOKEN not in await response.text()


@pytest.mark.parametrize("value", [[], {"verified": []}, {"pending": "bad"}])
async def test_malformed_evidence_fails_closed(make_env, value):
    runtime, _ = await runtime_for(make_env)
    private_write(runtime.proof_path, value)
    with pytest.raises(MusicRuntimeError, match="unreadable"):
        await runtime.snapshot()
