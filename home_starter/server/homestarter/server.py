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
from datetime import UTC, datetime
from importlib import resources
from typing import Any

import aiohttp
from aiohttp import web

from . import __version__, commissioning, context, context_runtime, readiness, screen_identity, this_house, waste, waste_runtime
from .activity import update_activity
from .core import CoreClient, CoreError
from .household import PROFILES, HouseholdStore, validate_household
from .inventory import assign_area, collect_inventory
from .music import MusicSetup, evaluate, gather_facts
from .music_runtime import MusicRuntime, MusicRuntimeError
from .music_runtime import digest as music_digest
from .reconcile import acknowledge, observe
from .scan import ha_version_from_scan, run_scan
from .settings import Settings
from .supervisor import SupervisorClient, SupervisorError
from .surfaces import classify, fingerprint, generate, publish
from .wodonga import WodongaProvider

_LOGGER = logging.getLogger(__name__)

INGRESS_PATH_RE = re.compile(r"^/api/hassio_ingress/[A-Za-z0-9_\-]{1,128}$")
STATIC_FILES = {
    "app.js": "text/javascript",
    "routes.js": "text/javascript",
    "house.js": "text/javascript",
    "this-house.js": "text/javascript",
    "context.js": "text/javascript",
    "screen-identity.js": "text/javascript",
    "waste.js": "text/javascript",
    "surfaces.js": "text/javascript",
    "installation.js": "text/javascript",
    "readiness.js": "text/javascript",
    "commissioning.js": "text/javascript",
    "music-runtime.js": "text/javascript",
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
        self.music_runtime = MusicRuntime(self.supervisor, session, settings.data_dir, settings.music_assistant_port)
        self.scan: dict[str, Any] | None = None
        self.scan_at = 0.0
        self.scan_lock = asyncio.Lock()
        self.inventory_write_lock = asyncio.Lock()
        self.household_lock = asyncio.Lock()
        self.activity_lock = asyncio.Lock()
        self.household = HouseholdStore(settings.data_dir)
        self.previews: dict[str, dict] = {}
        self.activity_task: asyncio.Task | None = None
        self.commissioning_task: asyncio.Task | None = None
        self.context_task: asyncio.Task | None = None
        self.waste_task: asyncio.Task | None = None
        self.waste_provider = WodongaProvider(session)
        self.waste_previews: dict[str, dict] = {}

    async def monitor_waste(self) -> None:
        while True:
            try:
                async with asyncio.timeout(55), self.household_lock:
                    await waste_runtime.tick(self.waste_provider, self.core, self.household)
            except (CoreError, OSError, ValueError, KeyError, TypeError, TimeoutError):
                _LOGGER.warning("Waste context unavailable; native bin entities expire safely. Saved schedule preserved.")
            await asyncio.sleep(60)

    async def monitor_context(self) -> None:
        while True:
            try:
                await context_runtime.update(self.core, self.household)
            except (CoreError, OSError, ValueError, KeyError, TypeError):
                _LOGGER.warning("Household context could not refresh; wall content expires rather than keeping old events.")
            await asyncio.sleep(60)

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
        result = evaluate(facts, operation)
        try:
            runtime = await self.music_runtime.snapshot()
            result["runtime"] = {k: runtime.get(k) for k in ("connected", "proof")}
        except (MusicRuntimeError, SupervisorError, OSError, ValueError, KeyError, TypeError):
            result["runtime"] = {"connected": False, "proof": None}
        return result

    async def installation(self) -> dict:
        async with self.household_lock:
            house = self.household.load()
            inventory = await collect_inventory(self.core)
            items = classify(inventory, await self.core.states(), house["overrides"]) if inventory["complete"] else []
            observation = observe(self.household, house, inventory, items)
            screens = await screen_status(self.core, house, self.household.read(self.household.publication_path, {}))
            identities = await screen_identity.inspect(self.core, self.household, house, screens)
            for screen in screens:
                screen["commissioning"] = next(r for r in identities["screens"] if r["id"] == screen["id"])
        try:
            music = await self.music()
            proof = music.get("runtime", {}).get("proof")
            music = {
                "state": music["state"],
                "verified": bool(proof),
                "title": "Playback verified for the chosen source and speaker; other paths untested."
                if proof
                else "Provider and speaker playback unverified. " + music["title"],
            }
        except (CoreError, SupervisorError, ValueError, KeyError, TypeError):
            music = {"state": "unavailable", "title": "Music check unavailable", "verified": False}
        return {
            "first_run": not house["configured"],
            "revision": house["revision"],
            "epoch": house["epoch"],
            "counts": {"people": len(house["people"]), "screens": len(house["surfaces"]), "activities": len(house["activities"])},
            "screens": screens,
            "music": music,
            "inventory_complete": inventory["complete"],
            "changes": list(observation["pending"].values()),
            "observation_revision": observation["revision"],
            "baseline_created": observation["baseline_created"],
            "climate_available": any(i["usable"] and i["function"] == "climate" for i in items),
            "unavailable": [
                {"kind": v["kind"], "label": v["label"]}
                for v in observation["known"].values()
                if v.get("unavailable") or v.get("status") in ("unavailable", "offline", "setup_error", "setup_retry", "migration_error")
            ],
            "app_version": __version__,
        }


# ---- middlewares ---------------------------------------------------------


@web.middleware
async def peer_guard(request: web.Request, handler):
    settings = request.app[K_SETTINGS]
    if not settings.allow_any_peer and request.remote not in settings.allowed_peers:
        _LOGGER.warning("Rejected a request outside authenticated ingress.")
        raise web.HTTPForbidden(text="Home Starter is only available through Home Assistant.")
    return await handler(request)


@web.middleware
async def harden(request: web.Request, handler):
    try:
        if (
            request.method == "POST"
            and request.path.startswith("/api/")
            and not request.path.startswith("/api/commissioning/")
            and request.path != "/api/installation/reset"
            and not request.path.startswith("/api/music/runtime")
        ):
            await household_admin(request)
            try:
                commissioning.gate(request.app[K_STATE].household)
            except ValueError as error:
                raise web.HTTPConflict(text=str(error)) from None
        response = await handler(request)
    except web.HTTPException as exc:
        response = exc
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("Cache-Control", "no-store")
    # Neither service credential may leave the server, even through provider metadata.
    tokens = [request.app[K_SETTINGS].token.reveal()]
    try:
        connection = request.app[K_STATE].music_runtime.connection()
        if connection:
            tokens.append(connection["token"].reveal())
    except (MusicRuntimeError, OSError, ValueError):
        pass
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)) and any(token and token.encode() in body for token in tokens):
        _LOGGER.error("Blocked a response that contained a service credential")
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


async def api_music_runtime(request):
    state = await household_admin(request)
    try:
        runtime = state.music_runtime
        if request.method == "POST":
            body = await household_body(request)
            action = request.match_info["action"]
            if action == "connect" and set(body) == {"token"}:
                await runtime.connect(body["token"])
            elif action == "observe" and set(body) == {"provider_id", "player_id"} and all(isinstance(v, str) for v in body.values()):
                return _json(await runtime.observe(body["provider_id"], body["player_id"], _user(request)))
            elif action in ("heard", "decline") and set(body) == {"id", "confirm"} and body["confirm"] is True and isinstance(body["id"], str):
                await getattr(runtime, action)(body["id"], _user(request))
            else:
                raise ValueError("Review the Music action and try again.")
        result = await runtime.snapshot()
        pending = runtime.evidence().get("pending", {})
        if pending.get("owner") != music_digest(_user(request)):
            result.pop("pending", None)
        return _json(result)
    except MusicRuntimeError as error:
        return _json({"error": str(error)}, 409)
    except (SupervisorError, OSError, KeyError, TypeError):
        return _json({"error": "Music could not be checked. Existing settings are preserved; retry."}, 503)
    except ValueError as error:
        return _json({"error": str(error)}, 400)


async def api_inventory(request: web.Request) -> web.Response:
    try:
        return _json(await collect_inventory(request.app[K_STATE].core))
    except (KeyError, TypeError, ValueError, AttributeError):
        return _json({"error": "Couldn't read the house inventory. Check again."}, status=503)


async def api_this_house(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        async with state.household_lock, state.inventory_write_lock:
            if request.method == "GET":
                return _json(await this_house.inspect(state.core, state.household))
            commissioning.gate(state.household)
            body = await household_body(request)
            return _json(await this_house.act(state.core, state.household, request.match_info["action"], body))
    except ValueError as error:
        return _json({"error": str(error), "verified": False}, 409)
    except (CoreError, OSError, KeyError, TypeError, AttributeError):
        return _json(
            {"error": "House changes could not be verified. HA may have changed; refresh before retrying. Saved settings are preserved.", "verified": False},
            503,
        )


async def api_house_readiness(request: web.Request) -> web.Response:
    state = await household_admin(request)
    checks = {"music": None, "screens": None, "readiness": None}
    try:
        house = state.household.load()
        try:
            checks["readiness"] = readiness.load(state.household, house)
        except (ValueError, OSError, KeyError, TypeError):
            pass
        try:
            checks["waste"] = await waste_runtime.inspect(state.core, state.household)
        except (ValueError, OSError, KeyError, TypeError, CoreError):
            checks["waste"] = None
        try:
            checks["screens"] = await screen_status(state.core, house, state.household.read(state.household.publication_path, {}))
            identities = await screen_identity.inspect(state.core, state.household, house, checks["screens"])
            for screen in checks["screens"]:
                screen["commissioning"] = next(r for r in identities["screens"] if r["id"] == screen["id"])
        except (ValueError, OSError, KeyError, TypeError, CoreError):
            pass
    except (ValueError, OSError, KeyError, TypeError):
        pass
    try:
        snapshot = await state.music_runtime.snapshot()
        checks["music"] = {k: snapshot.get(k) for k in ("connected", "proof")}
    except (MusicRuntimeError, CoreError, SupervisorError, OSError, ValueError, KeyError, TypeError):
        pass
    try:
        view = await this_house.inspect(state.core, state.household, checks)
        return _json({"capabilities": view["capabilities"], "checked_at": datetime.now(UTC).isoformat()})
    except (ValueError, OSError, KeyError, TypeError, CoreError):
        return _json({"error": "Household readiness could not be read. House records and saved checks are preserved."}, 503)


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
        async with state.household_lock, state.inventory_write_lock:
            commissioning.gate(state.household)
            result = await assign_area(state.core, body["device_id"], body["area_id"], body["expected_area_id"])
    except (CoreError, ValueError):
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
    try:
        async with state.household_lock:
            commissioning.gate(state.household)
            state.household.save(state.household.load())
    except (OSError, ValueError):
        return _json({"error": "Could not persist existing setup. Music installation was not started."}, 503)
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


async def screen_status(core: CoreClient, house: dict, records: dict) -> list[dict]:
    result = [
        {"id": s["id"], "name": s["name"], "profile": s["profile"], "url_path": "home-starter-" + s["id"].replace("_", "-"), "status": "unpublished"}
        for s in house["surfaces"]
    ]
    if not result:
        return result
    try:
        async with core.websocket() as ws:
            dashboards = await ws.command("lovelace/dashboards/list")
            paths = {d["url_path"] for d in dashboards}
            for screen in result:
                path = screen["url_path"]
                if path not in records:
                    screen["status"] = "untracked" if path in paths else "unpublished"
                elif path not in paths:
                    screen["status"] = "missing"
                else:
                    try:
                        current = await ws.command("lovelace/config", url_path=path, force=True)
                        screen["status"] = "published" if fingerprint(current) == records[path]["fingerprint"] else "external_edits"
                        screen["fingerprint"] = fingerprint(current)
                    except CoreError:
                        screen["status"] = "unavailable"
    except CoreError:
        for screen in result:
            screen["status"] = "unavailable"
    return result


async def api_installation(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        return _json(await state.installation())
    except (OSError, ValueError, KeyError, TypeError, CoreError):
        return _json({"error": "Existing setup could not be read safely. Restore or repair runtime data; onboarding was not restarted."}, 503)


async def api_screen_identity(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        async with state.household_lock:
            house = state.household.load()
            publications = await screen_status(state.core, house, state.household.read(state.household.publication_path, {}))
            if request.method == "POST":
                commissioning.gate(state.household)
                await screen_identity.apply(state.core, state.household, house, publications, await household_body(request), _user(request))
            return _json(await screen_identity.inspect(state.core, state.household, house, publications))
    except ValueError as error:
        return _json({"error": str(error), "verified": False}, 409)
    except (CoreError, OSError, KeyError, TypeError, AttributeError):
        return _json(
            {
                "error": "Display commissioning could not be verified. Refresh and inspect the saved state before retrying; no password is handled here.",
                "verified": False,
            },
            503,
        )


async def api_waste(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        if request.method == "GET":
            return _json(await waste_runtime.inspect(state.core, state.household))
        body = await household_body(request)
        if body.get("action") == "preview":
            if set(body) != {"action", "day"}:
                raise ValueError("Choose automatic location matching or one known collection weekday.")
            house = state.household.load()
            async with asyncio.timeout(55):
                candidate = await waste.candidate(state.waste_provider, state.core, body["day"])
            token = secrets.token_urlsafe(24)
            prepared = {
                "token": token,
                "at": datetime.now(UTC).isoformat(),
                "candidate": candidate,
                "house_revision": house["revision"],
                "epoch": house["epoch"],
            }
            state.waste_previews[_user(request)] = prepared
            value = waste.load(state.household, house)
            value.update(candidate)
            return _json({"preview_token": token, "proposal": waste.view(value, (await state.core.config())["time_zone"])})
        async with state.household_lock:
            commissioning.gate(state.household)
            house = state.household.load()
            value = waste.load(state.household, house)
            action = body.get("action")
            if action == "confirm":
                prepared = state.waste_previews.get(_user(request))
                if not prepared or prepared["house_revision"] != house["revision"] or prepared["epoch"] != house["epoch"]:
                    raise ValueError("Household screens changed; check the waste service again.")
                waste.confirm(state.household, house, body, prepared)
                state.waste_previews.pop(_user(request), None)
                await waste_runtime.prepare(state.core, state.household, house)
                await waste_runtime.project(state.core, state.household, house)
            elif action in {"refresh", "prepare"}:
                if (
                    set(body) != {"action", "revision", "epoch", "confirm"}
                    or body["confirm"] is not True
                    or type(body["revision"]) is not int
                    or body["revision"] != value["revision"]
                    or type(body["epoch"]) is not int
                    or body["epoch"] != house["epoch"]
                ):
                    raise ValueError("Refresh and confirm the current waste action.")
                if action == "refresh":
                    async with asyncio.timeout(55):
                        await waste.refresh(state.waste_provider, state.core, state.household, house)
                else:
                    await waste_runtime.prepare(state.core, state.household, house)
                await waste_runtime.project(state.core, state.household, house)
            else:
                raise ValueError("Choose a supported waste setup action.")
        return _json(await waste_runtime.inspect(state.core, state.household))
    except ValueError as error:
        return _json({"error": str(error)}, 409)
    except (CoreError, OSError, KeyError, TypeError, TimeoutError):
        return _json({"error": "Waste setup could not be verified. Saved schedule and existing household choices are preserved; refresh before retrying."}, 503)


async def commissioning_payload(state, value, discovery=False):
    result = {"state": value, "profiles": PROFILES}
    if discovery and value["scan"] is not None and value["active"]:
        inventory = await collect_inventory(state.core)
        states = await state.core.states()
        try:
            music = await state.music()
        except (CoreError, SupervisorError, ValueError):
            music = {"state": "unavailable"}
        result["discovery"] = readiness.report(value["draft"]["house"], value["draft"]["readiness"], inventory, states, music)
        result["music"] = {k: music.get(k) for k in ("state", "title", "open_path", "handoff_path")}
    return result


async def api_commissioning(request):
    state = await household_admin(request)
    try:
        value = commissioning.load(state.household)
        if value["phase"] == "executing" and (state.commissioning_task is None or state.commissioning_task.done()):
            value["phase"] = "verification_incomplete"
            value["results"]["execution"] = {
                "status": "incomplete",
                "detail": "Execution stopped. Inspect saved work, then retry; nothing was replayed on launch.",
            }
            commissioning.write(state.household, value)
        return _json(await commissioning_payload(state, value, discovery=value["phase"] != "executing"))
    except (OSError, ValueError, KeyError, TypeError, CoreError):
        return _json({"error": "Could not safely read commissioning. Saved setup is preserved. Restore runtime data or retry."}, 503)


async def api_commissioning_action(request):
    state = await household_admin(request)
    body = await household_body(request)
    action = request.match_info["action"]
    fields = {"revision", "epoch"} | {"save": {"draft", "step"}, "go": {"token", "confirm"}, "skip": {"key", "confirm"}, "display": {"key", "confirm"}}.get(
        action, set()
    )
    if set(body) != fields:
        raise web.HTTPBadRequest(text="Use the current commissioning step.")
    try:
        async with state.household_lock:
            store = state.household
            value = commissioning.load(store)
            commissioning.precondition(value, body)
            if value["phase"] == "executing":
                raise ValueError("Setup is running. Wait for its result before changing the plan.")
            if action == "start":
                value = commissioning.begin(store, value)
            elif action == "scan":
                if value["phase"] in ("not_started", "commissioned", "verification_incomplete"):
                    raise ValueError("Prepare the house before scanning this setup plan.")
                inventory, states = await collect_inventory(state.core), await state.core.states()
                if not inventory["complete"]:
                    raise ValueError("The scan is incomplete. Saved choices are retained; check access and retry.")
                value.update(phase="scanned", scan=commissioning.summary(inventory, states), review=None)
                commissioning.write(store, value)
            elif action == "save":
                value = commissioning.save_draft(store, value, body["draft"], body["step"], await collect_inventory(state.core), await state.core.states())
            elif action == "review":
                value = await commissioning.make_review(
                    store, value, state.core, await collect_inventory(state.core), await state.core.states(), await state.music()
                )
            elif action in ("go", "retry"):
                if action == "go":
                    if body["confirm"] is not True:
                        raise ValueError("Review and confirm Set up my home.")
                    commissioning.check_go(store, value, body["token"], await collect_inventory(state.core), await state.core.states())
                elif value["phase"] != "verification_incomplete":
                    raise ValueError("There is no incomplete execution to retry.")
                else:
                    if commissioning.source_signature(await collect_inventory(state.core), await state.core.states()) != value["review"]["source_signature"]:
                        raise ValueError("Sources changed. Edit and review the plan before retrying.")
                    value["results"].pop("execution", None)
                value["phase"] = "executing"
                commissioning.write(store, value)
                state.commissioning_task = asyncio.create_task(
                    commissioning.execute(store, value, state.core, state.setup, _user(request), state.music_runtime)
                )
            elif action == "edit":
                if value["phase"] not in ("verification_incomplete", "reviewed"):
                    raise ValueError("There is no reviewed plan to edit.")
                if value["phase"] == "verification_incomplete":
                    value["draft"]["house"] = store.load()
                    value["draft"]["readiness"] = readiness.load(store, value["draft"]["house"])
                value.update(phase="configuration_incomplete", review=None, results={})
                commissioning.write(store, value)
            elif action in ("skip", "display"):
                key = body["key"]
                if (
                    value["phase"] != "verification_incomplete"
                    or body["confirm"] is not True
                    or key not in value["results"]
                    or key in ("household", "execution", "music_installer")
                ):
                    raise ValueError("Review an incomplete capability or display first.")
                if action == "display":
                    item = next((s for s in value["review"]["screens"] if "display:" + s["generated"]["surface"]["id"] == key), None)
                    if not item or value["results"][key]["status"] != "published":
                        raise ValueError("Publish and open this screen before confirming its display.")
                    async with state.core.websocket() as ws:
                        current = await ws.command("lovelace/config", url_path=item["generated"]["url_path"], force=True)
                    if fingerprint(current) != item["generated"]["fingerprint"]:
                        raise ValueError("This screen changed. Inspect it before confirming.")
                    value["results"][key].update(
                        status="verified", detail="Publication readback matched; user confirmed it opened correctly.", verification="user_confirmed_display"
                    )
                else:
                    value["results"][key].update(status="skipped", detail="Deliberately skipped for now; not verified.")
                    if key in readiness.CAPABILITIES:
                        rd = readiness.load(store, store.load())
                        rd["choices"][key]["intent"] = "later"
                        rd["revision"] += 1
                        store.write(store.readiness_path, rd)
                commissioning.finish(store, value)
            elif action == "leave" and value["legacy"] and value["phase"] not in ("executing", "verification_incomplete"):
                value["active"] = False
                commissioning.write(store, value)
            else:
                raise ValueError("Unsupported commissioning action.")
            state.previews.clear()
        return _json(await commissioning_payload(state, value, discovery=action == "scan"))
    except ValueError as error:
        return _json({"error": str(error)}, 409)
    except (CoreError, SupervisorError, OSError, KeyError, TypeError):
        return _json({"error": "This step could not be verified. Saved work is retained. Retry or repair the source."}, 503)


async def api_installation_action(request: web.Request) -> web.Response:
    state = await household_admin(request)
    body = await household_body(request)
    action = request.match_info["action"]
    fields = {"confirm", "revision", "acknowledgement"} if action == "reset" else {"confirm", "revision"}
    if set(body) != fields or body.get("confirm") is not True or type(body.get("revision")) is not int:
        raise web.HTTPBadRequest(text="Review and confirm this setup action.")
    try:
        async with state.household_lock:
            house = state.household.load()
            if action != "reset":
                commissioning.gate(state.household)
            elif state.commissioning_task and not state.commissioning_task.done():
                raise ValueError("Wait for the running setup to finish before resetting its state.")
            if action == "complete":
                if house["revision"] != body["revision"]:
                    raise ValueError("Settings changed. Refresh before finishing review.")
                state.household.save(house)
            elif action == "review":
                inventory = await collect_inventory(state.core)
                if not inventory["complete"]:
                    raise ValueError("Inventory is incomplete. No differences were marked reviewed.")
                observe(state.household, house, inventory, classify(inventory, await state.core.states(), house["overrides"]))
                acknowledge(state.household, house, body["revision"])
            elif action == "reset":
                if body["acknowledgement"] != "RESET HOME STARTER":
                    raise ValueError("Type RESET HOME STARTER to confirm the described reset.")
                async with state.activity_lock:
                    state.household.reset(body["revision"])
            else:
                raise web.HTTPNotFound()
            state.previews.clear()
        return _json({"saved": True})
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (OSError, CoreError):
        return _json({"error": "The action could not be verified. Refresh before retrying; existing data is preserved."}, 503)


async def api_readiness(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        async with state.household_lock:
            house = state.household.load()
            value = readiness.load(state.household, house)
            inventory = await collect_inventory(state.core)
            states = await state.core.states()
        try:
            music = await state.music()
        except (CoreError, SupervisorError, ValueError):
            music = {"state": "unavailable"}
        result = readiness.report(house, value, inventory, states, music)
        row = next(r for r in result["rows"] if r["id"] == "waste")
        row["route"] = "#waste-collection"
        row["questions"] = ["Check the Council service and confirm your collection day in Waste collection."]
        row["provider_service"] = True
        try:
            bins = await waste_runtime.inspect(state.core, state.household)
            row["provider_configured"] = bins["configured"]
            if bins["configured"]:
                row["status"] = bins["message"] + (" " + bins["entity_issue"] if bins["entity_issue"] else "")
                row["guide"] = [bins["day"] + " · Green weekly · Recycling/General alternating"]
        except (ValueError, OSError, KeyError, TypeError, CoreError):
            row["status"] = "Bin schedule needs checking; saved data preserved."
        return _json(result)
    except (OSError, ValueError, KeyError, TypeError, CoreError):
        return _json({"error": "Readiness could not be read safely. Saved setup is preserved."}, 503)


async def api_readiness_action(request: web.Request) -> web.Response:
    state = await household_admin(request)
    body = await household_body(request)
    try:
        async with state.household_lock:
            commissioning.gate(state.household)
            house = state.household.load()
            inventory = await collect_inventory(state.core)
            states = await state.core.states()
            if request.match_info["action"] == "save":
                value = readiness.save(state.household, house, body, inventory, states, persist=False)
                state.household.save(house)
                if value != readiness.load(state.household, house):
                    state.household.write(state.household.readiness_path, value)
            elif request.match_info["action"] == "verify":
                current = readiness.load(state.household, house)
                if (
                    set(body) != {"revision", "epoch", "capability", "confirm"}
                    or body["confirm"] is not True
                    or type(body["revision"]) is not int
                    or type(body["epoch"]) is not int
                    or body["revision"] != current["revision"]
                    or body["epoch"] != house["epoch"]
                    or body["capability"] not in readiness.CAPABILITIES
                ):
                    raise ValueError("Save and review current readiness choices before verifying.")
                value = await readiness.verify(state.core, current, body["capability"], inventory, states)
                state.household.write(state.household.readiness_path, value)
            else:
                raise web.HTTPNotFound()
            state.previews.clear()
        return _json({"saved": True, "state": value})
    except ValueError as error:
        return _json({"error": str(error)}, 409)
    except (OSError, CoreError, KeyError, TypeError):
        return _json({"error": "Readiness action could not be verified. Refresh and retry; no HA configuration was changed."}, 503)


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
            commissioning.gate(state.household)
            current = state.household.load()
            inventory = await collect_inventory(state.core)
            if not inventory["complete"]:
                raise ValueError("House inventory is incomplete. Refresh before changing screen settings.")
            area_ids = {a["area_id"] for a in inventory["areas"]}
            entities = {e["entity_id"] for d in inventory["devices"] for e in d["entities"]} | {e["entity_id"] for e in inventory["unattached_entities"]}
            retained_rooms = {(s["id"], s["area_id"]) for s in current["surfaces"]}
            if any(s["area_id"] is not None and s["area_id"] not in area_ids and (s["id"], s["area_id"]) not in retained_rooms for s in value["surfaces"]):
                raise ValueError("A selected room no longer exists. Refresh first.")
            retained_rules = {(a["id"], a["entity_id"]) for a in current["activities"]}
            if not set(value["overrides"]) <= entities | set(current["overrides"]) or any(
                a["entity_id"] not in entities and (a["id"], a["entity_id"]) not in retained_rules for a in value["activities"]
            ):
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
            policy = readiness.policy_for(readiness.load(state.household, house), house, inventory, await state.core.states())
            waste_issue = False
            try:
                policy = waste.screen_policy(policy, waste.load(state.household, house)["confirmed"])
            except (ValueError, OSError, KeyError, TypeError):
                waste_issue = True
            generated = generate(house, surface, items, inventory["areas"], activities, policy)
            if waste_issue:
                generated["warnings"].append("Bin schedule unavailable; existing screen choices preserved.")
            if surface["profile"] == "wall":
                generated["context_preview"] = await context_runtime.inspect(state.core, state.household, surface)
            records = state.household.read(state.household.publication_path, {})
            token = secrets.token_hex(16)
            # One recent preview per screen, bounded by the validated screen count.
            state.previews[surface["id"]] = {
                "generated": generated,
                "token": token,
                "revision": house["revision"],
                "readiness_revision": readiness.load(state.household, house)["revision"],
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
            commissioning.gate(state.household)
            preview = state.previews.get(request.match_info["surface"])
            if not preview or preview["token"] != body["preview_token"] or preview["user"] != _user(request):
                raise ValueError("Generate and review this screen first.")
            current_house = state.household.load()
            if (
                time.monotonic() - preview["at"] > 600
                or preview["revision"] != current_house["revision"]
                or preview["readiness_revision"] != readiness.load(state.household, current_house)["revision"]
            ):
                raise ValueError("This preview expired or settings changed. Generate it again.")
            records = state.household.read(state.household.publication_path, {})
            result = await publish(state.core, preview["generated"], preview["expected"], records)
            if preview["generated"]["surface"]["profile"] == "wall":
                result["context"] = 1
                result["context_epoch"] = current_house["epoch"]
            records[result["url_path"]] = result
            if records != state.household.read(state.household.publication_path, {}):
                state.household.write(state.household.publication_path, records)
            if result.get("context") == 1:
                try:
                    await context_runtime.update(state.core, state.household)
                except (CoreError, OSError, ValueError, KeyError, TypeError):
                    result["context_refresh"] = "pending; dashboard saved, context unavailable"
            state.previews.pop(request.match_info["surface"], None)
            return _json(result)
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (CoreError, OSError):
        return _json({"error": "Dashboard publication was not verified. It may have been created or saved. Inspect it in Home Assistant before retrying."}, 409)


# ---- app factory -----------------------------------------------------------


async def api_context(request: web.Request) -> web.Response:
    state = await household_admin(request)
    try:
        view = await context_runtime.inspect(state.core, state.household)
        if request.method == "GET":
            return _json(view)
        body = await household_body(request)
        async with state.household_lock:
            commissioning.gate(state.household)
            house = state.household.load()
            saved = readiness.load(state.household, house)
            if (
                set(body) != {"revision", "epoch", "settings"}
                or type(body["revision"]) is not int
                or type(body["epoch"]) is not int
                or body["revision"] != saved["revision"]
                or body["epoch"] != house["epoch"]
            ):
                raise ValueError("Context changed. Refresh before saving.")
            settings = context.validate(body["settings"])
            known = view["people"].keys()
            if any(not set(r["people"]) <= known for r in settings["rules"] + list(settings["events"].values())):
                raise ValueError("Confirm these existing HA people in This House first.")
            if not set(settings["events"]) <= {e["key"] for e in view["events"]} | saved["context"]["events"].keys():
                raise ValueError("The chosen event changed. Refresh and review it again.")
            saved["context"] = settings
            saved["revision"] += 1
            state.household.write(state.household.readiness_path, saved)
            state.previews.clear()
        return _json(await context_runtime.inspect(state.core, state.household))
    except ValueError as err:
        return _json({"error": str(err)}, 409)
    except (CoreError, OSError, KeyError, TypeError):
        return _json({"error": "Household context unavailable. Saved choices are preserved."}, 503)


def create_app(settings: Settings, session: aiohttp.ClientSession | None = None) -> web.Application:
    app = web.Application(middlewares=[peer_guard, harden])
    app[K_SETTINGS] = settings

    async def on_startup(app: web.Application) -> None:
        own = session is None
        sess = session or aiohttp.ClientSession()
        app[K_STATE] = State(settings, sess)
        app[K_OWN_SESSION] = own
        app[K_STATE].activity_task = asyncio.create_task(app[K_STATE].monitor_activity())
        app[K_STATE].context_task = asyncio.create_task(app[K_STATE].monitor_context())
        app[K_STATE].waste_task = asyncio.create_task(app[K_STATE].monitor_waste())

    async def on_cleanup(app: web.Application) -> None:
        if task := app[K_STATE].waste_task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if task := app[K_STATE].context_task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        if task := app[K_STATE].commissioning_task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
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
    app.router.add_get("/api/house", api_this_house)
    app.router.add_get("/api/context", api_context)
    app.router.add_post("/api/context", api_context)
    app.router.add_get("/api/waste", api_waste)
    app.router.add_post("/api/waste", api_waste)
    app.router.add_get("/api/screens/identity", api_screen_identity)
    app.router.add_post("/api/screens/identity", api_screen_identity)
    app.router.add_get("/api/house/status", api_house_readiness)
    app.router.add_post("/api/house/{action}", api_this_house)
    app.router.add_get("/api/household", api_household)
    app.router.add_get("/api/commissioning", api_commissioning)
    app.router.add_post("/api/commissioning/{action}", api_commissioning_action)
    app.router.add_get("/api/readiness", api_readiness)
    app.router.add_post("/api/readiness/{action}", api_readiness_action)
    app.router.add_get("/api/installation", api_installation)
    app.router.add_post("/api/installation/{action}", api_installation_action)
    app.router.add_post("/api/household", api_save_household)
    app.router.add_get("/api/surfaces/{surface}/preview", api_surface_preview)
    app.router.add_post("/api/surfaces/{surface}/publish", api_surface_publish)
    app.router.add_post("/api/inventory/area", api_assign_area)
    app.router.add_get("/api/music", api_music)
    app.router.add_get("/api/music/runtime", api_music_runtime)
    app.router.add_post("/api/music/runtime/{action}", api_music_runtime)
    app.router.add_post("/api/music/setup", api_music_setup)
    app.router.add_get("/api/music/operation", api_music_operation)
    return app
