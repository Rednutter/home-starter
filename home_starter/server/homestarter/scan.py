"""Non-destructive Home Assistant scan.

Every source is read through a supported API (Supervisor REST, Core REST and
Core websocket). Nothing here writes anything. Each category is collected
independently: one failing source marks only that category as unavailable.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from .core import CoreClient, CoreError
from .supervisor import SupervisorClient, SupervisorError

# Config entry states (homeassistant/config_entries.py ConfigEntryState).
UNHEALTHY_ENTRY_STATES = {"setup_error", "setup_retry", "migration_error", "failed_unload"}
PENDING_ENTRY_STATES = {"setup_in_progress", "unload_in_progress"}
MAX_LISTED = 25


def section_ok(data: Any) -> dict[str, Any]:
    return {"status": "ok", "data": data}


def section_error(err: BaseException) -> dict[str, Any]:
    if isinstance(err, SupervisorError):
        kind, message = err.kind, err.message
    elif isinstance(err, CoreError):
        kind, message = err.kind, err.message
    else:
        kind, message = "error", f"Unexpected error ({type(err).__name__})."
    return {"status": "unavailable", "error": {"kind": kind, "message": message}}


async def collect(fn: Callable[[], Awaitable[Any]], parse: Callable[[Any], Any]) -> dict[str, Any]:
    try:
        raw = await fn()
        return section_ok(parse(raw))
    except (SupervisorError, CoreError) as err:
        return section_error(err)
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        return section_error(err)


# ---- parsers (pure; unit tested against API-shaped fixtures) -------------


def parse_system(info: dict[str, Any]) -> dict[str, Any]:
    """From Supervisor GET /info."""
    return {
        "homeassistant": info.get("homeassistant"),
        "supervisor": info.get("supervisor"),
        "os_version": info.get("hassos"),
        "operating_system": info.get("operating_system"),
        "arch": info.get("arch"),
        "supported_arch": list(info.get("supported_arch") or []),
        "machine": info.get("machine"),
        "hostname": info.get("hostname"),
        "channel": info.get("channel"),
        "timezone": info.get("timezone"),
        "supported": info.get("supported"),
        "state": info.get("state"),
    }


def parse_core_info(info: dict[str, Any]) -> dict[str, Any]:
    """From Supervisor GET /core/info."""
    return {
        "version": info.get("version"),
        "version_latest": info.get("version_latest"),
        "update_available": bool(info.get("update_available")),
        "machine": info.get("machine"),
        "arch": info.get("arch"),
    }


def parse_host(info: dict[str, Any]) -> dict[str, Any]:
    """From Supervisor GET /host/info (disk figures are in GB)."""
    return {
        "chassis": info.get("chassis"),
        "virtualization": info.get("virtualization") or None,
        "kernel": info.get("kernel"),
        "operating_system": info.get("operating_system"),
        "disk_total_gb": info.get("disk_total"),
        "disk_used_gb": info.get("disk_used"),
        "disk_free_gb": info.get("disk_free"),
    }


def parse_resolution(info: dict[str, Any]) -> dict[str, Any]:
    """From Supervisor GET /resolution/info."""
    issues = [{"type": i.get("type"), "context": i.get("context"), "reference": i.get("reference")} for i in info.get("issues") or []]
    return {
        "unsupported": list(info.get("unsupported") or []),
        "unhealthy": list(info.get("unhealthy") or []),
        "issues": issues[:MAX_LISTED],
        "issue_count": len(issues),
    }


def parse_apps(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """From Supervisor GET /addons (installed apps)."""
    items = sorted(
        (
            {
                "name": a.get("name"),
                "slug": a.get("slug"),
                "version": a.get("version"),
                "state": a.get("state"),
                "update_available": bool(a.get("update_available")),
                "repository": a.get("repository"),
            }
            for a in apps
        ),
        key=lambda a: (str(a["name"] or "")).lower(),
    )
    return {
        "count": len(items),
        "running": sum(1 for a in items if a["state"] == "started"),
        "updates": sum(1 for a in items if a["update_available"]),
        "items": items,
    }


def parse_config_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """From websocket ``config_entries/get``."""
    states = Counter()
    unhealthy = []
    disabled = 0
    ignored = 0
    domains = set()
    for entry in entries:
        if entry.get("source") == "ignore":
            ignored += 1
            continue
        domains.add(entry.get("domain"))
        if entry.get("disabled_by"):
            disabled += 1
            continue
        state = entry.get("state") or "unknown"
        states[state] += 1
        if state in UNHEALTHY_ENTRY_STATES:
            unhealthy.append(
                {
                    "domain": entry.get("domain"),
                    "title": entry.get("title"),
                    "state": state,
                    "reason": entry.get("reason"),
                    "entry_id": entry.get("entry_id"),
                }
            )
    unhealthy.sort(key=lambda e: (str(e["domain"]), str(e["title"])))
    return {
        "count": sum(states.values()) + disabled,
        "integrations": len(domains),
        "loaded": states.get("loaded", 0),
        "not_loaded": states.get("not_loaded", 0),
        "pending": sum(states.get(s, 0) for s in PENDING_ENTRY_STATES),
        "disabled": disabled,
        "ignored": ignored,
        "unhealthy_count": len(unhealthy),
        "unhealthy": unhealthy[:MAX_LISTED],
        "by_state": dict(states),
    }


def parse_areas(areas: list[dict[str, Any]]) -> dict[str, Any]:
    """From websocket ``config/area_registry/list``."""
    names = sorted((a.get("name") or a.get("area_id") or "?") for a in areas)
    return {"count": len(names), "names": names}


def parse_states(states: list[dict[str, Any]], registry: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """From REST ``GET /api/states`` (+ optional entity registry for platforms).

    "Unavailable" means the entity exists but its integration/device can't
    provide a value. ``unknown`` is common and benign, so it is only counted.
    """
    platform_of = {e.get("entity_id"): e.get("platform") for e in registry or []}
    unavailable = []
    unknown = 0
    by_domain: Counter = Counter()
    by_platform: Counter = Counter()
    for st in states:
        entity_id = st.get("entity_id", "")
        domain = entity_id.split(".", 1)[0]
        by_domain[domain] += 1
        value = st.get("state")
        if value == "unavailable":
            platform = platform_of.get(entity_id)
            unavailable.append(
                {
                    "entity_id": entity_id,
                    "name": (st.get("attributes") or {}).get("friendly_name") or entity_id,
                    "platform": platform,
                }
            )
            by_platform[platform or domain] += 1
        elif value == "unknown":
            unknown += 1
    unavailable.sort(key=lambda e: e["entity_id"])
    return {
        "count": len(states),
        "unavailable_count": len(unavailable),
        "unknown_count": unknown,
        "unavailable": unavailable[:MAX_LISTED],
        "unavailable_by_source": dict(by_platform.most_common(10)),
        "domains": len(by_domain),
    }


def parse_repairs(issues: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
    """From websocket ``repairs/list_issues`` (result ``{"issues": [...]}``)."""
    items = issues.get("issues", []) if isinstance(issues, dict) else issues
    active = [i for i in items if not i.get("ignored") and not i.get("dismissed_version")]
    return {
        "count": len(active),
        "items": [{"domain": i.get("domain"), "issue_id": i.get("issue_id"), "severity": i.get("severity")} for i in active[:MAX_LISTED]],
    }


def summarize(scan: dict[str, Any]) -> list[dict[str, str]]:
    """Short, plain-language observations for the top of the page."""
    notes: list[dict[str, str]] = []

    def data(name: str) -> dict[str, Any] | None:
        sec = scan.get(name) or {}
        return sec.get("data") if sec.get("status") == "ok" else None

    core = data("core")
    if core and core.get("update_available"):
        notes.append({"level": "info", "text": f"Home Assistant {core.get('version_latest')} is available."})
    integrations = data("integrations")
    if integrations and integrations["unhealthy_count"]:
        n = integrations["unhealthy_count"]
        notes.append({"level": "warn", "text": f"{n} integration{'s' if n != 1 else ''} failed to set up."})
    entities = data("entities")
    if entities and entities["unavailable_count"]:
        n = entities["unavailable_count"]
        notes.append({"level": "warn", "text": f"{n} entit{'ies are' if n != 1 else 'y is'} unavailable."})
    resolution = data("resolution")
    if resolution and (resolution["unhealthy"] or resolution["unsupported"]):
        notes.append({"level": "warn", "text": "The Supervisor reports this system as unhealthy or unsupported."})
    repairs = data("repairs")
    if repairs and repairs["count"]:
        n = repairs["count"]
        notes.append({"level": "info", "text": f"{n} repair{'s' if n != 1 else ''} waiting in Settings → Repairs."})
    apps = data("apps")
    if apps and apps["updates"]:
        n = apps["updates"]
        notes.append({"level": "info", "text": f"{n} app update{'s' if n != 1 else ''} available."})
    return notes


# ---- orchestration ------------------------------------------------------


async def _websocket_sections(core: CoreClient) -> dict[str, dict[str, Any]]:
    names = ("integrations", "areas", "registry", "repairs")
    try:
        async with core.websocket() as ws:

            async def cmd(msg_type: str) -> Any:
                return await ws.command(msg_type)

            results = {
                "integrations": await collect(lambda: cmd("config_entries/get"), parse_config_entries),
                "areas": await collect(lambda: cmd("config/area_registry/list"), parse_areas),
                "registry": await collect(lambda: cmd("config/entity_registry/list"), lambda r: r),
                "repairs": await collect(lambda: cmd("repairs/list_issues"), parse_repairs),
            }
            return results
    except CoreError as err:
        return {name: section_error(err) for name in names}


async def run_scan(supervisor: SupervisorClient, core: CoreClient) -> dict[str, Any]:
    started = time.monotonic()
    (system, core_info, host, resolution, apps, states_raw, ws) = await asyncio.gather(
        collect(supervisor.info, parse_system),
        collect(supervisor.core_info, parse_core_info),
        collect(supervisor.host_info, parse_host),
        collect(supervisor.resolution_info, parse_resolution),
        collect(supervisor.installed_apps, parse_apps),
        collect(core.states, lambda s: s),
        _websocket_sections(core),
    )

    registry = ws["registry"]["data"] if ws["registry"]["status"] == "ok" else None
    if states_raw["status"] == "ok":
        entities = section_ok(parse_states(states_raw["data"], registry))
    else:
        entities = states_raw

    # Fall back to Core's own /api/config for the version when the Supervisor
    # core endpoint is unavailable.
    if core_info["status"] != "ok":
        fallback = await collect(core.config, lambda c: {"version": c.get("version"), "update_available": False})
        if fallback["status"] == "ok":
            core_info = fallback

    scan = {
        "system": system,
        "core": core_info,
        "host": host,
        "resolution": resolution,
        "apps": apps,
        "integrations": ws["integrations"],
        "areas": ws["areas"],
        "entities": entities,
        "repairs": ws["repairs"],
    }
    scan["notes"] = summarize(scan)
    scan["duration_ms"] = int((time.monotonic() - started) * 1000)
    scan["scanned_at"] = int(time.time())
    return scan


def ha_version_from_scan(scan: dict[str, Any] | None) -> str | None:
    if not scan:
        return None
    for name, key in (("core", "version"), ("system", "homeassistant")):
        sec = scan.get(name) or {}
        if sec.get("status") == "ok" and sec["data"].get(key):
            return sec["data"][key]
    return None
