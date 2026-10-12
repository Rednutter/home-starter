"""Ingress-safe routing, request guards and token confidentiality."""

from __future__ import annotations

import logging
import re

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from homestarter.server import create_app, ingress_base
from homestarter.settings import Secret, Settings
from ingress_proxy import INGRESS_TOKEN, build_app
from mock_supervisor import TOKEN

PREFIX = f"/api/hassio_ingress/{INGRESS_TOKEN}"


@pytest.fixture
async def app_client(make_env):
    clients: list[TestClient] = []

    async def factory(scenario: str = "absent", *, peers: str = "127.0.0.1", **kw):
        env = await make_env(scenario, **kw)
        settings = Settings.from_env(
            {
                "SUPERVISOR_TOKEN": TOKEN,
                "HOME_STARTER_SUPERVISOR_URL": env.settings.supervisor_url,
                "HOME_STARTER_ALLOWED_PEERS": peers,
                "HOME_STARTER_MA_PORT": str(env.ma_port),
            }
        )
        client = TestClient(TestServer(create_app(settings)))
        await client.start_server()
        clients.append(client)
        return client, env

    yield factory
    for c in clients:
        await c.close()


@pytest.fixture
async def via_ingress(app_client):
    """Home Starter behind the simulated HA ingress proxy."""
    clients: list[TestClient] = []

    async def factory(scenario: str = "absent", **kw):
        app, env = await app_client(scenario, **kw)
        proxy = TestClient(TestServer(build_app(str(app.make_url("")))))
        await proxy.start_server()
        clients.append(proxy)
        return proxy, env, app

    yield factory
    for c in clients:
        await c.close()


# ---- ingress base path ---------------------------------------------------------


class _Req:
    def __init__(self, headers):
        self.headers = headers


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (PREFIX, PREFIX + "/"),
        ("", "./"),
        ("/api/hassio_ingress/abc/../../evil", "./"),
        ("//evil.example/x", "./"),
        ('/api/hassio_ingress/a"><script>alert(1)</script>', "./"),
        ("https://evil.example/api/hassio_ingress/abc", "./"),
    ],
)
def test_ingress_base_validation(header, expected):
    assert ingress_base(_Req({"X-Ingress-Path": header} if header else {})) == expected


async def test_index_without_ingress_uses_relative_base(app_client):
    client, _ = await app_client()
    resp = await client.get("/")
    assert resp.status == 200
    text = await resp.text()
    assert '<base href="./">' in text


async def test_index_assets_are_all_relative(app_client):
    client, _ = await app_client()
    text = await (await client.get("/")).text()
    refs = re.findall(r'(?:src|href)="([^"]*)"', text)
    assert refs, "expected asset references"
    for ref in refs:
        assert not ref.startswith("/"), f"absolute path breaks under ingress: {ref}"
        assert "://" not in ref


async def test_app_js_uses_only_relative_api_paths(app_client):
    client, _ = await app_client()
    js = await (await client.get("/static/app.js")).text()
    for path in re.findall(r'api\("([^"]+)"', js):
        assert not path.startswith("/"), path
    assert "fetch(apiUrl(" in js
    assert 'fetch("/' not in js and "fetch('/" not in js


async def test_static_whitelist(app_client):
    client, _ = await app_client()
    for name, ctype in (("app.js", "text/javascript"), ("routes.js", "text/javascript"), ("styles.css", "text/css"), ("icon.svg", "image/svg+xml")):
        resp = await client.get(f"/static/{name}")
        assert resp.status == 200 and resp.content_type == ctype
    for bad in ("/static/server.py", "/static/..%2fserver.py", "/static/index.html.bak", "/static/../settings.py"):
        assert (await client.get(bad)).status == 404


# ---- behind the simulated ingress proxy -------------------------------------------


async def test_routing_under_ingress_prefix(via_ingress):
    proxy, _, _ = await via_ingress("ready")
    resp = await proxy.get(PREFIX + "/")
    text = await resp.text()
    assert resp.status == 200
    assert f'<base href="{PREFIX}/">' in text
    # Without the trailing slash relative URLs would break; the base fixes it.
    text2 = await (await proxy.get(PREFIX)).text()
    assert f'<base href="{PREFIX}/">' in text2
    js = await proxy.get(PREFIX + "/static/app.js")
    assert js.status == 200 and js.content_type == "text/javascript"
    scan = await (await proxy.get(PREFIX + "/api/scan")).json()
    assert scan["system"]["status"] == "ok"
    music = await (await proxy.get(PREFIX + "/api/music")).json()
    assert music["state"] == "ready"
    assert music["open_path"] == "/app/d5369777_music_assistant"


async def test_setup_through_ingress_runs_and_verifies(via_ingress):
    import asyncio

    proxy, env, _ = await via_ingress("absent")
    resp = await proxy.post(PREFIX + "/api/music/setup", json={"confirm": True})
    assert resp.status == 202
    for _ in range(200):
        op = (await (await proxy.get(PREFIX + "/api/music/operation")).json())["operation"]
        if op["finished"]:
            break
        await asyncio.sleep(0.05)
    assert op["success"], op
    music = await (await proxy.get(PREFIX + "/api/music")).json()
    assert music["state"] == "integration_discovered"
    env.mock.confirm_integration()
    music = await (await proxy.get(PREFIX + "/api/music")).json()
    assert music["state"] == "ready" and music["verified"]


# ---- guards ---------------------------------------------------------------------------


async def test_only_ingress_peer_is_allowed(app_client):
    client, _ = await app_client(peers="172.30.32.2")
    assert (await client.get("/")).status == 403
    assert (await client.get("/api/scan")).status == 403


async def test_setup_requires_json(app_client):
    client, env = await app_client()
    resp = await client.post("/api/music/setup", data="confirm=true", headers={"X-Remote-User-Id": "u", "Content-Type": "application/x-www-form-urlencoded"})
    assert resp.status == 415
    assert [c for c in env.mock.calls if c[0] == "POST"] == []


async def test_setup_requires_ingress_user(app_client):
    client, env = await app_client()
    resp = await client.post("/api/music/setup", json={"confirm": True})
    assert resp.status == 403
    assert [c for c in env.mock.calls if c[0] == "POST"] == []


async def test_setup_requires_confirmation(app_client):
    client, env = await app_client()
    resp = await client.post("/api/music/setup", json={}, headers={"X-Remote-User-Id": "u"})
    assert resp.status == 400
    assert [c for c in env.mock.calls if c[0] == "POST"] == []


async def test_get_endpoints_never_install(app_client):
    client, env = await app_client("no_repo")
    for path in ("/", "/api/scan", "/api/scan?refresh=1", "/api/music", "/api/music/operation", "/api/health"):
        assert (await client.get(path)).status == 200
    assert [c for c in env.mock.calls if c[0] != "GET"] == []


async def test_security_headers(app_client):
    client, _ = await app_client()
    resp = await client.get("/")
    assert "frame-ancestors 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    api = await client.get("/api/music")
    assert api.headers["Cache-Control"] == "no-store"


# ---- token confidentiality --------------------------------------------------------------


async def test_supervisor_token_never_reaches_the_browser(via_ingress, caplog):
    caplog.set_level(logging.DEBUG)
    proxy, env, _ = await via_ingress("ready")
    bodies = []
    for path in (
        "/",
        "/static/app.js",
        "/static/routes.js",
        "/static/styles.css",
        "/static/icon.svg",
        "/api/scan?refresh=1",
        "/api/music",
        "/api/music/operation",
        "/api/health",
    ):
        resp = await proxy.get(PREFIX + path)
        bodies.append(await resp.read())
        bodies.append(str(dict(resp.headers)).encode())
    resp = await proxy.post(PREFIX + "/api/music/setup", json={"confirm": True})
    bodies.append(await resp.read())
    blob = b"\n".join(bodies)
    assert TOKEN.encode() not in blob
    assert b"Bearer" not in blob
    assert TOKEN not in caplog.text


async def test_leaking_handler_is_blocked(make_env):
    env = await make_env()
    settings = Settings.from_env({"SUPERVISOR_TOKEN": TOKEN, "HOME_STARTER_SUPERVISOR_URL": env.settings.supervisor_url, "HOME_STARTER_ALLOWED_PEERS": "*"})
    app = create_app(settings)

    async def leak(request):
        return web.json_response({"oops": settings.token.reveal()})

    app.router.add_get("/leak", leak)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        resp = await client.get("/leak")
        assert resp.status == 500
        assert TOKEN not in await resp.text()
    finally:
        await client.close()


def test_secret_never_formats():
    s = Secret("abc123")
    assert "abc123" not in repr(s) and "abc123" not in str(s) and "abc123" not in f"{s}" and "abc123" not in f"{s!r}"
    assert s.reveal() == "abc123"
    settings = Settings.from_env({"SUPERVISOR_TOKEN": "abc123"})
    assert "abc123" not in repr(settings)


async def test_clients_do_not_put_token_in_errors(make_env):
    from homestarter.supervisor import SupervisorClient, SupervisorError

    env = await make_env()
    sup = SupervisorClient(env.session, "http://127.0.0.1:9", Secret("very-secret-token"))
    with pytest.raises(SupervisorError) as exc:
        await sup.info()
    assert "very-secret-token" not in str(exc.value) and "very-secret-token" not in repr(exc.value.as_dict())
