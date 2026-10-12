"""aiohttp web server behind Home Assistant ingress.

Ingress serves this app at ``/api/hassio_ingress/<token>/`` on the Home
Assistant origin and forwards requests here with that prefix stripped
(Home Assistant Core adds the prefix as ``X-Ingress-Path``). The UI therefore
only uses relative URLs, and the page carries a ``<base href>`` derived from a
validated ``X-Ingress-Path`` so it also works without a trailing slash.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import secrets
import time
from contextlib import suppress
from importlib import resources
from typing import Any

import aiohttp
from aiohttp import web

from . import __version__
from .activity import update_activity
from .core import CoreClient, CoreError
from .household import PROFILES, HouseholdStore, validate_household
from .inventory import assign_area, collect_inventory
from .music import MusicSetup, evaluate, gather_facts
from .scan import ha_version_from_scan, run_scan
from .settings import Settings
from .supervisor import SupervisorClient, SupervisorError
from .surfaces import classify, generate, publish

_LOGGER = logging.getLogger(__name__)

INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]{1,128}$")
STATIC_FILES = {
    "app.js": "text/javascript",
    "routes.js": "text/javascript",
    "house.js": "text/javascript",
    "surfaces.js": "text/javascript",
    "styles.css": "text/css",
    "icon.svg": "image/svg+xml",
}
SCAN_TTL = 10.0

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'none'; object-src 'none'"
)

K_SETTINGS = web.AppKey("settings", Settings)
K_STATE = web.AppKey("state", "State")
K_OWN_SESSION = web.AppKey("own_session", bool)


class State:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession) -> None:
        self.settings = settings
        self.session = session
        self.supervisor = SupervisorClient(session, settings.supervisor_url, settings.token)
        self.core = CoreClient(session, settings.core_api_url, settings.core_ws_url, settings.token)
        self.setup = MusicSetup(self.supervisor)
        self.scan: dict[str, Any] | None = None
        self.scan_at = 0.0
        self.scan_lock = asyncio.Lock()
        self.inventory_write_lock = asyncio.Lock()
        self.household_lock = asyncio.Lock()
        self.activity_lock = asyncio.Lock()
        self.household = HouseholdStore(settings.data_dir)
        self.previews: dict[str, dict] = {}
        self.activity_task: asyncio.Task | None = None

    async def monitor_activity(self) -> None:
        while True:
            try:
                async with self.activity_lock:
                    house = self.household.load()
                    await update_activity(self.core, self.household, house["activities"])
            except (CoreError, OSError, ValueError, KeyError, TypeError):
                _LOGGER.warning("Appliance activity could not be refreshed; counts are not inferred.")
            await asyncio.sleep(30)

    async def get_scan(self, refresh: bool = False) -> dict[str, Any]:
        async with self.scan_lock:
            if refresh or self.scan is None or time.monotonic() - self.scan_at > SCAN_TTL:
                self.scan = await run_scan(self.supervisor, self.core)
                self.scan_at = time.monotonic()
            return self.scan

    async def ha_version(self) -> str | None:
        version = ha_version_from_scan(self.scan)
        if version:
            return version
        try:
            return (await self.supervisor.info()).get("homeassistant")
        except SupervisorError:
            return None

    async def music(self) -> dict[str, Any]:
        operation = self.setup.snapshot()
        facts = await gather_facts(
            self.supervisor,
            self.core,
            self.session,
            ha_version=await self.ha_version(),
            ma_port=self.settings.music_assistant_port,
        )
        return evaluate(facts, operation)


# ---- middlewares ---------------------------------------------------------


@web.middleware
async def peer_guard(request: web.Request, handler):
    settings = request.app[K_SETTINGS]
    if not settings.allow_any_peer and request.remote not in settings.allowed_peers:
        _LOGGER.warning("Rejected request from %s (only ingress is allowed)", request.remote)
        raise web.HTTPForbidden(text="Home Starter is only available through Home Assistant.")
    return await handler(request)


@web.middleware
async def harden(request: web.Request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("Cache-Control", "no-store")
    # Last line of defence: the Supervisor token must never leave the server.
    token = request.app[K_SETTINGS].token.reveal()
    body = getattr(response, "body", None)
    if token and isinstance(body, (bytes, bytearray)) and token.encode() in body:
        _LOGGER.error("Blocked a response that contained the Supervisor token")
        return web.json_response({"error": "internal"}, status=500)
    if isinstance(response, web.HTTPException):
        raise response
    return response


# ---- helpers ---------------------------------------------------------------


def ingress_base(request: web.Request) -> str:
    """Base href for the page; falls back to relative when not via ingress."""
    raw = request.headers.get("X-Ingress-Path", "")
    if INGRESS_PATH_RE.match(raw):
        return raw + "/"
    return "./"


def _static(name: str) -> bytes:
    return resources.files("homestarter").joinpath("static", name).read_bytes()


def _json(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, separators=(",", ":")))


def _user(request: web.Request) -> str | None:
    return request.headers.get("X-Remote-User-Id") or None


# ---- handlers --------------------------------------------------------------


async def index(request: web.Request) -> web.Response:
    page = _static("index.html").decode()
    base = html.escape(ingress_base(request), quote=True)
    page = page.replace("<!--BASE-->", f'<base href="{base}">', 1)
    return web.Response(text=page, content_type="text/html", headers={"Cache-Control": "no-cache"})


async def static(request: web.Request) -> web.Response:
    name = request.match_info["name"]
    if name not in STATIC_FILES:
        raise web.HTTPNotFound()
    return web.Response(body=_static(name), content_type=STATIC_FILES[name], headers={"Cache-Control": "no-cache"})


async def health(request: web.Request) -> web.Response:
    return _json({"ok": True, "version": __version__})


async def api_scan(request: web.Request) -> web.Response:
    state = request.app[K_STATE]
    refresh = request.query.get("refresh") in ("1", "true")
    return _json(await state.get_scan(refresh=refresh))


async def api_music(request: web.Request) -> web.Response:
    return _json(await request.app[K_STATE].music())


async def api_inventory(request: web.Request) -> web.Response:
    try:
        return _json(await collect_inventory(request.app[K_STATE].core))
    except (KeyError, TypeError, ValueError, AttributeError):
        return _json({"error": "Couldn't read the house inventory. Check again."}, status=503)


async def api_assign_area(request: web.Request) -> web.Response:
    if request.content_type != "application/json":
        raise web.HTTPUnsupportedMediaType(text="JSON required")
    user_id = _user(request)
    if not user_id:
        raise web.HTTPForbidden(text="Room changes must be made from Home Assistant.")
    try:
        body = await request.json()
    except ValueError:
        body = None
    required = {"device_id", "area_id", "expected_area_id", "confirm"}
    if (
        not isinstance(body, dict)
        or set(body) != required
        or body.get("confirm") is not True
        or not isinstance(body.get("device_id"), str)
        or not body["device_id"]
        or any(body[k] is not None and (not isinstance(body[k], str) or not body[k]) for k in ("area_id", "expected_area_id"))
    ):
        raise web.HTTPBadRequest(text="Review and confirm one device room change.")
    state = request.app[K_STATE]
    try:
        admin = await state.core.is_admin(user_id)
    except CoreError:
        raise web.HTTPServiceUnavailable(text="Couldn't verify administrator access. Check again.") from None
    if not admin:
        raise web.HTTPForbidden(text="A Home Assistant administrator must assign rooms.")
    try:
        async with state.inventory_write_lock:
            result = await assign_area(state.core, body["device_id"], body["area_id"], body["expected_area_id"])
    except CoreError:
        result = {"verified": False, "error": "Couldn't confirm the room change. Check again in Home Assistant before retrying."}
    state.scan = None
    return _json(result, status=200 if result["verified"] else 409)


async def api_music_setup(request: web.Request) -> web.Response:
    # Only an explicit button press in the ingress UI gets here: the request
    # must be a JSON POST (not a simple cross-site form) from an ingress
    # session (Supervisor sets X-Remote-User-Id for authenticated HA users).
    if request.content_type != "application/json":
        raise web.HTTPUnsupportedMediaType(text="JSON required")
    if not _user(request):
        raise web.HTTPForbidden(text="Setup must be started from Home Assistant.")
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.get("confirm") is not True:
        raise web.HTTPBadRequest(text="Missing confirmation")
    state = request.app[K_STATE]
    try:
        admin = await state.core.is_admin(_user(request))
    except CoreError:
        raise web.HTTPServiceUnavailable(text="Couldn't verify administrator access. Continue in the Home Assistant App Store.") from None
    if not admin:
        raise web.HTTPForbidden(text="A Home Assistant administrator must start setup.")
    op = state.setup.start(_user(request))
    return _json({"operation": op.to_dict()}, status=202)


async def api_music_operation(request: web.Request) -> web.Response:
    return _json({"operation": request.app[K_STATE].setup.snapshot()})


async def household_admin(request: web.Request) -> State:
    state = request.app[K_STATE]
    if not _user(request):
        raise web.HTTPForbidden(text="Open screen setup from Home Assistant.")
    try:
        if not await state.core.is_admin(_user(request)):
            raise web.HTTPForbidden(text="A Home Assistant administrator manages people and screens.")
    except CoreError:
        raise web.HTTPServiceUnavailable(text="Could not verify administrator access.") from None
    return state


async def household_body(request: web.Request) -> dict:
    if request.content_type != "application/json":
        raise web.HTTPUnsupportedMediaType(text="JSON required")
    try:
        value = await request.json()
    except ValueError:
        value = None
    if not isinstance(value, dict):
        raise web.HTTPBadRequest(text="Invalid screen settings.")
    return value


async def api_household(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        house = state.household.load()
        inventory = await collect_inventory(state.core)
        states = await state.core.states()
        return _json(
            {
                "household": house,
                "profiles": PROFILES,
                "areas": inventory["areas"],
                "items": classify(inventory, states, house["overrides"]),
                "inventory_complete": inventory["complete"],
            }
        )
    except (OSError, ValueError, KeyError, TypeError, CoreError):
        return _json({"error": "Could not read household settings or the house. Existing saved data is preserved."}, 503)


async def api_save_household(request: web.Request) -> web.Response:
    state = await household_admin(request)
    value = await household_body(request)
    try:
        value = validate_household(value)
        async with state.household_lock:
            inventory = await collect_inventory(state.core)
            if not inventory["complete"]:
                raise ValueError("House inventory is incomplete. Refresh before changing screen settings.")
            area_ids = {a["area_id"] for a in inventory["areas"]}
            entities = {e["entity_id"] for d in inventory["devices"] for e in d["entities"]} | {e["entity_id"] for e in inventory["unattached_entities"]}
            if any(s["area_id"] is not None and s["area_id"] not in area_ids for s in value["surfaces"]):
                raise ValueError("A selected room no longer exists. Refresh first.")
            if not set(value["overrides"]) <= entities or any(a["entity_id"] not in entities for a in value["activities"]):
                raise ValueError("A selected household control no longer exists. Refresh first.")
            saved = state.household.save(value)
            state.previews.clear()
        return _json({"household": saved, "saved": True})
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (OSError, CoreError):
        return _json({"error": "Settings could not be saved. Refresh to check before retrying."}, 503)


async def api_surface_preview(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        async with state.household_lock:
            house = state.household.load()
            surface = next((s for s in house["surfaces"] if s["id"] == request.match_info["surface"]), None)
            if surface is None:
                raise ValueError("Save this screen before generating it.")
            inventory = await collect_inventory(state.core)
            if not inventory["complete"]:
                raise ValueError("House inventory is incomplete. No dashboard will be published.")
            items = classify(inventory, await state.core.states(), house["overrides"])
            async with state.activity_lock:
                activities = await update_activity(state.core, state.household, house["activities"])
            generated = generate(house, surface, items, inventory["areas"], activities)
            records = state.household.read(state.household.publication_path, {})
            token = secrets.token_hex(16)
            # One recent preview per screen, bounded by the validated screen count.
            state.previews[surface["id"]] = {
                "generated": generated,
                "token": token,
                "revision": house["revision"],
                "user": _user(request),
                "at": time.monotonic(),
                "expected": records.get(generated["url_path"], {}).get("fingerprint"),
            }
            return _json(
                {
                    **generated,
                    "preview_token": token,
                    "published": records.get(generated["url_path"]),
                    "warnings": [w for w in generated["warnings"] if not w.startswith("Activity today is a snapshot")],
                }
            )
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (OSError, CoreError, KeyError, TypeError):
        return _json({"error": "Could not generate this screen. Saved settings and existing dashboards are preserved."}, 503)


async def api_surface_publish(request: web.Request) -> web.Response:
    state = await household_admin(request)
    body = await household_body(request)
    if set(body) != {"preview_token", "confirm"} or body.get("confirm") is not True:
        raise web.HTTPBadRequest(text="Review and confirm the generated screen.")
    try:
        async with state.household_lock:
            preview = state.previews.get(request.match_info["surface"])
            if not preview or preview["token"] != body["preview_token"] or preview["user"] != _user(request):
                raise ValueError("Generate and review this screen first.")
            if time.monotonic() - preview["at"] > 600 or preview["revision"] != state.household.load()["revision"]:
                raise ValueError("This preview expired or settings changed. Generate it again.")
            records = state.household.read(state.household.publication_path, {})
            result = await publish(state.core, preview["generated"], preview["expected"], records)
            records[result["url_path"]] = result
            state.household.write(state.household.publication_path, records)
            state.previews.pop(request.match_info["surface"], None)
            return _json(result)
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (CoreError, OSError):
        return _json({"error": "Dashboard publication was not verified. It may have been created or saved. Inspect it in Home Assistant before retrying."}, 409)


# ---- app factory -----------------------------------------------------------


def create_app(settings: Settings, session: aiohttp.ClientSession | None = None) -> web.Application:
    app = web.Application(middlewares=[peer_guard, harden])
    app[K_SETTINGS] = settings

    async def on_startup(app: web.Application) -> None:
        own = session is None
        sess = session or aiohttp.ClientSession()
        app[K_STATE] = State(settings, sess)
        app[K_OWN_SESSION] = own
        app[K_STATE].activity_task = asyncio.create_task(app[K_STATE].monitor_activity())

    async def on_cleanup(app: web.Application) -> None:
        if task := app[K_STATE].activity_task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if app.get(K_OWN_SESSION):
            await app[K_STATE].session.close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", index)
    app.router.add_get("/static/{name}", static)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/scan", api_scan)
    app.router.add_get("/api/inventory", api_inventory)
    app.router.add_get("/api/household", api_household)
    app.router.add_post("/api/household", api_save_household)
    app.router.add_get("/api/surfaces/{surface}/preview", api_surface_preview)
    app.router.add_post("/api/surfaces/{surface}/publish", api_surface_publish)
    app.router.add_post("/api/inventory/area", api_assign_area)
    app.router.add_get("/api/music", api_music)
    app.router.add_post("/api/music/setup", api_music_setup)
    app.router.add_get("/api/music/operation", api_music_operation)
    return app
