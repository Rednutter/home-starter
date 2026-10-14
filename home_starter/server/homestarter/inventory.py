"""Household inventory from HA registries. No discovery or persistent storage."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from itertools import combinations
from typing import Any
from urllib.parse import quote

from .core import CoreClient, CoreError

BAD_STATES = {"setup_error", "setup_retry", "migration_error", "failed_unload"}
COMMANDS = {
    "devices": "config/device_registry/list",
    "areas": "config/area_registry/list",
    "floors": "config/floor_registry/list",
    "entities": "config/entity_registry/list",
    "integrations": "config_entries/get",
    "repairs": "repairs/list_issues",
}


def validate_source(name: str, value: Any) -> Any:
    """A malformed source is unavailable, not an empty successful scan."""
    if name == "repairs":
        if not isinstance(value, dict) or not isinstance(value.get("issues"), list):
            raise CoreError("api", "Home Assistant returned an unexpected repairs response.")
        return value
    key = {"devices": "id", "areas": "area_id", "floors": "floor_id", "entities": "entity_id", "states": "entity_id", "integrations": "entry_id"}[name]
    if not isinstance(value, list) or any(not isinstance(item, dict) or not isinstance(item.get(key), str) for item in value):
        raise CoreError("api", f"Home Assistant returned an unexpected {name} response.")
    return value


def pairs(value: Any, *, mac: bool = False) -> set[tuple[str, str]]:
    result = set()
    for item in value or []:
        if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(x, str) and x for x in item):
            kind, identity = item
            if mac and kind == "mac":
                identity = re.sub(r"[^a-f0-9]", "", identity.lower())
                if len(identity) != 12 or identity == "000000000000":
                    continue
            result.add((kind, identity))
    return result


def build_inventory(sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    def data(name: str, default=None):
        source = sources.get(name, {})
        return source.get("data", default) if source.get("status") == "ok" else default

    raw_devices = data("devices", [])
    areas = {a["area_id"]: a for a in data("areas", [])}
    entries = {e["entry_id"]: e for e in data("integrations", [])}
    states = {s["entity_id"]: s for s in data("states", [])}
    registry = {e["entity_id"]: e for e in data("entities", [])}
    # YAML entities may exist in states without a registry entry.
    entities = []
    for entity_id in sorted(registry.keys() | states.keys()):
        entry, live = registry.get(entity_id, {}), states.get(entity_id, {})
        entities.append(
            {
                "entity_id": entity_id,
                "registry_id": entry.get("id"),
                "device_id": entry.get("device_id"),
                "area_id": entry.get("area_id"),
                "name": entry.get("name") or (live.get("attributes") or {}).get("friendly_name") or entry.get("original_name") or entity_id,
                "platform": entry.get("platform"),
                "config_entry_id": entry.get("config_entry_id"),
                "disabled_by": entry.get("disabled_by"),
                "hidden_by": entry.get("hidden_by"),
                "entity_category": entry.get("entity_category"),
                "state": live.get("state"),
                "observed": entity_id in states,
            }
        )
    devices = []
    findings = []

    def finding(category, title, confidence, reasons, device_ids=None, path=None, suggestion=None):
        findings.append(
            {
                "category": category,
                "title": title,
                "confidence": confidence,
                "reasons": reasons,
                "device_ids": device_ids or [],
                "path": path,
                "suggestion": suggestion,
            }
        )

    complete = all(sources.get(n, {}).get("status") == "ok" for n in ("devices", "areas", "entities", "states", "integrations"))
    for raw in raw_devices:
        device_id = raw["id"]
        owned = [e for e in entities if e["device_id"] == device_id]
        enabled = [e for e in owned if not e["disabled_by"]]
        observed = [e for e in enabled if e["observed"]]
        unavailable = [e for e in observed if e["state"] == "unavailable"]
        entry_ids = list(raw.get("config_entries") or [])
        if raw.get("config_entry_id") and raw["config_entry_id"] not in entry_ids:
            entry_ids.append(raw["config_entry_id"])
        integrations = [entries[e] for e in entry_ids if e in entries]
        name = raw.get("name_by_user") or raw.get("name") or raw.get("model") or "Unnamed device"
        device = {
            k: raw.get(k)
            for k in (
                "id",
                "area_id",
                "manufacturer",
                "model",
                "entry_type",
                "disabled_by",
                "parent_device_id",
                "via_device_id",
                "config_entry_id",
                "config_subentry_id",
            )
        }
        device.update(
            connection_fingerprint=hashlib.sha256(
                json.dumps([raw.get("configuration_url"), sorted(pairs(raw.get("connections")))], sort_keys=True).encode()
            ).hexdigest(),
            name=name,
            entities=owned,
            integrations=integrations,
            config_entries=entry_ids,
            identifiers=sorted(pairs(raw.get("identifiers"))),
            connections=sorted(pairs(raw.get("connections"), mac=True)),
            linked_ids=[],
            children_ids=[],
            sibling_ids=[],
            unavailable_count=len(unavailable),
            disabled_count=len(owned) - len(enabled),
            status="unknown",
            path=f"/config/devices/device/{quote(device_id, safe='')}",
        )
        if sources.get("areas", {}).get("status") == "ok" and not raw.get("area_id"):
            reasons = ["Home Assistant has no room assigned to this device."]
            suggestion = None
            votes = Counter(e["area_id"] for e in owned if e["area_id"] in areas)
            named = [a for a in areas.values() if re.search(r"\b" + re.escape(a["name"]) + r"\b", name, re.I)]
            if len(votes) == 1:
                area_id = next(iter(votes))
                suggestion = {
                    "area_id": area_id,
                    "name": areas[area_id]["name"],
                    "confidence": "High confidence" if votes[area_id] >= 2 else "Plausible",
                    "reasons": [f"{votes[area_id]} related entities are assigned to {areas[area_id]['name']}."],
                }
                if any(a["area_id"] != area_id for a in named):
                    suggestion = None
            elif not votes and len(named) == 1:
                suggestion = {
                    "area_id": named[0]["area_id"],
                    "name": named[0]["name"],
                    "confidence": "Plausible",
                    "reasons": [f"Its name contains the room name {named[0]['name']}."],
                }
            finding("needs_room", name, "Confirmed", reasons, [device_id], device["path"], suggestion)
        bad = [e for e in integrations if e.get("state") in BAD_STATES and not e.get("disabled_by") and e.get("source") != "ignore"]
        disabled_entry = any(e.get("disabled_by") for e in integrations)
        if raw.get("disabled_by") or disabled_entry:
            finding(
                "attention",
                name,
                "Confirmed",
                ["This device or its integration is disabled in Home Assistant. This may be intentional."],
                [device_id],
                device["path"],
            )
            device["status"] = "disabled"
        elif unavailable and (len(unavailable) >= 2 or len(unavailable) == len(enabled)):
            finding(
                "attention",
                name,
                "Confirmed",
                [
                    f"{len(unavailable)} of {len(enabled)} enabled entities are unavailable during this scan.",
                    "This may be power, connectivity or a sleeping device; it does not establish retired hardware.",
                ],
                [device_id],
                device["path"],
            )
            device["status"] = "attention"
            if bad and len(unavailable) == len(enabled):
                finding(
                    "offline",
                    name,
                    "Unknown",
                    [
                        "This hasn't been available during the scan, and its integration cannot connect.",
                        "Wake or power it, then check again. Only you can confirm whether it is retired.",
                    ],
                    [device_id],
                    device["path"],
                )
        elif bad:
            device["status"] = "attention"
        elif (
            complete
            and enabled
            and len(observed) == len(enabled)
            and all(e["state"] not in ("unavailable", "unknown") for e in enabled)
            and len(integrations) == len(entry_ids)
            and all(e.get("state") == "loaded" and e.get("source") != "ignore" for e in integrations)
        ):
            device["status"] = "fine"
        devices.append(device)

    by_id = {d["id"]: d for d in devices}
    for device in devices:
        parent = device.get("parent_device_id")
        if parent in by_id:
            by_id[parent]["children_ids"].append(device["id"])
            device["sibling_ids"] = [d["id"] for d in devices if d["id"] != device["id"] and d.get("parent_device_id") == parent]
    for left, right in combinations(devices, 2):
        # Child identifiers are scoped to their parent, not physical identity.
        if left.get("parent_device_id") or right.get("parent_device_id"):
            continue
        shared_mac = pairs(left["connections"], mac=True) & pairs(right["connections"], mac=True)
        shared_ids = pairs(left["identifiers"]) & pairs(right["identifiers"])
        if shared_mac or shared_ids:
            left["linked_ids"].append(right["id"])
            right["linked_ids"].append(left["id"])
            # HA deliberately keeps integration-specific representations separate.
            finding(
                "duplicate",
                f"{left['name']} / {right['name']}",
                "Plausible",
                [
                    "HA exposes the same connection or identifier on these devices.",
                    "They may be valid views of the same hardware through different integrations. Review in HA; no merge is proposed.",
                ],
                [left["id"], right["id"]],
                left["path"],
            )
    for entry in entries.values():
        if entry.get("source") == "ignore":
            continue
        if entry.get("state") in BAD_STATES and not entry.get("disabled_by"):
            finding(
                "attention",
                entry.get("title") or entry.get("domain"),
                "Confirmed",
                ["This integration failed to set up.", entry.get("reason") or "Home Assistant did not provide a reason; check its logs."],
                [d["id"] for d in devices if entry["entry_id"] in d["config_entries"]],
                f"/config/integrations/integration/{quote(entry['domain'], safe='')}",
            )
    repairs = data("repairs", {})
    for repair in repairs.get("issues", []) if isinstance(repairs, dict) else repairs:
        if not repair.get("ignored") and not repair.get("dismissed_version"):
            finding(
                "attention",
                "Home Assistant repair",
                "Confirmed",
                [f"Home Assistant reports {repair.get('domain')}: {repair.get('issue_id')}.", "Open Repairs for the full explanation."],
                path="/config/repairs",
            )
    rooms = [{**a, "device_ids": [d["id"] for d in devices if d["area_id"] == a["area_id"]]} for a in areas.values()]
    return {
        "devices": devices,
        "areas": rooms,
        "floors": data("floors", []),
        "integrations": [{k: e.get(k) for k in ("entry_id", "domain", "title", "state", "disabled_by", "source")} for e in entries.values()],
        "unattached_entities": [e for e in entities if e["device_id"] not in by_id],
        "findings": findings,
        "sources": {n: {k: v for k, v in s.items() if k != "data"} for n, s in sources.items()},
        "complete": complete,
        "counts": {
            "devices": len(devices),
            "areas": len(areas),
            "entities": len(entities),
            "integrations": len({e["domain"] for e in entries.values() if e.get("source") != "ignore"}),
            "ignored_entries": sum(e.get("source") == "ignore" for e in entries.values()),
            "fine": sum(d["status"] == "fine" for d in devices),
            "findings": len(findings),
        },
    }


async def collect_inventory(core: CoreClient) -> dict[str, Any]:
    sources = {}
    try:
        async with core.websocket() as ws:
            for name, command in COMMANDS.items():
                try:
                    sources[name] = {"status": "ok", "data": validate_source(name, await ws.command(command))}
                except CoreError as err:
                    sources[name] = {"status": "unavailable", "error": {"kind": err.kind, "message": err.message}}
    except CoreError as err:
        sources.update({name: {"status": "unavailable", "error": {"kind": err.kind, "message": err.message}} for name in COMMANDS})
    try:
        sources["states"] = {"status": "ok", "data": validate_source("states", await core.states())}
    except CoreError as err:
        sources["states"] = {"status": "unavailable", "error": {"kind": err.kind, "message": err.message}}
    return build_inventory(sources)


async def assign_area(core: CoreClient, device_id: str, area_id: str | None, expected_area_id: str | None) -> dict[str, Any]:
    """Compare live state, change one field, then verify with a fresh registry read."""
    async with core.websocket() as ws:
        devices = await ws.command("config/device_registry/list")
        device = next((d for d in devices if d["id"] == device_id), None)
        if device is None:
            return {"verified": False, "error": "Device no longer exists. Check again."}
        if device.get("area_id") != expected_area_id:
            return {"verified": False, "error": "The room changed since you reviewed it. Check again before making another change."}
        areas = await ws.command("config/area_registry/list")
        if area_id is not None and not any(a["area_id"] == area_id for a in areas):
            return {"verified": False, "error": "That room no longer exists. Check again."}
        await ws.command("config/device_registry/update", device_id=device_id, area_id=area_id)
        fresh = await ws.command("config/device_registry/list")
        changed = next((d for d in fresh if d["id"] == device_id), None)
        verified = changed is not None and changed.get("area_id") == area_id
        return {
            "verified": verified,
            "device_id": device_id,
            "area_id": area_id,
            "error": None if verified else "The requested room change was not confirmed by Home Assistant. Check again.",
        }
