"""The LAN socket is a separate router/role, using fictional household data."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from homestarter import household_lan as lan
from homestarter import server
from homestarter.household import HouseholdStore, empty_household
from homestarter.listening import ListeningRuntime
from homestarter.music_runtime import digest
from homestarter.settings import Secret, Settings


@pytest.fixture
def parent(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = empty_household()
    surface = {"id": "shared", "name": "Example shared", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}
    house["surfaces"] = [surface]
    house = store.save(house)
    settings = Settings(
        token=Secret("synthetic-secret"), household_lan=True, household_lan_surface="shared", household_lan_binding=digest([house["epoch"], surface])
    )
    listening = SimpleNamespace(
        authorize=AsyncMock(),
        bootstrap=AsyncMock(return_value={"surfaces": [{"id": "shared", "name": "Example"}]}),
        view=AsyncMock(return_value={"person_id": None, "players": [], "books": []}),
        action=AsyncMock(),
    )
    parent = web.Application()
    parent[server.K_SETTINGS] = settings
    parent[server.K_STATE] = SimpleNamespace(household=store, listening=listening, music_runtime=SimpleNamespace(connection=lambda: None))
    return parent


@pytest.mark.parametrize(
    "peer,expected",
    [
        ("192.168.68.24", True),
        ("::ffff:192.168.68.24", True),
        ("192.168.69.24", False),
        ("172.30.32.1", False),
        ("127.0.0.1", False),
        ("8.8.8.8", False),
        (None, False),
    ],
)
def test_exact_source_subnet(peer, expected):
    assert lan.allowed_peer(peer) is expected


@pytest.mark.asyncio
async def test_browser_and_admin_boundaries(parent, monkeypatch):
    monkeypatch.setattr(lan, "allowed_peer", lambda peer: peer == "127.0.0.1")
    async with TestClient(TestServer(lan.create_household_app(parent)), cookie_jar=CookieJar(unsafe=True)) as client:
        headers = {"Host": lan.HOST}
        assert (await client.get("/api/listening", headers=headers)).status == 403
        root = await client.get("/", headers=headers)
        assert root.status == 200
        assert "Household" in await root.text()
        cookie = root.cookies[lan.COOKIE]
        assert cookie["httponly"] and cookie["samesite"] == "Strict"
        assert (await client.get("/api/listening", headers=headers)).status == 200
        assert (await client.get("/static/media-app.js", headers=headers)).status == 200
        for path in (
            "/api/household",
            "/api/media",
            "/api/music/runtime",
            "/api/connections",
            "/api/scan",
            "/api/supervisor",
            "/api/websocket",
            "/static/app.js",
            "/static/../app.js",
        ):
            assert (await client.get(path, headers=headers)).status == 404
        assert (await client.get("/api/listening/private", headers=headers)).status == 404
        assert (await client.post("/api/household", json={"action": "pause"}, headers={**headers, "Origin": lan.ORIGIN})).status == 404
        for forged in (
            {"Origin": "http://evil.example"},
            {"Host": "evil.example"},
            {"X-Remote-User-Id": "administrator"},
            {"X-Forwarded-For": "192.168.68.2"},
            {"X-Ingress-Path": "/api/hassio_ingress/spoof"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            assert (await client.get("/api/listening", headers={**headers, **forged})).status == 403
        action = {"action": "pause", "epoch": 1}
        assert (await client.post("/api/listening/shared", json=action, headers=headers)).status == 403
        assert (await client.post("/api/listening/shared", json=action, headers={**headers, "Origin": lan.ORIGIN})).status == 200
        assert parent[server.K_STATE].listening.action.await_args.args[0]["kind"] == "household-lan"
        for name in ("provider", "setup", "authenticate", "arbitrary_command", "delay"):
            assert (await client.post("/api/listening/shared", json={"action": name}, headers={**headers, "Origin": lan.ORIGIN})).status == 403
        parent[server.K_STATE].listening.view.return_value = {"error": "synthetic-secret"}
        response = await client.get("/api/listening/shared", headers=headers)
        assert response.status == 500 and "synthetic-secret" not in await response.text()
        monkeypatch.setattr(lan.time, "monotonic", lambda: 10**15)
        assert (await client.get("/api/listening", headers=headers)).status == 403


@pytest.mark.asyncio
async def test_source_guard_does_not_trust_forwarded_header(parent):
    async with TestClient(TestServer(lan.create_household_app(parent))) as client:
        assert (await client.get("/", headers={"Host": lan.HOST})).status == 403
        assert (await client.get("/", headers={"Host": lan.HOST, "X-Forwarded-For": "192.168.68.2"})).status == 403


@pytest.mark.asyncio
async def test_distinct_role_never_uses_ha_admin(parent, monkeypatch):
    from homestarter import listening

    state = parent[server.K_STATE]
    core = SimpleNamespace(is_admin=AsyncMock(side_effect=AssertionError("Must not impersonate HA")))
    runtime = ListeningRuntime(SimpleNamespace(), core, state.household)
    monkeypatch.setattr(listening.readiness, "load", lambda *args: {"choices": {"music": {"intent": "wanted", "screens": ["shared"]}}})
    caller = {"kind": "household-lan", "surface": "shared", "binding": parent[server.K_SETTINGS].household_lan_binding}
    runtime.household_lan_caller = caller
    assert (await runtime.authorize(caller, "shared", None))[3] is False
    house = state.household.load()
    house["surfaces"][0]["name"] = "Changed"
    state.household.save(house)
    with pytest.raises(PermissionError):
        await runtime.authorize(caller, "shared", None)
    core.is_admin.assert_not_awaited()
