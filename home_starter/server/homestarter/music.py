"""Outcome: Music around the house -> Music Assistant.

Three parts:

* ``gather_facts``: read-only collection of everything we know about Music
  Assistant from the Supervisor (store, repositories, installed apps, app
  info), Home Assistant Core (config entries, discovered flows) and the Music
  Assistant server itself (unauthenticated ``GET /info``).
* ``evaluate``: a pure function turning those facts into one state, a list of
  verification checks and the actions to offer. Unit tested exhaustively.
* ``MusicSetup``: the explicit, user-triggered direct installation
  (add repository if missing -> install -> start), idempotent and with a
  native Home Assistant handoff as the fallback for every failure.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from . import navigation as nav
from .core import CoreClient, CoreError
from .supervisor import SupervisorClient, SupervisorError

_LOGGER = logging.getLogger(__name__)

# The official Music Assistant app repository. Current Supervisors ship it as a
# built-in store repository (supervisor/store/const.py BuiltinRepository); on
# older ones it may have to be added.
MA_REPOSITORY_URL = "https://github.com/music-assistant/home-assistant-addon"
# Slug of the stable app *within* that repository. The installed slug is
# "<repository hash>_music_assistant"; the hash is read from store metadata.
MA_APP = "music_assistant"
MA_VARIANTS = ("music_assistant", "music_assistant_beta", "music_assistant_nightly", "music_assistant_dev")
MA_DOMAIN = "music_assistant"
MA_NAME = "Music Assistant"
# Used only as a fallback when the Supervisor refuses to list apps: the slug
# current Supervisors give the built-in Music Assistant repository's stable app
# (supervisor/store/const.py BuiltinRepository.MUSIC_ASSISTANT -> "d5369777").
MA_BUILTIN_SLUG = "d5369777_music_assistant"

_INSTALLED_SLUG = re.compile(r"^(?P<repo>[0-9a-f]{8}|local)_(?P<app>music_assistant(?:_beta|_nightly|_dev)?)$")
_PROBE_TIMEOUT = aiohttp.ClientTimeout(total=4)


def normalize_repo_url(url: str | None) -> str:
    url = (url or "").strip().split("#", 1)[0].lower().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------


@dataclass
class Facts:
    """Raw observations. ``*_error`` holds a SupervisorError/CoreError dict."""

    ha_version: str | None = None
    self_role: str | None = None
    self_error: dict[str, Any] | None = None
    repositories: list[dict[str, Any]] | None = None
    repositories_error: dict[str, Any] | None = None
    store_apps: list[dict[str, Any]] | None = None
    store_error: dict[str, Any] | None = None
    installed_apps: list[dict[str, Any]] | None = None
    installed_error: dict[str, Any] | None = None
    app_info: dict[str, Any] | None = None
    app_info_error: dict[str, Any] | None = None
    availability_error: dict[str, Any] | None = None
    config_entries: list[dict[str, Any]] | None = None
    flows: list[dict[str, Any]] | None = None
    core_error: dict[str, Any] | None = None
    server: dict[str, Any] | None = None
    server_error: str | None = None
    ingress_responding: bool = False


def _err(err: Exception) -> dict[str, Any]:
    if isinstance(err, SupervisorError):
        return err.as_dict()
    if isinstance(err, CoreError):
        return {"kind": err.kind, "message": err.message, "status": None}
    return {"kind": "error", "message": type(err).__name__, "status": None}


def ma_repository_slug(repositories: list[dict[str, Any]] | None) -> str | None:
    target = normalize_repo_url(MA_REPOSITORY_URL)
    for repo in repositories or []:
        if target in (normalize_repo_url(repo.get("source")), normalize_repo_url(repo.get("url"))):
            return repo.get("slug")
    return None


def find_store_app(store_apps: list[dict[str, Any]] | None, repo_slug: str | None) -> dict[str, Any] | None:
    """The stable Music Assistant app in store metadata."""
    apps = store_apps or []
    if repo_slug:
        for app in apps:
            if app.get("slug") == f"{repo_slug}_{MA_APP}" and app.get("repository") == repo_slug:
                return app
        return None
    # Repository list unavailable: accept the app only when its own metadata
    # clearly identifies it (exact app name and the expected slug shape).
    for app in apps:
        m = _INSTALLED_SLUG.match(app.get("slug") or "")
        if m and m.group("app") == MA_APP and app.get("name") == MA_NAME:
            return app
    return None


def find_installed(installed: list[dict[str, Any]] | None, repo_slug: str | None) -> dict[str, Any] | None:
    """An installed Music Assistant app (stable preferred, running preferred)."""
    candidates = []
    for app in installed or []:
        m = _INSTALLED_SLUG.match(app.get("slug") or "")
        if not m:
            continue
        from_official = bool(repo_slug) and app.get("repository") == repo_slug
        candidates.append(
            (
                app.get("state") != "started",
                m.group("app") != MA_APP,
                not from_official,
                MA_VARIANTS.index(m.group("app")),
                app,
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[:4])
    return candidates[0][4]


async def probe_server(session: aiohttp.ClientSession, host: str, port: int) -> dict[str, Any]:
    """GET http://host:port/info - Music Assistant's unauthenticated info."""
    async with session.get(f"http://{host}:{port}/info", timeout=_PROBE_TIMEOUT, allow_redirects=False) as resp:
        if resp.status != 200:
            raise ValueError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    if not isinstance(data, dict) or not isinstance(data.get("server_version"), str) or not data["server_version"]:
        raise ValueError("unexpected response")
    return {
        "server_version": data.get("server_version"),
        "schema_version": data.get("schema_version"),
        "onboard_done": data.get("onboard_done"),
        "homeassistant_addon": data.get("homeassistant_addon"),
        "status": data.get("status"),
    }


async def gather_facts(
    supervisor: SupervisorClient,
    core: CoreClient,
    session: aiohttp.ClientSession,
    *,
    ha_version: str | None,
    ma_port: int,
) -> Facts:
    facts = Facts(ha_version=ha_version)

    async def grab(coro, ok_attr: str, err_attr: str) -> None:
        try:
            setattr(facts, ok_attr, await coro)
        except (SupervisorError, CoreError) as err:
            setattr(facts, err_attr, _err(err))

    async def self_role() -> str | None:
        return (await supervisor.self_info()).get("hassio_role")

    async def core_facts() -> None:
        try:
            async with core.websocket() as ws:
                facts.config_entries = await ws.command("config_entries/get", domain=MA_DOMAIN)
                flows = await ws.command("config_entries/flow/progress")
                facts.flows = [f for f in flows or [] if f.get("handler") == MA_DOMAIN]
        except CoreError as err:
            facts.core_error = _err(err)

    await asyncio.gather(
        grab(self_role(), "self_role", "self_error"),
        grab(supervisor.store_repositories(), "repositories", "repositories_error"),
        grab(supervisor.store_apps(), "store_apps", "store_error"),
        grab(supervisor.installed_apps(), "installed_apps", "installed_error"),
        core_facts(),
    )

    if facts.installed_error and facts.installed_error.get("kind") == "forbidden":
        await _fallback_known_slug(supervisor, facts)

    repo_slug = ma_repository_slug(facts.repositories)
    installed = find_installed(facts.installed_apps, repo_slug)
    if installed:
        await grab(supervisor.app_info(installed["slug"]), "app_info", "app_info_error")
        info = facts.app_info or {}
        if info.get("state") == "started":
            host = info.get("ip_address") or info.get("hostname")
            if host:
                try:
                    # MA's internal ingress listener is independent of its user-
                    # configurable public port/TLS settings. /info is read-only
                    # and unauthenticated on both listeners in MA 2.10.6.
                    port = info.get("ingress_port") if info.get("ingress") else ma_port
                    facts.server = await probe_server(session, host, int(port or ma_port))
                    facts.ingress_responding = bool(info.get("ingress") and info.get("ingress_port"))
                except (TimeoutError, aiohttp.ClientError, OSError, ValueError) as err:
                    facts.server_error = type(err).__name__
    else:
        store_app = find_store_app(facts.store_apps, repo_slug)
        if store_app:
            try:
                await supervisor.store_app_availability(store_app["slug"])
            except SupervisorError as err:
                facts.availability_error = err.as_dict()
    return facts


async def _fallback_known_slug(supervisor: SupervisorClient, facts: Facts) -> None:
    """Without permission to list apps, ``/addons/<slug>/info`` is still allowed
    (every role may call ``/.+/info``). For a not-installed app the Supervisor
    answers with its store info and ``version: null``."""
    try:
        info = await supervisor.app_info(MA_BUILTIN_SLUG)
    except SupervisorError:
        return
    entry = {k: info.get(k) for k in ("name", "slug", "repository", "version", "version_latest", "state", "available", "update_available")}
    if info.get("version"):
        facts.installed_apps = [entry]
        facts.installed_error = None
    elif facts.store_apps is None and info.get("slug") == MA_BUILTIN_SLUG:
        facts.store_apps = [dict(entry, installed=False)]
        facts.installed_apps = []
        facts.installed_error = None


# ---------------------------------------------------------------------------
# Evaluation (pure)
# ---------------------------------------------------------------------------

DIRECT_ROLES = {"manager", "admin"}


def _action(kind: str, label: str, *, style: str = "secondary", path: str | None = None, hint: str | None = None) -> dict[str, Any]:
    action: dict[str, Any] = {"kind": kind, "label": label, "style": style}
    if path is not None:
        if not nav.is_safe_ha_path(path):
            raise ValueError(f"unsafe navigation path {path!r}")
        action["path"] = path
    if hint:
        action["hint"] = hint
    return action


def _check(check_id: str, label: str, status: str, detail: str = "") -> dict[str, str]:
    return {"id": check_id, "label": label, "status": status, "detail": detail}


def _pick_entry(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    real = [e for e in entries if e.get("source") != "ignore"]
    if not real:
        return None
    order = {"loaded": 0, "setup_in_progress": 1, "setup_retry": 2, "not_loaded": 3}
    real.sort(key=lambda e: (bool(e.get("disabled_by")), order.get(e.get("state"), 9)))
    return real[0]


def evaluate(facts: Facts, operation: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {state, title, detail, app, checks, actions, direct_install}."""
    repo_slug = ma_repository_slug(facts.repositories)
    store_app = find_store_app(facts.store_apps, repo_slug)
    installed = find_installed(facts.installed_apps, repo_slug)
    info = facts.app_info if installed else None

    can_direct = facts.self_role in DIRECT_ROLES
    direct_reason = None
    if not can_direct:
        if facts.self_error:
            direct_reason = "Home Starter could not read its own permissions from the Supervisor."
        else:
            direct_reason = f"Home Starter runs with the '{facts.self_role}' Supervisor role, which cannot install apps."
    for err in (facts.store_error, facts.repositories_error, facts.installed_error):
        if can_direct and err and err.get("kind") == "forbidden":
            can_direct = False
            direct_reason = "The Supervisor refused access to the App Store for Home Starter."

    # Native handoff targets, derived from what we know right now.
    if store_app or installed:
        slug = (installed or store_app)["slug"]
        store_path = nav.app_info_path(slug, MA_REPOSITORY_URL if not repo_slug else None)
    elif repo_slug:
        store_path = nav.app_info_path(f"{repo_slug}_{MA_APP}")
    else:
        store_path = nav.add_repository_path(MA_REPOSITORY_URL)

    checks: list[dict[str, str]] = []
    actions: list[dict[str, Any]] = []
    app_summary: dict[str, Any] | None = None
    open_path: str | None = None

    # -- App Store metadata ------------------------------------------------
    repo_names = {r.get("slug"): r.get("name") for r in facts.repositories or []}

    def source(app: dict[str, Any]) -> str:
        return f"From the {repo_names.get(app.get('repository')) or app.get('repository') or 'unknown'} repository"

    if installed:
        checks.append(_check("store", "Found in the App Store", "pass", source(installed)))
    elif store_app:
        latest = store_app.get("version_latest")
        checks.append(_check("store", "Found in the App Store", "pass", source(store_app) + (f" · version {latest}" if latest else "")))
    elif facts.store_error or facts.repositories_error:
        checks.append(_check("store", "Found in the App Store", "unknown", (facts.store_error or facts.repositories_error or {}).get("message", "")))
    else:
        checks.append(_check("store", "Found in the App Store", "fail", "The Music Assistant repository is not in this App Store."))

    supervisor_down = all(e and e.get("kind") == "unreachable" for e in (facts.store_error, facts.installed_error, facts.repositories_error))

    # -- Operation in progress overrides everything else ------------------
    if operation and not operation.get("finished"):
        checks.append(_check("installed", "Installed", "pending"))
        return _result(
            "installing",
            "Setting up Music Assistant…",
            "Home Starter is installing and starting Music Assistant. This carries on even if you leave this page.",
            app_summary,
            checks,
            [],
            can_direct,
            direct_reason,
            store_path,
            operation,
        )

    if supervisor_down:
        checks.append(_check("installed", "Installed", "unknown", "Supervisor not reachable"))
        actions.append(_action("recheck", "Check again", style="primary"))
        actions.append(_action("navigate", "Open the App Store", path=nav.app_store_path()))
        return _result(
            "unknown",
            "Can't reach the Supervisor",
            "Home Starter couldn't read app information from the Home Assistant Supervisor. This needs Home Assistant OS or a Supervised installation.",
            None,
            checks,
            actions,
            False,
            direct_reason,
            store_path,
            operation,
        )

    if not installed:
        checks.append(
            _check(
                "installed",
                "Installed",
                "unknown" if facts.installed_error else "fail",
                "Couldn't read installed apps." if facts.installed_error else "Not installed",
            )
        )
        if facts.installed_error:
            actions.append(_action("navigate", "Open Music Assistant in the App Store", style="primary", path=store_path))
            actions.append(_action("recheck", "Check again"))
            return _result(
                "unknown",
                "Couldn't check for Music Assistant",
                facts.installed_error.get("message", ""),
                None,
                checks,
                actions,
                can_direct,
                direct_reason,
                store_path,
                operation,
            )
        if not store_app and (facts.store_error or facts.repositories_error):
            err = facts.store_error or facts.repositories_error or {}
            actions.append(_action("navigate", "Open Music Assistant in the App Store", style="primary", path=store_path))
            actions.append(_action("recheck", "Check again"))
            return _result(
                "unknown",
                "Couldn't read the App Store",
                err.get("message", ""),
                None,
                checks,
                actions,
                False,
                direct_reason or "The App Store couldn't be read.",
                store_path,
                operation,
            )
        if facts.availability_error and not (facts.availability_error.get("kind") == "api" and facts.availability_error.get("status") == 400):
            checks.append(_check("compatible", "Compatible with this system", "unknown", "Couldn't check system compatibility."))
            actions += [_action("navigate", "Continue in the App Store", style="primary", path=store_path), _action("recheck", "Check again")]
            return _result(
                "unknown",
                "Couldn't check Music Assistant compatibility",
                "Continue in Home Assistant, then check again.",
                None,
                checks,
                actions,
                False,
                "Compatibility couldn't be checked.",
                store_path,
                operation,
            )
        if store_app and (facts.availability_error or store_app.get("available") is False):
            reason = (facts.availability_error or {}).get("message") or "Not available for this system."
            checks.append(_check("compatible", "Compatible with this system", "fail", reason))
            actions.append(_action("navigate", "View in the App Store", style="primary", path=store_path))
            actions.append(_action("recheck", "Check again"))
            return _result(
                "unsupported",
                "Music Assistant can't be installed here",
                reason,
                {"slug": store_app["slug"], "name": store_app.get("name"), "version_latest": store_app.get("version_latest")},
                checks,
                actions,
                False,
                direct_reason,
                store_path,
                operation,
            )
        if store_app:
            checks.append(_check("compatible", "Compatible with this system", "pass"))
            app_summary = {"slug": store_app["slug"], "name": store_app.get("name"), "version_latest": store_app.get("version_latest")}
            state, title = "available", "Music Assistant is ready to install"
            detail = "It's in your App Store but not installed yet."
        else:
            state, title = "not_in_store", "Music Assistant isn't in your App Store yet"
            detail = "Home Starter can add the official Music Assistant repository and install it."
        if can_direct:
            actions.append(
                _action("setup", "Install Music Assistant", style="primary", hint="Adds the official repository if needed, installs and starts the app.")
            )
            actions.append(_action("navigate", "Do it in the App Store instead", path=store_path))
        else:
            actions.append(_action("navigate", "Install from the App Store", style="primary", path=store_path))
        actions.append(_action("recheck", "Check again"))
        return _result(state, title, detail, app_summary, checks, actions, can_direct, direct_reason, store_path, operation)

    # -- Installed ----------------------------------------------------------
    slug = installed["slug"]
    variant = _INSTALLED_SLUG.match(slug).group("app")  # type: ignore[union-attr]
    info = info or {}
    app_state = info.get("state") or installed.get("state")
    app_summary = {
        "slug": slug,
        "name": info.get("name") or installed.get("name"),
        "version": info.get("version") or installed.get("version"),
        "version_latest": info.get("version_latest") or installed.get("version_latest"),
        "state": app_state,
        "variant": variant,
        "update_available": bool(info.get("update_available") or installed.get("update_available")),
    }
    checks.append(_check("installed", "Installed", "pass", f"{app_summary['name']} {app_summary['version'] or ''}".strip()))
    app_page = nav.app_info_path(slug)

    if app_state != "started":
        if app_state == "startup":
            checks.append(_check("running", "Running", "pending", "Starting up"))
            actions.append(_action("recheck", "Check again", style="primary"))
            actions.append(_action("navigate", "View app in Home Assistant", path=app_page))
            return _result(
                "starting",
                "Music Assistant is starting",
                "This usually takes under a minute.",
                app_summary,
                checks,
                actions,
                can_direct,
                direct_reason,
                app_page,
                operation,
            )
        checks.append(_check("running", "Running", "fail", f"Supervisor state: {app_state or 'unknown'}"))
        if can_direct:
            actions.append(_action("setup", "Start Music Assistant", style="primary"))
            actions.append(_action("navigate", "Open the app page instead", path=app_page))
        else:
            actions.append(_action("navigate", "Start it from the app page", style="primary", path=app_page))
        actions.append(_action("recheck", "Check again"))
        detail = "It's installed but not running."
        if app_state == "error":
            detail = "It's installed but stopped with an error. Its log on the app page usually says why."
        return _result("stopped", "Music Assistant is stopped", detail, app_summary, checks, actions, can_direct, direct_reason, app_page, operation)

    checks.append(_check("running", "Running", "pass", "Supervisor state: started"))

    # Web UI (ingress) metadata.
    if info.get("ingress") and info.get("ingress_url"):
        checks.append(
            _check(
                "web_ui",
                "Web interface available",
                "pass" if facts.ingress_responding else "unknown",
                "Ingress listener responding" if facts.ingress_responding else "Ingress is configured; its listener hasn't responded.",
            )
        )
        open_path = nav.app_ui_path(slug, facts.ha_version)
    elif facts.app_info_error:
        checks.append(_check("web_ui", "Web interface available", "unknown", facts.app_info_error.get("message", "")))
        open_path = nav.app_ui_path(slug, facts.ha_version)
    else:
        checks.append(_check("web_ui", "Web interface available", "fail", "The app reports no ingress web UI."))
        open_path = app_page

    # Music Assistant server itself.
    if facts.server:
        onboard = facts.server.get("onboard_done")
        checks.append(_check("server", "Music Assistant server responding", "pass", f"Version {facts.server.get('server_version')}"))
    else:
        onboard = None
        checks.append(
            _check(
                "server",
                "Music Assistant server responding",
                "unknown",
                "The server hasn't responded yet. Open Music Assistant, then check again.",
            )
        )

    # Home Assistant integration.
    open_action = _action("navigate", "Open Music Assistant", style="primary", path=open_path)
    if facts.core_error or facts.config_entries is None:
        checks.append(_check("integration", "Connected to Home Assistant", "unknown", (facts.core_error or {}).get("message", "Couldn't read integrations.")))
        actions += [open_action, _action("recheck", "Check again")]
        return _result(
            "running_unverified",
            "Music Assistant is running",
            "Home Starter couldn't confirm the Home Assistant integration, so setup can't be verified yet.",
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )

    entry = _pick_entry(facts.config_entries)
    ignored = any(e.get("source") == "ignore" for e in facts.config_entries)
    integration_page = nav.integration_path(MA_DOMAIN)

    if entry is None:
        if facts.flows:
            checks.append(_check("integration", "Connected to Home Assistant", "fail", "Discovered by Home Assistant, waiting for you to confirm."))
            actions.append(
                _action(
                    "navigate",
                    "Confirm the integration",
                    style="primary",
                    path=nav.integrations_dashboard_path(),
                    hint="Under Discovered, choose Music Assistant → Add.",
                )
            )
            state, title = "integration_discovered", "One step left: connect it to Home Assistant"
            detail = "Home Assistant has discovered Music Assistant. Confirm it so your speakers and players show up."
        elif ignored:
            checks.append(_check("integration", "Connected to Home Assistant", "fail", "The discovered integration was ignored."))
            actions.append(
                _action(
                    "navigate",
                    "Show ignored integrations",
                    style="primary",
                    path=nav.integrations_dashboard_path(),
                    hint="Use the filter menu to show ignored integrations, then stop ignoring Music Assistant.",
                )
            )
            state, title = "integration_ignored", "The Music Assistant integration is ignored"
            detail = "Home Assistant was told to ignore Music Assistant. Un-ignore it to finish setup."
        else:
            checks.append(_check("integration", "Connected to Home Assistant", "fail", "No Music Assistant integration yet."))
            actions.append(_action("navigate", "Add the integration", style="primary", path=nav.config_flow_start_path(MA_DOMAIN)))
            state, title = "needs_integration", "One step left: connect it to Home Assistant"
            detail = "Music Assistant usually announces itself to Home Assistant a minute after it starts. If nothing shows up, add the integration yourself."
        actions += [_action("navigate", "Open Music Assistant", path=open_path), _action("recheck", "Check again")]
        return _result(state, title, detail, app_summary, checks, actions, can_direct, direct_reason, app_page, operation, open_path)

    entry_state = entry.get("state")
    if entry.get("disabled_by"):
        checks.append(_check("integration", "Connected to Home Assistant", "fail", "The integration is disabled."))
        actions += [_action("navigate", "Enable the integration", style="primary", path=integration_page), _action("recheck", "Check again")]
        return _result(
            "integration_disabled",
            "The Music Assistant integration is disabled",
            "Enable it in Home Assistant to use your players.",
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )
    if entry_state == "setup_in_progress":
        checks.append(_check("integration", "Connected to Home Assistant", "pending", "Setting up"))
        actions += [_action("recheck", "Check again", style="primary"), _action("navigate", "Open Music Assistant", path=open_path)]
        return _result(
            "integration_starting",
            "Connecting to Home Assistant…",
            "The integration is setting up.",
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )
    if entry_state != "loaded":
        reason = entry.get("reason") or entry_state
        checks.append(_check("integration", "Connected to Home Assistant", "fail", f"{entry_state}: {reason}"))
        actions += [
            _action("navigate", "Review the integration", style="primary", path=integration_page),
            _action("navigate", "Open Music Assistant", path=open_path),
            _action("recheck", "Check again"),
        ]
        return _result(
            "integration_error",
            "The Music Assistant integration isn't working",
            f"Home Assistant reports '{entry_state}'" + (f": {entry.get('reason')}" if entry.get("reason") else "."),
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )

    checks.append(_check("integration", "Connected to Home Assistant", "pass", entry.get("title") or "Loaded"))

    if onboard is False:
        actions += [_action("navigate", "Finish setup in Music Assistant", style="primary", path=open_path), _action("recheck", "Check again")]
        return _result(
            "needs_onboarding",
            "Finish setting up Music Assistant",
            "Music Assistant is running and connected, but its own first-run setup isn't finished.",
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )

    real_entries = [e for e in facts.config_entries if e.get("source") != "ignore"]
    # Public config-entry summaries omit server IDs/URLs. A loaded entry may
    # belong to another MA server, so don't claim instance-level verification.
    ma_apps = [a for a in facts.installed_apps or [] if _INSTALLED_SLUG.match(a.get("slug") or "")]
    unambiguous = len(real_entries) == 1 and len(ma_apps) == 1 and entry.get("source") == "hassio"
    matching_version = bool(facts.server) and facts.server.get("server_version") == app_summary["version"]
    if not (
        facts.ingress_responding
        and info.get("ingress_url")
        and onboard is True
        and matching_version
        and facts.server.get("homeassistant_addon") is True
        and facts.server.get("status") == "running"
        and unambiguous
    ):
        actions += [open_action, _action("recheck", "Check again")]
        return _result(
            "running_unverified",
            "Music Assistant is running",
            "Setup isn't fully verified. Open Music Assistant to finish or review setup, then check again. "
            "Home Starter needs a responding ingress listener, completed first-run setup and one healthy app-discovered integration.",
            app_summary,
            checks,
            actions,
            can_direct,
            direct_reason,
            app_page,
            operation,
            open_path,
        )

    actions += [open_action, _action("recheck", "Check again")]
    detail = "Installed, running and connected to Home Assistant."
    if onboard is True:
        detail = "Installed, running, set up and connected to Home Assistant."
    return _result("ready", "Music Assistant is ready", detail, app_summary, checks, actions, can_direct, direct_reason, app_page, operation, open_path)


def _result(state, title, detail, app, checks, actions, can_direct, direct_reason, handoff_path, operation, open_path=None):
    return {
        "state": state,
        "title": title,
        "detail": detail,
        "app": app,
        "checks": checks,
        "actions": actions,
        "direct_install": {"available": bool(can_direct), "reason": None if can_direct else direct_reason},
        "handoff_path": handoff_path,
        "open_path": open_path,
        "operation": operation,
        "verified": state == "ready",
    }


# ---------------------------------------------------------------------------
# Direct setup (explicit user action only)
# ---------------------------------------------------------------------------


@dataclass
class Operation:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.time)
    step: str = "checking"
    message: str = "Checking what's already there…"
    progress: float | None = None
    finished: bool = False
    success: bool = False
    error: dict[str, Any] | None = None
    fallback_path: str | None = None
    log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "step": self.step,
            "message": self.message,
            "progress": self.progress,
            "finished": self.finished,
            "success": self.success,
            "error": self.error,
            "fallback_path": self.fallback_path,
            "log": list(self.log[-20:]),
            "started_at": int(self.started_at),
        }


class SetupFailed(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class MusicSetup:
    """Runs at most one setup at a time; repeated requests join the current one."""

    def __init__(
        self,
        supervisor: SupervisorClient,
        *,
        poll_interval: float = 2.0,
        install_timeout: float = 30 * 60,
        start_timeout: float = 180,
    ) -> None:
        self._sup = supervisor
        self._poll = poll_interval
        self._install_timeout = install_timeout
        self._start_timeout = start_timeout
        self._lock = asyncio.Lock()
        self.current: Operation | None = None
        self._task: asyncio.Task | None = None

    def snapshot(self) -> dict[str, Any] | None:
        return self.current.to_dict() if self.current else None

    def start(self, user: str | None) -> Operation:
        if self.current and not self.current.finished:
            return self.current
        op = Operation()
        self.current = op
        _LOGGER.info("Music Assistant setup requested (operation %s)", op.id)
        self._task = asyncio.get_running_loop().create_task(self._run(op))
        return op

    async def wait(self) -> None:
        if self._task:
            await self._task

    def _step(self, op: Operation, step: str, message: str) -> None:
        op.step, op.message = step, message
        op.log.append(message)
        _LOGGER.info("[%s] %s", op.id, message)

    async def _run(self, op: Operation) -> None:
        async with self._lock:
            try:
                await self._setup(op)
                op.success = True
                self._step(op, "done", "Music Assistant is installed and running.")
            except SetupFailed as err:
                op.error = {"kind": err.kind, "message": err.message}
                self._step(op, "failed", err.message)
            except SupervisorError as err:
                kind = "permission" if err.kind == "forbidden" else err.kind
                op.error = {"kind": kind, "message": err.message}
                self._step(op, "failed", f"The Supervisor refused or failed the request: {err.message}")
            except Exception as err:  # noqa: BLE001 - never leave an operation hanging
                _LOGGER.error("Unexpected setup failure (%s)", type(err).__name__)
                op.error = {"kind": "error", "message": f"Unexpected error ({type(err).__name__})."}
                self._step(op, "failed", op.error["message"])
            finally:
                op.finished = True
                if not op.success and op.fallback_path is None:
                    op.fallback_path = nav.add_repository_path(MA_REPOSITORY_URL)

    async def _setup(self, op: Operation) -> None:
        sup = self._sup
        # 0. Our own permission level decides whether direct install is possible.
        role = (await sup.self_info()).get("hassio_role")
        if role not in DIRECT_ROLES:
            raise SetupFailed("permission", f"Home Starter's Supervisor role is '{role}', which can't install apps.")

        # 1. Already installed (any variant)? Then only make sure it runs.
        repositories = await sup.store_repositories()
        repo_slug = ma_repository_slug(repositories)
        installed = find_installed(await sup.installed_apps(), repo_slug)
        if installed:
            slug = installed["slug"]
            op.fallback_path = nav.app_info_path(slug)
            self._step(op, "installed", f"{installed.get('name') or slug} is already installed.")
        else:
            # 2. Repository: add only if missing (never duplicate).
            if repo_slug is None:
                op.fallback_path = nav.add_repository_path(MA_REPOSITORY_URL)
                self._step(op, "adding_repository", "Adding the official Music Assistant repository…")
                try:
                    await sup.add_repository(MA_REPOSITORY_URL)
                except SupervisorError as err:
                    # A concurrent add (e.g. from the UI) is fine; anything else is not.
                    if "already" not in err.message.lower():
                        raise
                repositories = await sup.store_repositories()
                repo_slug = ma_repository_slug(repositories)
                if repo_slug is None:
                    raise SetupFailed("not_found", "The Music Assistant repository didn't appear in the App Store.")
            else:
                self._step(op, "repository_present", "The Music Assistant repository is already in the App Store.")

            # 3. Locate the stable app from returned metadata.
            store_app = find_store_app(await sup.store_apps(), repo_slug)
            if store_app is None:
                self._step(op, "reloading_store", "Refreshing the App Store…")
                await sup.reload_store()
                store_app = find_store_app(await sup.store_apps(), repo_slug)
            if store_app is None:
                raise SetupFailed("not_found", "Music Assistant wasn't found in the App Store metadata.")
            slug = store_app["slug"]
            op.fallback_path = nav.app_info_path(slug)

            # 4. Architecture / system compatibility.
            if store_app.get("available") is False:
                raise SetupFailed("unsupported", "Music Assistant isn't available for this system.")
            try:
                await sup.store_app_availability(slug)
            except SupervisorError as err:
                if err.kind == "api" and err.status == 400:
                    raise SetupFailed("unsupported", err.message) from None
                raise

            # 5. Install (background job, polled).
            self._step(op, "installing", f"Installing Music Assistant {store_app.get('version_latest') or ''}… this can take a few minutes.".replace("  ", " "))
            try:
                job_id = await sup.install_app(slug)
            except SupervisorError as err:
                if "already installed" not in err.message.lower():
                    raise
                job_id = None
            await self._wait_installed(op, slug, job_id)

        # 6. Start if not running.
        info = await sup.app_info(slug)
        if info.get("state") != "started":
            self._step(op, "starting", "Starting Music Assistant…")
            op.progress = None
            await sup.start_app(slug)
            await self._wait_started(op, slug)

    async def _wait_installed(self, op: Operation, slug: str, job_id: str | None) -> None:
        deadline = time.monotonic() + self._install_timeout
        job_gone = job_id is None
        while time.monotonic() < deadline:
            if not job_gone:
                try:
                    job = await self._sup.job(job_id)  # type: ignore[arg-type]
                except SupervisorError as err:
                    if err.kind in ("not_found",):
                        job_gone = True
                    else:
                        raise
                else:
                    if job.get("progress") is not None:
                        op.progress = float(job.get("progress") or 0)
                    if job.get("done"):
                        errors = job.get("errors") or []
                        if errors:
                            msg = "; ".join(str(e.get("message")) for e in errors if e.get("message")) or "Install failed."
                            raise SetupFailed("install_failed", f"Install failed: {msg}")
                        job_gone = True
            if job_gone:
                try:
                    info = await self._sup.app_info(slug)
                except SupervisorError as err:
                    if err.kind != "not_found":
                        raise
                    info = {}
                if info.get("version"):
                    op.progress = 100
                    self._step(op, "installed", f"Installed Music Assistant {info.get('version')}.")
                    return
                raise SetupFailed("install_failed", "The install finished but the app isn't reported as installed.")
            await asyncio.sleep(self._poll)
        raise SetupFailed("timeout", "Installing took too long. It may still finish; check again in a few minutes.")

    async def _wait_started(self, op: Operation, slug: str) -> None:
        deadline = time.monotonic() + self._start_timeout
        while time.monotonic() < deadline:
            state = (await self._sup.app_info(slug)).get("state")
            if state == "started":
                return
            if state in ("error",):
                raise SetupFailed("start_failed", "Music Assistant failed to start. Its log on the app page says why.")
            await asyncio.sleep(self._poll)
        raise SetupFailed("timeout", "Music Assistant didn't report as started in time.")
