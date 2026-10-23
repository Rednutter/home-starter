import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import CookieJar, web
from aiohttp.test_utils import TestClient, TestServer
from homestarter import household_lan, media_preview, server
from homestarter.household import HouseholdStore, empty_household
from homestarter.metadata_projection import fingerprint
from homestarter.settings import Secret, Settings


def artist():
    return {
        "item_id": "one",
        "provider": "example-source",
        "uri": "example-source://artist/one",
        "media_type": "artist",
        "name": "Example artist",
        "sort_name": "Example artist",
        "version": "",
        "artist_type": "singer",
        "is_playable": True,
        "provider_mappings": [{"provider_instance": "example-source", "provider_domain": "example", "item_id": "one", "available": True, "in_library": True}],
        "metadata": {"images": [{"type": "thumb", "provider": "builtin", "path": "https://i.scdn.co/image/example", "proxy_id": "a" * 64}]},
    }


def album():
    return {
        **artist(),
        "item_id": "album-one",
        "uri": "example-source://album/album-one",
        "media_type": "album",
        "name": "Example album",
        "album_type": "album",
        "artists": [artist()],
        "provider_mappings": [{"provider_instance": "example-source", "provider_domain": "example", "item_id": "album-one", "available": True}],
    }


def track():
    return {
        **artist(),
        "item_id": "track-one",
        "uri": "example-source://track/track-one",
        "media_type": "track",
        "name": "Example track",
        "duration": 180,
        "artists": [artist()],
        "album": album(),
        "position": 1,
        "track_number": 1,
        "disc_number": 1,
        "provider_mappings": [{"provider_instance": "example-source", "provider_domain": "example", "item_id": "track-one", "available": True}],
    }


@pytest.fixture
def preview_state(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    (root / "assets").mkdir(parents=True)
    files = {
        "index.html": b'<html><head></head><body><div id="app"></div><script src="./assets/example.js"></script></body></html>',
        "assets/example.js": b'console.log("fictional asset")',
    }
    for name, content in files.items():
        (root / name).write_bytes(content)
    (root / "manifest.json").write_text(json.dumps({"files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()}}))
    monkeypatch.setattr(media_preview, "ASSET_ROOT", root)
    store = HouseholdStore(str(tmp_path / "data"))
    house = empty_household()
    house["people"] = [{"id": "one", "name": "Example One", "audience": "adult"}]
    surface = {"id": "shared", "name": "Example", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}
    house["surfaces"] = [surface]
    house = store.save(house)
    connection = {"server_id": "example-server", "app": "example-ma", "generation": "one", "token": Secret("example-runtime-value")}
    endpoint = {**{k: v for k, v in connection.items() if k != "token"}, "version": "2.10.7", "address": "http://example.invalid"}
    filters = ["example-source"]
    calls = []

    async def command(endpoint, connection, name, **args):
        calls.append(name)
        if name == "providers":
            return [
                {
                    "instance_id": "example-source",
                    "domain": "example",
                    "type": "music",
                    "available": True,
                    "supported_features": ["library_artists", "library_albums", "library_playlists", "artist_albums", "artist_tracks"],
                }
            ]
        if name == "auth/users":
            return [
                {"user_id": "house", "display_name": "House", "provider_filter": filters},
                {"user_id": "one", "display_name": "Example One", "provider_filter": filters},
            ]
        if name == "music/artists/library_items":
            return [artist()]
        if name == "music/albums/library_items":
            return [album()]
        if name in {"music/artists/artist_tracks", "music/albums/album_tracks"}:
            return [track()]
        if name == "music/playlists/library_items":
            return []
        raise AssertionError("Unexpected native command")

    runtime = SimpleNamespace(
        connection=lambda: connection, endpoint=AsyncMock(return_value=endpoint), command=command, control=AsyncMock(side_effect=AssertionError("No controls"))
    )
    listening = SimpleNamespace(
        bootstrap=AsyncMock(return_value={"surfaces": [surface]}),
        authorize=AsyncMock(),
        load=lambda h, c: {"profiles": {"person:one": {"favorites": [], "recent": []}}},
        view=AsyncMock(return_value={"players": [], "books": []}),
        action=AsyncMock(),
        catalog={},
    )
    state = SimpleNamespace(household=store, music_runtime=runtime, listening=listening, session=None, filters=filters, calls=calls)
    return state, surface, root


def parent_for(state, surface):
    settings = Settings(
        token=Secret("example-service-value"),
        allowed_peers=("127.0.0.1",),
        household_lan=True,
        household_lan_surface=surface["id"],
        household_lan_binding=fingerprint([state.household.load()["epoch"], surface]),
    )
    app = web.Application(middlewares=[server.peer_guard, server.harden])
    app[server.K_SETTINGS], app[server.K_STATE] = settings, state
    media_preview.register(app, server.K_STATE, server._user, server.ingress_base)
    return app


@pytest.mark.asyncio
async def test_ingress_assets_read_allowlist_and_profile_capabilities(preview_state):
    state, surface, root = preview_state
    app = parent_for(state, surface)
    async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
        assert (await client.get("/audio/")).status == 403
        headers = {"X-Remote-User-Id": "example-admin", "X-Ingress-Path": "/api/hassio_ingress/example"}
        page = await client.get("/audio", headers=headers)
        assert page.status == 200 and 'href="/api/hassio_ingress/example/audio/"' in await page.text()
        assert "script-src 'self';" in page.headers["Content-Security-Policy"]
        assert (await client.get("/audio/assets/example.js", headers=headers)).status == 200
        for path in [
            "/audio/assets/not-listed.js",
            "/audio/assets/%2e%2e/manifest.json",
            "/audio/admin",
            "/audio/control",
            "/audio/read",
        ]:
            assert (await client.get(path, headers=headers)).status in {404, 405}
        boot = await client.get("/audio/bootstrap", headers=headers)
        assert boot.status == 200
        assert (await boot.json())["providers"][0]["supported_features"] == [
            "library_artists",
            "library_albums",
            "library_playlists",
            "artist_albums",
            "artist_tracks",
        ]
        cookie = boot.cookies[media_preview.COOKIE]
        assert cookie["httponly"] and cookie["samesite"] == "Strict"
        headers.update({"Cookie": media_preview.COOKIE + "=" + cookie.value, "Origin": str(client.make_url("")).rstrip("/")})
        body = {"profile": "house", "generation": 1, "command": "music/artists/library_items", "args": {}}
        response = await client.post("/audio/read", json=body, headers=headers)
        assert response.status == 200
        offered_artist = (await response.json())["result"][0]
        image = offered_artist["metadata"]["images"][0]["path"]
        old_selection = offered_artist["household_selection"]
        assert (await client.post("/audio/select", json={"profile": "one", "selection": old_selection}, headers=headers)).status == 403
        track_response = await client.post(
            "/audio/read",
            json={**body, "command": "music/albums/album_tracks", "args": {"item_id": "album-one", "provider_instance_id_or_domain": "example-source"}},
            headers=headers,
        )
        selected_track = (await track_response.json())["result"][0]
        selection = {"profile": "house", "selection": selected_track["household_selection"]}
        selected = await client.post("/audio/select", json=selection, headers=headers)
        assert selected.status == 200
        item = await selected.json()
        assert item["title"] == "Example track" and item["id"] in state.listening.catalog
        state.listening.action.assert_not_awaited()
        identity = image.rsplit("/", 1)[-1]
        service = state.media_preview
        record = service.sessions[cookie.value]
        record["metadata"].art_read = AsyncMock(return_value=("image/png", b"fictional-image-bytes"))
        assert (await client.get("/audio/art/" + identity, headers=headers)).status == 200
        assert (await client.get("/audio/imageproxy", params={"path": "http://127.0.0.1/private"}, headers=headers)).status == 404
        assert (await client.post("/audio/read", json={**body, "profile": "one", "generation": 2}, headers=headers)).status == 200
        assert (await client.get("/audio/art/" + identity, headers=headers)).status == 404
        for name in ["auth/user/update", "player_queues/play_media", "players/cmd/volume_set", "config/providers", "homestarter/media_prepare"]:
            assert (await client.post("/audio/read", json={**body, "generation": 3, "command": name}, headers=headers)).status == 403
        for extra in [{"Origin": "https://other.example"}, {"Sec-Fetch-Site": "cross-site"}, {"X-Remote-User-Id": "other-person"}]:
            assert (await client.post("/audio/read", json=body, headers={**headers, **extra})).status == 403
        state.filters.clear()
        assert (await client.post("/audio/select", json=selection, headers=headers)).status == 403
        assert (await client.post("/audio/read", json={**body, "generation": 4}, headers=headers)).status == 403
        record["expires"] = 0
        assert (await client.post("/audio/read", json=body, headers=headers)).status == 403
        (root / "assets/example.js").write_bytes(b"changed")
        assert (await client.get("/audio/assets/example.js", headers=headers)).status == 503
        state.music_runtime.control.assert_not_awaited()


@pytest.mark.asyncio
async def test_approved_lan_preview_and_original_controls_coexist(preview_state, monkeypatch):
    state, surface, _ = preview_state
    parent = parent_for(state, surface)
    monkeypatch.setattr(household_lan, "allowed_peer", lambda peer: peer == "127.0.0.1")
    app = household_lan.create_household_app(parent)
    async with TestClient(TestServer(app), cookie_jar=CookieJar(unsafe=True)) as client:
        headers = {"Host": household_lan.HOST}
        assert (await client.get("/audio/", headers=headers)).status == 200
        boot = await client.get("/audio/bootstrap", headers=headers)
        assert boot.status == 200
        headers["Cookie"] = media_preview.COOKIE + "=" + boot.cookies[media_preview.COOKIE].value
        body = {"profile": "house", "generation": 1, "command": "music/artists/library_items"}
        assert (await client.post("/audio/read", json=body, headers={**headers, "Origin": household_lan.ORIGIN})).status == 200
        for path in ["/api/household", "/api/media", "/api/music/runtime", "/static/app.js", "/audio/assets/../../app.js"]:
            assert (await client.get(path, headers=headers)).status == 404
        for extra in [{"Origin": "http://other.example"}, {"X-Remote-User-Id": "admin"}, {"X-Forwarded-For": "192.168.68.5"}]:
            assert (await client.get("/audio/bootstrap", headers={**headers, **extra})).status == 403
        assert (await client.get("/media", headers=headers)).status == 200
        state.music_runtime.control.assert_not_awaited()
