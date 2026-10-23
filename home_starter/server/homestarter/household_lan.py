"""Separate, explicitly enabled household media boundary; never an ingress proxy."""

from __future__ import annotations

import ipaddress
import secrets
import time

from aiohttp import web

from .music_runtime import digest

HOST = "192.168.68.119:13379"
ORIGIN = "http://" + HOST
SUBNET = ipaddress.ip_network("192.168.68.0/24")
COOKIE = "household_context"
TTL = 1800
ASSETS = {"media-app.js", "media-app.css", "media.webmanifest", "routes.js", "icon.svg"}
# Existing service checks still validate profile/source/player/queue ownership and
# fresh revisions. No setup, account/provider configuration or arbitrary MA calls.
ACTIONS = {
    "destination",
    "play_item",
    "resume",
    "pause",
    "play",
    "stop",
    "next",
    "previous",
    "volume",
    "sleep",
    "favorite",
    "unfavorite",
    "queue_add",
    "queue_next",
    "queue_remove",
    "queue_move",
    "queue_clear",
    "queue_join",
    "queue_takeover_prepare",
    "queue_takeover",
    "queue_takeover_cancel",
    "transfer_prepare",
    "transfer_confirm",
    "transfer_cancel",
    "transfer_recheck",
    "play_radio",
    "play_ambient",
    "play_playlist",
    "surprise_me",
    "something_different",
}


def allowed_peer(value: str | None) -> bool:
    try:
        address = ipaddress.ip_address(value or "")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        return address in SUBNET
    except ValueError:
        return False


def create_household_app(parent: web.Application) -> web.Application:
    from . import server

    settings, state = parent[server.K_SETTINGS], parent[server.K_STATE]
    house = state.household.load()
    surface = next((s for s in house["surfaces"] if s["id"] == settings.household_lan_surface), None)
    if not settings.household_lan or not surface or surface.get("person_id") or settings.household_lan_binding != digest([house["epoch"], surface]):
        raise ValueError("LAN access requires its reviewed shared display binding.")
    caller = {"kind": "household-lan", "surface": surface["id"], "binding": settings.household_lan_binding}
    state.listening.household_lan_caller = caller
    contexts: dict[str, float] = {}

    @web.middleware
    async def boundary(request, handler):
        if (
            not allowed_peer(request.remote)
            or request.headers.get("Host") != HOST
            or any(
                name in request.headers
                for name in (
                    "Forwarded",
                    "X-Forwarded-For",
                    "X-Forwarded-Host",
                    "X-Ingress-Path",
                    "X-Remote-User-Id",
                )
            )
            or request.headers.get("Origin") not in (None, ORIGIN)
            or request.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin")
        ):
            raise web.HTTPForbidden(text="Household Audio is available on the approved home network only.")
        now = time.monotonic()
        for token, expiry in list(contexts.items()):
            if expiry <= now:
                contexts.pop(token, None)
        if request.path.startswith("/api/"):
            if not (
                request.path == "/api/listening"
                and request.method == "GET"
                or request.path == "/api/listening/" + surface["id"]
                and request.method in {"GET", "POST"}
            ):
                raise web.HTTPNotFound()
            if request.cookies.get(COOKIE) not in contexts:
                return web.json_response({"error": "Reopen Household Audio to renew this browser session."}, status=403)
            if request.method == "POST":
                if request.headers.get("Origin") != ORIGIN or request.content_type != "application/json":
                    raise web.HTTPForbidden(text="Use the household page to control playback.")
                try:
                    body = await request.json()
                except ValueError:
                    body = None
                if not isinstance(body, dict) or body.get("action") not in ACTIONS:
                    return web.json_response({"error": "This action is not available on the household listener."}, status=403)
        request["household_lan_caller"] = caller
        response = await handler(request)
        if request.path in {"/", "/media"} and request.method in {"GET", "HEAD"}:
            if len(contexts) >= 2048:
                raise web.HTTPServiceUnavailable(text="Too many browser sessions. Retry shortly.")
            token = secrets.token_urlsafe(32)
            contexts[token] = now + TTL
            response.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite="Strict", path="/")
        return response

    async def listening(request):
        if request.match_info["surface"] != surface["id"]:
            raise web.HTTPForbidden(text="Choose the configured household audio view.")
        return await server.api_listening(request)

    async def asset(request):
        if request.match_info["name"] not in ASSETS:
            raise web.HTTPNotFound()
        return await server.static(request)

    # A different Application/router on a different socket: administrative routes
    # never reach peer_guard, household_admin, Core or Supervisor from this port.
    app = web.Application(middlewares=[boundary, server.harden], client_max_size=32 * 1024)
    app[server.K_SETTINGS], app[server.K_STATE] = settings, state
    app.router.add_get("/", server.media_app)
    app.router.add_get("/media", server.media_app)
    app.router.add_get("/static/{name}", asset)
    app.router.add_get("/api/listening", server.api_listening_bootstrap)
    app.router.add_get("/api/listening/{surface}", listening)
    app.router.add_post("/api/listening/{surface}", listening)
    return app


async def start_listener(parent):
    app = create_household_app(parent)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    try:
        await web.TCPSite(runner, "0.0.0.0", 8098).start()
    except BaseException:
        await runner.cleanup()
        raise
    return runner
