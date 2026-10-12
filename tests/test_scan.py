"""Scan parsing and partial-failure behaviour (real HA 2026.10.1 Core payloads)."""

from __future__ import annotations

from aiohttp import web
from conftest import core_fixture, sup_fixture
from homestarter import scan


def test_parse_system_and_core_info():
    system = scan.parse_system(sup_fixture("info.json"))
    assert system["homeassistant"] == "2026.10.1"
    assert system["arch"] == "amd64"
    assert system["machine"] == "generic-x86-64"
    assert system["operating_system"] == "Home Assistant OS 17.0"
    core = scan.parse_core_info(sup_fixture("core_info.json"))
    assert core == {
        "version": "2026.10.1",
        "version_latest": "2026.10.2",
        "update_available": True,
        "machine": "generic-x86-64",
        "arch": "amd64",
    }


def test_parse_host_and_resolution():
    host = scan.parse_host(sup_fixture("host_info.json"))
    assert host["disk_free_gb"] == 84.2 and host["disk_total_gb"] == 116.7
    assert host["virtualization"] is None  # "" from the API means bare metal
    res = scan.parse_resolution(sup_fixture("resolution_info.json"))
    assert res["issue_count"] == 1 and res["issues"][0]["type"] == "no_current_backup"


def test_parse_installed_apps():
    apps = scan.parse_apps(sup_fixture("addons_with_ma.json")["addons"])
    assert apps["count"] == 5
    assert apps["running"] == 4
    assert apps["updates"] == 1  # File editor 5.8.0 -> 5.9.0
    assert [a["name"] for a in apps["items"]][0] == "File editor"  # sorted by name


def test_config_entry_health_from_real_payload():
    result = scan.parse_config_entries(core_fixture("config_entries_get.json"))
    assert result["count"] == 4
    assert result["loaded"] == 3
    assert result["unhealthy_count"] == 1
    bad = result["unhealthy"][0]
    assert bad["domain"] == "met" and bad["state"] == "setup_retry"
    assert bad["reason"].startswith("Update of data from the web site failed")


def test_config_entry_disabled_and_ignored_are_not_unhealthy():
    entries = core_fixture("config_entries_get.json") + core_fixture("ma_entries_ignored.json") + core_fixture("ma_entries_disabled.json")
    result = scan.parse_config_entries(entries)
    assert result["ignored"] == 1
    assert result["disabled"] == 1
    assert result["unhealthy_count"] == 1
    for state in ("setup_error", "migration_error", "failed_unload"):
        e = dict(core_fixture("ma_entries_loaded.json")[0], state=state)
        assert scan.parse_config_entries([e])["unhealthy_count"] == 1
    pending = dict(core_fixture("ma_entries_loaded.json")[0], state="setup_in_progress")
    assert scan.parse_config_entries([pending])["pending"] == 1


def test_unavailable_entity_detection():
    result = scan.parse_states(core_fixture("api_states.json"), core_fixture("entity_registry_list.json"))
    assert result["count"] == 19
    assert result["unavailable_count"] == 2
    ids = [e["entity_id"] for e in result["unavailable"]]
    assert ids == ["sensor.garage_door_battery", "sensor.pool_pump_power"]
    assert result["unavailable"][0]["name"] == "Garage door battery"
    assert result["unavailable"][0]["platform"] == "template"
    assert result["unknown_count"] > 0  # counted, not reported as a problem
    assert result["unavailable_by_source"] == {"template": 2}


def test_unavailable_entities_without_registry():
    result = scan.parse_states(core_fixture("api_states.json"), None)
    assert result["unavailable_count"] == 2
    assert result["unavailable"][0]["platform"] is None


def test_areas_and_repairs():
    areas = scan.parse_areas(core_fixture("area_registry_list.json"))
    assert areas["count"] == 5 and "Garage" in areas["names"]
    repairs = scan.parse_repairs(core_fixture("repairs_list_issues.json"))
    assert repairs["count"] >= 1
    ignored = {"issues": [dict(i, ignored=True, dismissed_version="2026.10.1") for i in core_fixture("repairs_list_issues.json")["issues"]]}
    assert scan.parse_repairs(ignored)["count"] == 0


async def test_full_scan_against_mock(make_env):
    env = await make_env("ready")
    result = await scan.run_scan(env.supervisor, env.core)
    for name in ("system", "core", "host", "resolution", "apps", "integrations", "areas", "entities", "repairs"):
        assert result[name]["status"] == "ok", (name, result[name])
    assert result["integrations"]["data"]["unhealthy_count"] == 1
    assert result["entities"]["data"]["unavailable_count"] == 2
    texts = " ".join(n["text"] for n in result["notes"])
    assert "failed to set up" in texts and "unavailable" in texts
    assert scan.ha_version_from_scan(result) == "2026.10.1"


async def test_scan_is_read_only(make_env):
    env = await make_env("absent")
    await scan.run_scan(env.supervisor, env.core)
    assert all(method == "GET" for method, _ in env.mock.calls), env.mock.calls


async def test_partial_scan_failures_are_isolated(make_env):
    env = await make_env("ready")
    app_routes = env.mock

    # Break two Supervisor sources: one with an API error, one with a 403.
    async def broken(request):
        return web.json_response({"result": "error", "message": "Host info not available"}, status=400)

    async def forbidden(request):
        raise web.HTTPForbidden()

    app_routes.host_info = broken  # type: ignore[method-assign]
    app_routes.resolution_info = forbidden  # type: ignore[method-assign]
    # Re-create the app so the patched handlers are routed.
    from aiohttp.test_utils import TestServer

    server = TestServer(app_routes.app())
    await server.start_server()
    try:
        from homestarter.supervisor import SupervisorClient

        sup = SupervisorClient(env.session, str(server.make_url("")).rstrip("/"), env.supervisor._token)
        result = await scan.run_scan(sup, env.core)
    finally:
        await server.close()
    assert result["host"]["status"] == "unavailable"
    assert result["host"]["error"]["message"] == "Host info not available"
    assert result["resolution"]["status"] == "unavailable"
    assert result["resolution"]["error"]["kind"] == "forbidden"
    assert result["system"]["status"] == "ok"
    assert result["integrations"]["status"] == "ok"


async def test_scan_when_core_unreachable(make_env):
    env = await make_env("absent")
    from homestarter.core import CoreClient
    from homestarter.settings import Secret

    dead_core = CoreClient(env.session, "http://127.0.0.1:9/core/api", "ws://127.0.0.1:9/core/websocket", Secret("x"))
    result = await scan.run_scan(env.supervisor, dead_core)
    for name in ("integrations", "areas", "repairs", "entities"):
        assert result[name]["status"] == "unavailable"
        assert result[name]["error"]["kind"] == "unreachable"
    assert result["system"]["status"] == "ok"
    assert result["apps"]["status"] == "ok"


async def test_scan_with_wrong_token(make_env):
    env = await make_env("absent")
    from homestarter.core import CoreClient
    from homestarter.settings import Secret
    from homestarter.supervisor import SupervisorClient

    sup = SupervisorClient(env.session, env.settings.supervisor_url, Secret("wrong"))
    core = CoreClient(env.session, env.settings.core_api_url, env.settings.core_ws_url, Secret("wrong"))
    result = await scan.run_scan(sup, core)
    assert result["system"]["status"] == "unavailable" and result["system"]["error"]["kind"] == "forbidden"
    assert result["integrations"]["error"]["kind"] == "auth"
    assert result["entities"]["error"]["kind"] == "auth"
