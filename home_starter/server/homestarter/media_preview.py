"""Opt-in read-only catalogue surface, separate from working media controls."""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import mimetypes
import re
import secrets
import time
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from aiohttp import web

from . import household_services
from .catalogue_preview import MetadataPreview
from .metadata_projection import native_artwork_path
from .music_runtime import MusicRuntimeError, digest

COOKIE = "media_preview_context"
TTL = 1800
PREFIX = "/audio"
PAGE_KEY = web.AppKey("household_audio_page", object)
ASSET_ROOT = Path(__file__).parent / "static" / "media-preview"
READS = {
    "providers",
    "auth/users",
    "music/browse",
    "music/search",
    "music/recommendations/items",
    *("music/" + k + "/library_items" for k in ("artists", "albums", "playlists")),
    "music/artists/artist_tracks",
    "music/albums/album_tracks",
    "music/playlists/playlist_tracks",
}


def asset_bytes(root, name):
    if not isinstance(name, str) or "\\" in name or any(p in {"", ".", ".."} for p in name.split("/")):
        raise web.HTTPNotFound()
    manifest = json.loads((root / "manifest.json").read_text())
    expected = manifest.get("files", {}).get(name)
    target = (root / name).resolve()
    if not expected or not target.is_relative_to(root.resolve()):
        raise web.HTTPNotFound()
    body = target.read_bytes()
    if hashlib.sha256(body).hexdigest() != expected:
        raise web.HTTPServiceUnavailable(text="Preview asset verification failed.")
    return body


class PreviewService:
    def __init__(self, state):
        self.state, self.sessions = state, {}

    async def authority(self, caller, surface=None, person=None):
        if not caller:
            raise PermissionError("Use authenticated ingress or the approved household listener.")
        house = self.state.household.load()
        if isinstance(caller, dict):
            selected = caller.get("surface")
            if surface not in (None, selected):
                raise PermissionError("Use the configured shared household view.")
        else:
            candidates = (await self.state.listening.bootstrap(caller)).get("surfaces", [])
            selected = surface or next((s["id"] for s in candidates if s.get("person_id") is None), None)
        if not selected:
            raise PermissionError("A permitted shared household view is required.")
        await self.state.listening.authorize(caller, selected, person)
        return house, selected

    def binding(self, caller, house, surface, connection):
        return digest([caller, house["epoch"], house["revision"], surface, connection["server_id"], connection["app"], connection["generation"]])

    async def open(self, caller, surface=None):
        house, surface = await self.authority(caller, surface)
        runtime = self.state.music_runtime
        connection, endpoint = runtime.connection(), await runtime.endpoint()
        if not connection or endpoint["server_id"] != connection["server_id"] or endpoint["app"] != connection["app"] or endpoint.get("version") != "2.10.7":
            raise MusicRuntimeError("The reviewed Music Assistant connection is unavailable.")

        async def command(name, **args):
            if name not in READS:
                raise PermissionError("Read-only catalogue operation unavailable.")
            return await runtime.command(endpoint, connection, name, **args)

        async def app_read(path):
            # Read the existing app-owned saved state; never invoke control,
            # provisioning, source sharing or a native personal-history union.
            person = path.split("?person=", 1)[1] if "?person=" in path else None
            await self.authority(caller, surface, person)
            saved = self.state.listening.load(house, connection)
            key = "person:" + person if person else "house"
            profile = saved.get("profiles", {}).get(key, {})
            configured = next((p for p in house["people"] if p["id"] == person), {})
            return {
                "favorites": profile.get("favorites", []),
                "recent": profile.get("recent", []),
                "browse": person is None or configured.get("audience") == "adult",
            }

        async def art_read(image):
            path = native_artwork_path(image)
            if not path:
                return None
            async with self.state.session.get(
                endpoint["address"] + path,
                headers={"Authorization": "Bearer " + connection["token"].reveal()},
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=6),
            ) as response:
                mime = response.headers.get("Content-Type", "").split(";")[0]
                if response.status != 200 or mime not in {"image/jpeg", "image/png", "image/webp"}:
                    return None
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 4 * 1024 * 1024:
                        return None
                return mime, bytes(body)

        metadata = MetadataPreview(command, app_read, art_read, house, surface)
        configured = household_services.load(self.state.household, house).get("region") or {}
        metadata.region = {k: configured.get(k) for k in ("id", "name", "country_code", "search_terms")}
        # Keep public directory enrichment optional. No new Internet endpoint is
        # needed for the production trial; absent fields retain honest labels.
        await asyncio.wait_for(metadata.prepare(), 60)
        now = time.monotonic()
        self.sessions = {k: v for k, v in self.sessions.items() if v["expires"] > now}
        if len(self.sessions) >= 64:
            raise MusicRuntimeError("Too many catalogue preview sessions. Try later.")
        identity = secrets.token_urlsafe(32)
        self.sessions[identity] = {
            "expires": now + TTL,
            "caller": digest(caller),
            "surface": surface,
            "binding": self.binding(caller, house, surface, connection),
            "metadata": metadata,
        }
        return identity, {
            "surface": surface,
            "profiles": metadata.profiles,
            "providers": [
                {
                    "instance_id": p["instance_id"],
                    "domain": p["domain"],
                    "name": "Spotify" if p["domain"] == "spotify" else p["domain"],
                    "type": "music",
                    "available": p.get("available", False),
                    "supported_features": [f for f in p.get("supported_features", []) if f.startswith("library_") or f in {"artist_albums", "artist_tracks"}],
                }
                for p in metadata.providers.values()
            ],
            "notes": (
                "Connected catalogues combine by exact identity. Personal collections use your own saved listening; "
                "unassigned playlist ownership and missing regional/language metadata stay unverified."
            ),
        }

    async def selected(self, identity, caller, person=None):
        record = self.sessions.get(identity)
        if not record or record["expires"] <= time.monotonic() or record["caller"] != digest(caller):
            raise PermissionError("Reopen the catalogue preview.")
        house, surface = await self.authority(caller, record["surface"], person)
        connection = self.state.music_runtime.connection()
        if not connection or record["binding"] != self.binding(caller, house, surface, connection):
            self.sessions.pop(identity, None)
            raise PermissionError("Household or music connection changed. Reopen the preview.")
        return record

    async def read(self, identity, caller, body):
        if not isinstance(body, dict):
            raise PermissionError("Choose a supported read.")
        person = body.get("profile")
        if not isinstance(person, str):
            raise PermissionError("Choose a household profile.")
        record = await self.selected(identity, caller, None if person == "house" else person)
        result = await record["metadata"].read(identity, body)
        await self.selected(identity, caller, None if person == "house" else person)
        return result

    async def artwork(self, identity, caller, image):
        record = await self.selected(identity, caller)
        selected = record["metadata"].ledger.contexts.get(identity)
        if not selected:
            raise PermissionError("Choose a current profile.")
        person = selected["profile"]
        await self.selected(identity, caller, None if person == "house" else person)
        result = await record["metadata"].artwork(identity, image)
        await self.selected(identity, caller, None if person == "house" else person)
        return result

    async def selection(self, identity, caller, body):
        from . import catalogue
        from .listening import media_record
        from .listening_sessions import queueable

        if not isinstance(body, dict) or set(body) != {"profile", "selection"} or not isinstance(body["selection"], str):
            raise PermissionError("Choose an offered catalogue selection.")
        profile = body["profile"]
        record = await self.selected(identity, caller, None if profile == "house" else profile)
        metadata = record["metadata"]
        offered = metadata.offered.get(body["selection"])
        allowed, policy = await metadata.policy(profile)
        if not offered or offered["profile"] != profile or offered["policy"] != policy:
            raise PermissionError("This selection belongs to an old profile or source mapping. Choose it again.")
        row = offered["row"]
        providers = [{**p, "id": p["instance_id"], "features": p.get("supported_features", [])} for p in metadata.providers.values()]
        sources = set(row.get("household_provenance", [])) & set(allowed)
        if not sources:
            raise PermissionError("This source is no longer assigned.")
        if not any(p["domain"] == "spotify" and p["id"] in sources for p in providers):
            runtime = self.state.music_runtime
            connection, endpoint = runtime.connection(), await runtime.endpoint()
            access = await catalogue.policy(runtime, endpoint, connection, self.state.household.load(), None if profile == "house" else profile, providers)
            candidates = [catalogue.sanitise(row, p) for p in providers if p["id"] in sources]
            row = next((r for r in candidates if r), None)
            if not row:
                raise PermissionError("This catalogue source needs a fresh selection.")
            row = {**row, "catalogue_access": access["signature"]}
        else:
            # Reuse the existing household collection -> protected allocator flow.
            # Never send a native play command or choose a Spotify account here.
            row = {**row, "household_collection": True}
        item = media_record(row)
        if not item:
            raise PermissionError("This selection cannot be played.")
        self.state.listening.catalog[item["id"]] = item
        return {
            **{key: item[key] for key in ("id", "title", "kind", "folder")},
            "queueable": queueable(item, providers),
            "source_scoped": bool(item.get("catalogue_access")),
        }


def register(app, state_key, user, base):
    def root(request):
        prefix = base(request)
        return prefix if prefix.startswith("/") else "/"

    def same_origin(request, required=False):
        origin = request.headers.get("Origin")
        if (
            request.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin")
            or (required and not origin)
            or origin
            and origin != request.scheme + "://" + request.host
        ):
            raise web.HTTPForbidden()

    def service(request):
        state = request.app[state_key]
        if not hasattr(state, "media_preview"):
            state.media_preview = PreviewService(state)
        return state.media_preview

    async def page(request):
        try:
            await service(request).authority(user(request), request.query.get("surface"))
            text = asset_bytes(ASSET_ROOT, "index.html").decode()
            href = root(request) + PREFIX.lstrip("/") + "/"
            text = text.replace("<head>", '<head><base href="' + html.escape(href, quote=True) + '">', 1)
            return web.Response(text=text, content_type="text/html")
        except PermissionError:
            raise web.HTTPForbidden(text="Use a permitted household view.") from None
        except (OSError, ValueError):
            raise web.HTTPServiceUnavailable(text="The catalogue trial assets are not installed.") from None

    async def asset(request):
        name = "assets/" + request.match_info["asset"]
        try:
            body = asset_bytes(ASSET_ROOT, name)
            return web.Response(body=body, content_type=mimetypes.guess_type(name)[0] or "application/octet-stream")
        except (OSError, ValueError):
            raise web.HTTPNotFound() from None

    async def bootstrap(request):
        same_origin(request)
        try:
            identity, result = await service(request).open(user(request), request.query.get("surface"))
            response = web.json_response(result)
            response.set_cookie(COOKIE, identity, httponly=True, samesite="Strict", max_age=TTL, path=root(request) + PREFIX.lstrip("/") + "/")
            return response
        except PermissionError:
            raise web.HTTPForbidden(text="Use a permitted household view.") from None
        except (MusicRuntimeError, OSError, ValueError, TimeoutError):
            return web.json_response({"error": "Read-only catalogue unavailable. Existing controls are unchanged."}, status=503)

    async def read(request):
        same_origin(request, required=True)
        if request.content_type != "application/json":
            raise web.HTTPForbidden()
        try:
            result = await service(request).read(request.cookies.get(COOKIE), user(request), await request.json())
            return web.json_response({"result": result})
        except (PermissionError, ValueError, TypeError, KeyError):
            return web.json_response({"error": "This read is unavailable for the selected profile."}, status=403)
        except (MusicRuntimeError, OSError, TimeoutError):
            return web.json_response({"error": "Catalogue source unavailable. Existing controls are unchanged."}, status=503)

    async def art(request):
        same_origin(request)
        identity = request.match_info.get("image")
        if identity is None:
            path = unquote(request.query.get("path", ""))
            match = re.fullmatch(r"/?art/([a-f0-9]{64})", path)
            identity = match[1] if match else None
        if not identity:
            raise web.HTTPNotFound()
        try:
            result = await service(request).artwork(request.cookies.get(COOKIE), user(request), identity)
            if result:
                return web.Response(body=result[1], content_type=result[0])
        except (PermissionError, MusicRuntimeError, OSError, ValueError, TypeError, KeyError, aiohttp.ClientError, TimeoutError):
            pass
        raise web.HTTPNotFound(text="Artwork unavailable")

    async def selection(request):
        same_origin(request, required=True)
        if request.content_type != "application/json":
            raise web.HTTPForbidden()
        try:
            return web.json_response(await service(request).selection(request.cookies.get(COOKIE), user(request), await request.json()))
        except (PermissionError, ValueError, KeyError, TypeError):
            return web.json_response({"error": "This catalogue selection needs refreshing for the selected profile."}, status=403)
        except (MusicRuntimeError, OSError, TimeoutError):
            return web.json_response({"error": "This source is unavailable. Existing playback was kept."}, status=503)

    app.router.add_get(PREFIX, page)
    app.router.add_get(PREFIX + "/", page)
    app.router.add_get(PREFIX + "/assets/{asset:.+}", asset)
    app.router.add_get(PREFIX + "/bootstrap", bootstrap)
    app.router.add_post(PREFIX + "/read", read)
    app.router.add_post(PREFIX + "/select", selection)
    app.router.add_get(PREFIX + "/art/{image:[a-f0-9]{64}}", art)
    app.router.add_get(PREFIX + "/imageproxy", art)
    app[PAGE_KEY] = page
