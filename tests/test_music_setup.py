"""Fact gathering and the explicit direct-install flow against the contract mock."""

from __future__ import annotations

import pytest
from homestarter.music import MusicSetup, evaluate, gather_facts


async def state_of(env) -> dict:
    facts = await gather_facts(env.supervisor, env.core, env.session, ha_version="2026.10.1", ma_port=env.ma_port)
    return evaluate(facts)


def writes(env) -> list[tuple[str, str]]:
    return [(m, p) for m, p in env.mock.calls if m != "GET"]


async def run_setup(env, **kw) -> dict:
    setup = MusicSetup(env.supervisor, poll_interval=0, **kw)
    setup.start("user-1")
    await setup.wait()
    return setup.snapshot()


# ---- detection against the mock ---------------------------------------------


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        ("no_repo", "not_in_store"),
        ("absent", "available"),
        ("unavailable", "unsupported"),
        ("installed_stopped", "stopped"),
        ("running_no_integration", "needs_integration"),
        ("discovered", "integration_discovered"),
        ("integration_error", "integration_error"),
        ("not_onboarded", "needs_onboarding"),
        ("ready", "ready"),
        ("beta_running", "ready"),
    ],
)
async def test_detection(make_env, scenario, expected):
    env = await make_env(scenario)
    result = await state_of(env)
    assert result["state"] == expected, result
    assert writes(env) == []  # detection never writes


async def test_ready_uses_server_probe(make_env):
    env = await make_env("ready")
    facts = await gather_facts(env.supervisor, env.core, env.session, ha_version="2026.10.1", ma_port=env.ma_port)
    assert facts.server == {"server_version": "2.10.6", "schema_version": 33, "onboard_done": True, "homeassistant_addon": True, "status": "running"}
    assert evaluate(facts)["verified"] is True


async def test_default_role_detection_hands_off(make_env):
    env = await make_env("default_role")
    result = await state_of(env)
    # Listing is forbidden for the default role, but /addons/<slug>/info isn't.
    assert result["state"] == "unknown"  # default role cannot check availability
    assert result["direct_install"]["available"] is False
    assert all(a["kind"] != "setup" for a in result["actions"])
    assert result["actions"][0]["path"].startswith("/_my_redirect/")


async def test_default_role_detects_installed_app(make_env):
    env = await make_env("default_role")
    env.mock._mark_installed("stopped")
    result = await state_of(env)
    assert result["state"] == "stopped"
    assert result["actions"][0]["label"] == "Start it from the app page"
    assert result["actions"][0]["path"] == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"


# ---- direct installation -----------------------------------------------------------


async def test_direct_install_with_repository_present(make_env):
    env = await make_env("absent")
    op = await run_setup(env)
    assert op["success"], op
    assert writes(env) == [
        ("POST", "/store/addons/d5369777_music_assistant/install"),
        ("POST", "/addons/d5369777_music_assistant/start"),
    ]
    assert "already in the App Store" in " ".join(op["log"])
    result = await state_of(env)
    # Started -> Music Assistant announced itself -> waiting for confirmation.
    assert result["state"] == "integration_discovered"
    env.mock.confirm_integration()
    result = await state_of(env)
    assert result["state"] == "ready" and result["verified"]


async def test_direct_install_adds_missing_repository_once(make_env):
    env = await make_env("no_repo")
    op = await run_setup(env)
    assert op["success"], op
    assert writes(env)[0] == ("POST", "/store/repositories")
    assert sum(1 for w in writes(env) if w[1] == "/store/repositories") == 1
    # A second run must not add the repository again nor reinstall.
    env.mock.calls.clear()
    op2 = await run_setup(env)
    assert op2["success"]
    assert writes(env) == []


async def test_already_installed_is_not_reinstalled(make_env):
    env = await make_env("installed_stopped")
    op = await run_setup(env)
    assert op["success"], op
    assert writes(env) == [("POST", "/addons/d5369777_music_assistant/start")]


async def test_already_running_is_a_no_op(make_env):
    env = await make_env("ready")
    op = await run_setup(env)
    assert op["success"]
    assert writes(env) == []


async def test_install_failure_surfaces_job_error_and_handoff(make_env):
    env = await make_env("install_fails")
    op = await run_setup(env)
    assert op["finished"] and not op["success"]
    assert op["error"]["kind"] == "install_failed"
    assert "no space left on device" in op["error"]["message"]
    assert op["fallback_path"] == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"
    assert ("POST", "/addons/d5369777_music_assistant/start") not in writes(env)


async def test_permission_failure_falls_back_to_handoff(make_env):
    env = await make_env("default_role")
    op = await run_setup(env)
    assert not op["success"]
    assert op["error"]["kind"] == "permission"
    assert op["fallback_path"].startswith("/_my_redirect/")
    assert writes(env) == []


async def test_permission_denied_mid_flow_maps_to_permission(make_env):
    env = await make_env("absent")
    env.mock.role = "manager"
    # Self info says manager, but the Supervisor then refuses the store.
    original = env.mock.security

    from aiohttp import web

    @web.middleware
    async def deny_store(request, handler):
        if request.path.startswith("/store"):
            env.mock.calls.append((request.method, request.path))
            raise web.HTTPForbidden()
        return await original(request, handler)

    env.mock.security = deny_store  # type: ignore[method-assign]
    from aiohttp.test_utils import TestServer
    from homestarter.supervisor import SupervisorClient

    server = TestServer(env.mock.app())
    await server.start_server()
    try:
        sup = SupervisorClient(env.session, str(server.make_url("")).rstrip("/"), env.supervisor._token)
        setup = MusicSetup(sup, poll_interval=0)
        setup.start(None)
        await setup.wait()
        op = setup.snapshot()
    finally:
        await server.close()
    assert op["error"]["kind"] == "permission"
    assert op["fallback_path"]


async def test_unsupported_system_stops_before_install(make_env):
    env = await make_env("unavailable")
    op = await run_setup(env)
    assert op["error"]["kind"] == "unsupported"
    assert writes(env) == []


async def test_concurrent_requests_join_one_operation(make_env):
    env = await make_env("absent")
    setup = MusicSetup(env.supervisor, poll_interval=0)
    first = setup.start("a")
    second = setup.start("b")
    assert first is second
    await setup.wait()
    assert sum(1 for w in writes(env) if w[1].endswith("/install")) == 1


async def test_install_timeout(make_env):
    env = await make_env("absent", job_ticks=10_000)
    op = await run_setup(env, install_timeout=0.05)
    assert op["error"]["kind"] == "timeout"


async def test_operation_shown_while_running(make_env):
    env = await make_env("absent", job_ticks=50)
    setup = MusicSetup(env.supervisor, poll_interval=0.01)
    setup.start("u")
    import asyncio

    await asyncio.sleep(0.05)
    facts = await gather_facts(env.supervisor, env.core, env.session, ha_version="2026.10.1", ma_port=env.ma_port)
    result = evaluate(facts, setup.snapshot())
    assert result["state"] == "installing"
    await setup.wait()
    assert setup.snapshot()["success"]
