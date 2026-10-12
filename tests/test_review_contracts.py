"""Adversarial cases missing from the original happy-path contract harness."""

from __future__ import annotations

import copy

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homestarter.music import evaluate, gather_facts, probe_server
from homestarter.server import K_STATE
from homestarter.supervisor import SupervisorClient, SupervisorError
from test_music_evaluate import facts
from test_server import app_client as _app_client

app_client = _app_client


@pytest.mark.parametrize(
    "change",
    [
        "no_ingress",
        "no_probe",
        "unknown_onboarding",
        "wrong_version",
        "external_server",
        "server_starting",
        "manual_entry",
        "multiple_entries",
        "multiple_apps",
    ],
)
def test_incomplete_or_ambiguous_evidence_is_not_ready(change):
    f = facts(installed="addons_with_ma.json", info="app_info_ma_started.json", entries="ma_entries_loaded.json")
    if change == "no_ingress":
        f.app_info.update(ingress=False, ingress_url=None)
        f.ingress_responding = False
    elif change == "no_probe":
        f.server = None
        f.ingress_responding = False
    elif change == "unknown_onboarding":
        f.server.pop("onboard_done")
    elif change == "wrong_version":
        f.server["server_version"] = "0.0.0"
    elif change == "external_server":
        f.server["homeassistant_addon"] = False
    elif change == "server_starting":
        f.server["status"] = "starting"
    elif change == "manual_entry":
        f.config_entries[0]["source"] = "user"
    elif change == "multiple_entries":
        f.config_entries.append(dict(f.config_entries[0], entry_id="another-server"))
    else:
        f.installed_apps.append(dict(f.installed_apps[-1], slug="d5369777_music_assistant_beta"))
    result = evaluate(f)
    assert result["state"] == "running_unverified"
    assert not result["verified"]
    assert any(a["kind"] == "navigate" for a in result["actions"])


def test_unreadable_installed_list_does_not_mean_not_installed():
    f = facts(installed=None)
    f.installed_error = {"kind": "unreachable", "message": "timed out"}
    result = evaluate(f)
    assert result["state"] == "unknown"
    assert next(c for c in result["checks"] if c["id"] == "installed")["status"] == "unknown"
    assert all(a["kind"] != "setup" for a in result["actions"])


@pytest.mark.parametrize(("kind", "status"), [("forbidden", 403), ("api", 503)])
def test_unreadable_availability_does_not_mean_compatible(kind, status):
    f = facts(availability_error={"kind": kind, "message": "unavailable", "status": status})
    result = evaluate(f)
    assert result["state"] == "unknown"
    assert not result["direct_install"]["available"]
    assert all(a["kind"] != "setup" for a in result["actions"])


async def test_probe_uses_ingress_metadata_even_when_public_port_is_unreachable(make_env):
    env = await make_env("ready")
    f = await gather_facts(env.supervisor, env.core, env.session, ha_version="2026.10.1", ma_port=1)
    assert f.server and f.ingress_responding
    assert evaluate(f)["verified"]


@pytest.mark.parametrize("kind", ["redirect", "empty_version", "not_json"])
async def test_probe_rejects_redirects_and_invalid_responses(make_env, kind):
    env = await make_env("ready")
    app = web.Application()
    followed = []

    async def info(request):
        if kind == "redirect":
            raise web.HTTPFound("/other")
        if kind == "empty_version":
            return web.json_response({"server_version": ""})
        return web.Response(text="broken")

    async def other(request):
        followed.append(True)
        return web.json_response(env.mock.server_info)

    app.router.add_get("/info", info)
    app.router.add_get("/other", other)
    async with TestServer(app) as srv:
        with pytest.raises(ValueError):
            await probe_server(env.session, "127.0.0.1", srv.port)
    assert not followed


@pytest.mark.parametrize("policy", ["ordinary", "inactive", "unknown", "system", "unreadable"])
async def test_setup_fails_closed_for_untrusted_user(app_client, policy):
    client, env = await app_client()
    user = copy.deepcopy(env.mock.users[0])
    if policy == "ordinary":
        user.update(is_owner=False, group_ids=["system-users"])
    elif policy == "inactive":
        user["is_active"] = False
    elif policy == "unknown":
        user["id"] = "someone-else"
    elif policy == "system":
        user["system_generated"] = True
    else:
        original = env.mock._fake_ws_result

        def deny(msg):
            if msg["type"] == "config/auth/list":
                raise KeyError("unavailable")
            return original(msg)

        env.mock._fake_ws_result = deny
    env.mock.users = [user]
    response = await client.post("/api/music/setup", json={"confirm": True}, headers={"X-Remote-User-Id": "a1b2c3d4e5f6"})
    assert response.status == (503 if policy == "unreadable" else 403)
    assert not any(m == "POST" for m, _ in env.mock.calls)


async def test_active_administrator_can_start_setup(app_client):
    client, env = await app_client("ready")
    env.mock.users[0].update(is_owner=False, group_ids=["system-admin"])
    response = await client.post("/api/music/setup", json={"confirm": True}, headers={"X-Remote-User-Id": "a1b2c3d4e5f6"})
    assert response.status == 202
    await client.server.app[K_STATE].setup.wait()


@pytest.mark.parametrize("status", [403, 500])
async def test_http_error_is_not_success_even_with_ok_envelope(make_env, status):
    env = await make_env()
    app = web.Application()

    async def info(request):
        return web.json_response({"result": "ok", "data": {"homeassistant": "2026.10.1"}}, status=status)

    app.router.add_get("/info", info)
    async with TestServer(app) as srv:
        sup = SupervisorClient(env.session, str(srv.make_url("")).rstrip("/"), env.settings.token)
        with pytest.raises(SupervisorError):
            await sup.info()


async def test_reflected_token_is_redacted_before_errors_can_be_logged(make_env):
    env = await make_env()
    app = web.Application()

    async def info(request):
        return web.json_response({"result": "error", "message": f"Rejected {env.settings.token.reveal()}"}, status=400)

    app.router.add_get("/info", info)
    async with TestServer(app) as srv:
        sup = SupervisorClient(env.session, str(srv.make_url("")).rstrip("/"), env.settings.token)
        with pytest.raises(SupervisorError) as err:
            await sup.info()
    assert env.settings.token.reveal() not in str(err.value)
