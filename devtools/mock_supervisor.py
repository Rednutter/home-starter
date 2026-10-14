"""A contract-faithful fake Home Assistant Supervisor for development and tests.

It serves the Supervisor v1 endpoints Home Starter uses, with payloads taken
from tests/fixtures/supervisor (which mirror supervisor 2026.10.1 source) and
the same role-based access rules as supervisor/api/middleware/security.py, so
permission failures look exactly like the real thing (a bare HTTP 403).

State is mutable so whole flows can be exercised: adding the Music Assistant
repository, installing it as a background job, starting it, Music Assistant
announcing itself to Home Assistant (a discovered flow), and the user
confirming the integration.

Core API (/core/api/*, /core/websocket) is either served from fixtures (fake
core) or proxied to a real Home Assistant Core given --core-url/--core-token,
mimicking the Supervisor's own proxy (token swap + supervisor/ and hassio/
websocket command filtering).

Run standalone:
    python devtools/mock_supervisor.py --port 8181 --scenario absent
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

FIX = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
TOKEN = os.environ.get("HOME_STARTER_DEV_TOKEN") or secrets.token_urlsafe(32)
MA_SLUG = "d5369777_music_assistant"
MA_REPO = "https://github.com/music-assistant/home-assistant-addon"

RE_SLUG = r"[-_.A-Za-z0-9]+"
API_BYPASS = re.compile(r"^(?:|/addons/self/(?!security|update)[^/]+|/addons/self/options/config|/info|/services.*|/discovery.*|/auth)$")
ROLE_ACCESS = {
    "default": re.compile(r"^(?:|/.+/info)$"),
    "manager": re.compile(
        r"^(?:|/.+/info|/addons(?:/" + RE_SLUG + r"/(?!security).+|/reload)?|/audio/.+|/auth/cache|/available_updates"
        r"|/backups.*|/cli/.+|/core/.+|/dns/.+|/docker/.+|/jobs/.+|/hardware/.+|/homeassistant/.+|/host/.+|/mounts.*"
        r"|/multicast/.+|/network/.+|/observer/.+|/os/(?!datadisk/wipe|ssh/authorized_keys).+|/refresh_updates"
        r"|/resolution/.+|/security/.+|/snapshots.*|/store.*|/supervisor/.+|/time/.+)$"
    ),
    "admin": re.compile(r".*"),
}
NO_SECURITY_CHECK = re.compile(r"^(?:|/core/api/.*|/core/websocket|/supervisor/ping)$")


def sup(name: str) -> Any:
    return json.loads((FIX / "supervisor" / name).read_text())["data"]


def core_fix(name: str) -> Any:
    return json.loads((FIX / "core" / name).read_text())


def ok(data: Any = None) -> web.Response:
    return web.json_response({"result": "ok", "data": data if data is not None else {}})


def err(message: str, status: int = 400) -> web.Response:
    return web.json_response({"result": "error", "message": message}, status=status)


SCENARIOS = (
    "absent",
    "no_repo",
    "installed_stopped",
    "running_no_integration",
    "discovered",
    "ready",
    "integration_error",
    "not_onboarded",
    "beta_running",
    "unavailable",
    "default_role",
    "install_fails",
)


class MockSupervisor:
    def __init__(
        self,
        scenario: str = "absent",
        *,
        job_ticks: int = 3,
        start_ticks: int = 2,
        core_url: str | None = None,
        core_token: str | None = None,
        ma_host: str | None = None,
    ) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario {scenario}")
        self.scenario = scenario
        self.job_ticks = job_ticks
        self.start_ticks = start_ticks
        self.core_url = core_url.rstrip("/") if core_url else None
        self.core_token = core_token
        self.ma_host = ma_host
        self.ma_port = 8195
        self.users = [{"id": "a1b2c3d4e5f6", "is_active": True, "is_owner": True, "group_ids": ["system-admin"], "system_generated": False}]
        self.calls: list[tuple[str, str]] = []
        self.ws_calls: list[dict[str, Any]] = []
        self.calendar_events: dict[str, list[dict]] = {}
        self.devices = core_fix("device_registry_list.json")
        self.entity_registry = core_fix("inventory_entity_registry_list.json")
        self.dashboard_configs: dict[str, Any] = {}
        self.dashboards: list[dict] = []
        self.activity_states: dict[str, dict] = {}
        self.role = "default" if scenario == "default_role" else "manager"
        self.repos = sup("store_repositories.json" if scenario != "no_repo" else "store_repositories_without_ma.json")
        self.store = sup("store_addons.json" if scenario != "no_repo" else "store_addons_without_ma_repo.json")["addons"]
        if scenario == "unavailable":
            self.store = sup("store_addons_ma_unavailable.json")["addons"]
        self.installed = sup("addons_without_ma.json")["addons"]
        self.ma_info: dict[str, Any] | None = None
        self.entries: list[dict[str, Any]] = []
        self.flows: list[dict[str, Any]] = []
        self.jobs: dict[str, dict[str, Any]] = {}
        self.server_info: dict[str, Any] | None = None
        self.start_countdown = 0
        if scenario in ("installed_stopped",):
            self._mark_installed("stopped")
        if scenario in ("running_no_integration", "discovered", "ready", "integration_error", "not_onboarded"):
            self._mark_installed("started")
        if scenario == "beta_running":
            self.installed = sup("addons_with_ma_beta.json")["addons"]
            info = sup("app_info_ma_started.json")
            info.update(slug="d5369777_music_assistant_beta", name="Music Assistant (BETA)", version="2.11.0b4", hostname="d5369777-music-assistant-beta")
            if ma_host:
                info["ip_address"] = ma_host
            self.ma_info = info
            self.entries = core_fix("ma_entries_loaded.json")
        if scenario == "discovered":
            self.flows = core_fix("flow_progress_ma_discovered.json")
        if scenario == "ready":
            self.entries = core_fix("ma_entries_loaded.json")
        if scenario == "integration_error":
            self.entries = core_fix("ma_entries_setup_retry.json")
        if scenario == "not_onboarded":
            self.entries = core_fix("ma_entries_loaded.json")
            self.server_info = json.loads((FIX / "music_assistant" / "server_info_not_onboarded.json").read_text())
        if self.ma_info and self.ma_info["state"] == "started" and self.server_info is None:
            self.server_info = json.loads((FIX / "music_assistant" / "server_info.json").read_text())
            self.server_info["server_version"] = self.ma_info["version"]

    # ---- state helpers --------------------------------------------------
    def _mark_installed(self, state: str) -> None:
        self.installed = [a for a in self.installed if a["slug"] != MA_SLUG]
        entry = copy.deepcopy(next(a for a in sup("addons_with_ma.json")["addons"] if a["slug"] == MA_SLUG))
        entry["state"] = state
        self.installed.append(entry)
        self.ma_info = sup("app_info_ma_started.json")
        self.ma_info["state"] = state
        if self.ma_host:
            self.ma_info["ip_address"] = self.ma_host
        for app in self.store:
            if app["slug"] == MA_SLUG:
                app["installed"], app["version"] = True, app["version_latest"]

    def _set_state(self, state: str) -> None:
        if self.ma_info:
            self.ma_info["state"] = state
        for a in self.installed:
            if a["slug"] == (self.ma_info or {}).get("slug"):
                a["state"] = state

    def announce(self) -> None:
        """Music Assistant sends its hassio discovery once it is running."""
        if not self.entries and not self.flows:
            self.flows = core_fix("flow_progress_ma_discovered.json")
        self.server_info = json.loads((FIX / "music_assistant" / "server_info.json").read_text())

    def confirm_integration(self) -> None:
        self.flows = []
        self.entries = core_fix("ma_entries_loaded.json")

    # ---- middleware -----------------------------------------------------
    @web.middleware
    async def security(self, request: web.Request, handler):
        path = request.path
        if path.startswith("/_mock/"):
            return await handler(request)
        self.calls.append((request.method, path))
        auth = request.headers.get("Authorization", "")
        if NO_SECURITY_CHECK.match(path):
            if path.startswith("/core/api") and auth != f"Bearer {TOKEN}":
                return web.Response(status=401, text="401: Unauthorized")
            return await handler(request)
        if auth != f"Bearer {TOKEN}":
            raise web.HTTPForbidden()
        if API_BYPASS.match(path) or ROLE_ACCESS[self.role].match(path):
            return await handler(request)
        raise web.HTTPForbidden()

    # ---- supervisor handlers -------------------------------------------
    async def info(self, request):
        return ok(sup("info.json"))

    async def core_info(self, request):
        return ok(sup("core_info.json"))

    async def host_info(self, request):
        return ok(sup("host_info.json"))

    async def resolution_info(self, request):
        return ok(sup("resolution_info.json"))

    async def self_info(self, request):
        data = sup("self_info_manager.json")
        data["hassio_role"] = self.role
        return ok(data)

    async def addons(self, request):
        return ok({"addons": self.installed})

    async def addon_info(self, request):
        slug = request.match_info["slug"]
        if self.ma_info and slug == self.ma_info["slug"]:
            self._tick_start()
            return ok(dict(self.ma_info, ingress_port=self.ma_port))
        if slug == MA_SLUG and any(a["slug"] == MA_SLUG for a in self.store):
            return ok(sup("app_info_ma_not_installed.json"))
        for a in self.installed:
            if a["slug"] == slug:
                return ok(dict(a))
        return err(f"App {slug} does not exist", 404)

    async def store_addons(self, request):
        return ok({"addons": self.store})

    async def store_repositories(self, request):
        return ok(self.repos)

    async def add_repository(self, request):
        body = await request.json()
        url = body.get("repository")
        if any(r["source"] == url for r in self.repos):
            return err(f"Can't add {url}, already in the store", 409)
        if url != MA_REPO:
            return err(f"{url} is not a valid app repository", 400)
        self.repos = sup("store_repositories.json")
        self.store = sup("store_addons.json")["addons"]
        return ok()

    async def store_reload(self, request):
        return ok()

    async def availability(self, request):
        slug = request.match_info["slug"]
        app = next((a for a in self.store if a["slug"] == slug), None)
        if app is None:
            return err(f"App {slug} does not exist in the store", 404)
        if not app["available"]:
            return web.json_response(json.loads((FIX / "supervisor" / "error_unavailable_arch.json").read_text()), status=400)
        return ok()

    async def install(self, request):
        slug = request.match_info["slug"]
        if slug != MA_SLUG or not any(a["slug"] == slug for a in self.store):
            return err(f"App {slug} does not exist in the store", 404)
        if any(a["slug"] == slug for a in self.installed):
            return err(f"App {slug} is already installed", 400)
        job = sup("job_install_running.json")
        job["progress"], job["done"] = 0, False
        job["_ticks"] = self.job_ticks
        self.jobs[job["uuid"]] = job
        return ok({"job_id": job["uuid"]})

    async def job(self, request):
        job = self.jobs.get(request.match_info["uuid"])
        if job is None:
            return err("Job does not exist", 404)
        if not job["done"]:
            job["_ticks"] -= 1
            job["progress"] = round(100 * (1 - max(job["_ticks"], 0) / max(self.job_ticks, 1)), 1)
            if job["_ticks"] <= 0:
                job["done"] = True
                if self.scenario == "install_fails":
                    job["errors"] = sup("job_install_failed.json")["errors"]
                else:
                    self._mark_installed("stopped")
        return ok({k: v for k, v in job.items() if not k.startswith("_")})

    async def start(self, request):
        slug = request.match_info["slug"]
        if not self.ma_info or slug != self.ma_info["slug"]:
            return err("App is not installed", 400)
        self._set_state("startup")
        self.start_countdown = self.start_ticks
        return ok()

    def _tick_start(self) -> None:
        if self.ma_info and self.ma_info["state"] == "startup":
            self.start_countdown -= 1
            if self.start_countdown <= 0:
                self._set_state("started")
                self.announce()

    # ---- Music Assistant server (/info) ---------------------------------
    async def ma_server_info(self, request):
        if not self.server_info or not self.ma_info or self.ma_info["state"] != "started":
            return web.Response(status=503)
        return web.json_response(self.server_info)

    # ---- mock controls ----------------------------------------------------
    async def mock_state(self, request):
        return web.json_response({"scenario": self.scenario, "calls": self.calls, "entries": self.entries, "flows": self.flows})

    async def mock_confirm(self, request):
        self.confirm_integration()
        return web.json_response({"ok": True})

    # ---- Core proxy / fake core ----------------------------------------
    async def core_api(self, request):
        tail = request.match_info["tail"]
        if self.core_url:
            async with aiohttp.ClientSession() as s:
                body = await request.json() if request.method == "POST" else None
                async with s.request(
                    request.method, f"{self.core_url}/api/{tail}", params=request.query, json=body, headers={"Authorization": f"Bearer {self.core_token}"}
                ) as r:
                    return web.Response(body=await r.read(), status=r.status, content_type="application/json")
        if tail == "config":
            return web.json_response(core_fix("api_config.json"))
        if tail == "states":
            return web.json_response(core_fix("api_states.json") + list(self.activity_states.values()))
        if tail.startswith("calendars/"):
            return web.json_response(self.calendar_events.get(tail.removeprefix("calendars/"), []))
        if tail.startswith("states/sensor.home_starter_activity_") and request.method == "POST":
            entity_id = tail.removeprefix("states/")
            self.activity_states[entity_id] = {"entity_id": entity_id, **await request.json()}
            return web.json_response(self.activity_states[entity_id], status=201)
        return web.Response(status=404)

    def _fake_ws_result(self, msg: dict[str, Any]) -> Any:
        t = msg.get("type")
        self.ws_calls.append(copy.deepcopy(msg))
        if t == "lovelace/dashboards/list":
            return self.dashboards
        if t == "lovelace/dashboards/create":
            self.dashboards.append({"id": msg["url_path"], **{k: v for k, v in msg.items() if k not in ("id", "type")}})
            return self.dashboards[-1]
        if t == "lovelace/config/save":
            self.dashboard_configs[msg["url_path"]] = msg["config"]
            return None
        if t == "lovelace/config":
            return self.dashboard_configs[msg["url_path"]]
        if t == "config/device_registry/list":
            return self.devices
        if t == "config/device_registry/update":
            device = next(d for d in self.devices if d["id"] == msg["device_id"])
            device["area_id"] = msg["area_id"]
            return device
        if t == "config/floor_registry/list":
            return core_fix("floor_registry_list.json")
        if t == "config/auth/list":
            return self.users
        if t == "config_entries/get":
            entries = core_fix("config_entries_get.json") + self.entries
            if msg.get("domain"):
                entries = [e for e in entries if e["domain"] == msg["domain"]]
            return entries
        if t == "config_entries/flow/progress":
            return core_fix("flow_progress.json") + self.flows
        if t == "config/area_registry/list":
            return core_fix("area_registry_list.json")
        if t == "config/entity_registry/list":
            return self.entity_registry
        if t == "repairs/list_issues":
            return core_fix("repairs_list_issues.json")
        raise KeyError(t)

    async def core_ws(self, request):
        server = web.WebSocketResponse()
        await server.prepare(request)
        await server.send_json({"type": "auth_required", "ha_version": "2026.10.1"})
        auth = await server.receive_json()
        if auth.get("access_token") != TOKEN:
            await server.send_json({"type": "auth_invalid", "message": "Invalid access"})
            await server.close()
            return server
        await server.send_json({"type": "auth_ok", "ha_version": "2026.10.1"})
        upstream = None
        session = None
        if self.core_url:
            session = aiohttp.ClientSession()
            upstream = await session.ws_connect(self.core_url.replace("http", "ws", 1) + "/api/websocket")
            await upstream.receive_json()
            await upstream.send_json({"type": "auth", "access_token": self.core_token})
            await upstream.receive_json()
        try:
            async for raw in server:
                if raw.type != aiohttp.WSMsgType.TEXT:
                    break
                msg = json.loads(raw.data)
                msg_type = str(msg.get("type", ""))
                if msg_type.startswith(("supervisor/", "hassio/")):
                    await server.send_json(
                        {"id": msg.get("id"), "type": "result", "success": False, "error": {"code": "unauthorized", "message": "Unauthorized"}}
                    )
                    continue
                if upstream is None:
                    try:
                        reply = {"id": msg.get("id"), "type": "result", "success": True, "result": self._fake_ws_result(msg)}
                    except KeyError:
                        reply = {"id": msg.get("id"), "type": "result", "success": False, "error": {"code": "unknown_command", "message": "Unknown command."}}
                    await server.send_json(reply)
                    continue
                # Real Core behind us: forward, then overlay the simulated
                # Music Assistant integration state (it can't exist upstream).
                await upstream.send_str(raw.data)
                while True:
                    reply = await upstream.receive_json()
                    if reply.get("id") == msg.get("id") and reply.get("type") == "result":
                        break
                if reply.get("success") and msg_type == "config_entries/get":
                    reply["result"] = list(reply["result"]) + [e for e in self.entries if not msg.get("domain") or e["domain"] == msg["domain"]]
                if reply.get("success") and msg_type == "config_entries/flow/progress":
                    reply["result"] = list(reply["result"]) + self.flows
                await server.send_json(reply)
        finally:
            if upstream is not None:
                await upstream.close()
            if session is not None:
                await session.close()
        return server

    def ma_app(self) -> web.Application:
        """Stand-in for the Music Assistant server's own port (GET /info)."""
        app = web.Application()
        app.router.add_get("/info", self.ma_server_info)
        return app

    def app(self) -> web.Application:
        app = web.Application(middlewares=[self.security])
        r = app.router
        r.add_get("/info", self.info)
        r.add_get("/core/info", self.core_info)
        r.add_get("/host/info", self.host_info)
        r.add_get("/resolution/info", self.resolution_info)
        r.add_get("/addons/self/info", self.self_info)
        r.add_get("/addons", self.addons)
        r.add_get("/addons/{slug}/info", self.addon_info)
        r.add_post("/addons/{slug}/start", self.start)
        r.add_get("/store/addons", self.store_addons)
        r.add_get("/store/repositories", self.store_repositories)
        r.add_post("/store/repositories", self.add_repository)
        r.add_post("/store/reload", self.store_reload)
        r.add_get("/store/addons/{slug}/availability", self.availability)
        r.add_post("/store/addons/{slug}/install", self.install)
        r.add_get("/jobs/{uuid}", self.job)
        r.add_get("/core/api/{tail:.*}", self.core_api)
        r.add_post("/core/api/{tail:.*}", self.core_api)
        r.add_get("/core/websocket", self.core_ws)
        r.add_get("/_mock/state", self.mock_state)
        r.add_post("/_mock/confirm_integration", self.mock_confirm)
        return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8181)
    parser.add_argument("--scenario", default="absent", choices=SCENARIOS)
    parser.add_argument("--core-url")
    parser.add_argument("--core-token-file", help="file containing a long-lived token for --core-url")
    parser.add_argument("--ma-port", type=int, default=8195, help="port for the fake Music Assistant /info")
    parser.add_argument("--job-ticks", type=int, default=4)
    args = parser.parse_args()
    token = Path(args.core_token_file).read_text().strip() if args.core_token_file else None
    mock = MockSupervisor(args.scenario, job_ticks=args.job_ticks, core_url=args.core_url, core_token=token, ma_host="127.0.0.1")
    mock.ma_port = args.ma_port

    async def run() -> None:
        runners = []
        for app, port in ((mock.app(), args.port), (mock.ma_app(), args.ma_port)):
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
            runners.append(runner)
        print(f"mock supervisor on :{args.port}, fake Music Assistant on :{args.ma_port} (scenario {args.scenario})", flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            for runner in runners:
                await runner.cleanup()

    asyncio.run(run())


if __name__ == "__main__":
    main()
