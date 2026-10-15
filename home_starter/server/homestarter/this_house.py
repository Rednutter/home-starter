"""Live HA household projection; retain only confirmations, notes and our changes."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import UTC, datetime

from .core import CoreError
from .house_readiness import report as readiness_report
from .household import text
from .inventory import assign_area, collect_inventory

EQUIPMENT = {
    "light",
    "switch",
    "sensor",
    "binary_sensor",
    "climate",
    "cover",
    "media_player",
    "camera",
    "vacuum",
    "fan",
    "lock",
    "remote",
    "event",
    "device_tracker",
    "water_heater",
    "alarm_control_panel",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def empty():
    return {
        "version": 1,
        "revision": 0,
        "expectation": None,
        "people": {},
        "presence": {},
        "placements": {},
        "portable": {},
        "multiroom": {},
        "area_intent": {},
        "relationships": {},
        "structure": None,
        "changes": [],
    }


def load(store):
    value = store.read(store.this_house_path, empty())
    if isinstance(value, dict):
        value.setdefault("area_intent", {})
        value.setdefault("multiroom", {})
        value.setdefault("presence", {})
    if (
        not isinstance(value, dict)
        or set(value) != set(empty())
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["revision"]) is not int
        or value["revision"] < 0
        or any(not isinstance(value[k], dict) for k in ("people", "presence", "placements", "portable", "multiroom", "relationships", "area_intent"))
        or not isinstance(value["changes"], list)
        or len(value["changes"]) > 100
    ):
        raise ValueError("House confirmations could not be read. Existing data is preserved; restore the file before saving.")
    if value["expectation"] is not None:
        counts = value["expectation"]
        if (
            not isinstance(counts, dict)
            or set(counts) != {"people", "adults"}
            or type(counts["people"]) is not int
            or type(counts["adults"]) is not int
            or not 1 <= counts["people"] <= 50
            or not 0 <= counts["adults"] <= counts["people"]
        ):
            raise ValueError("Invalid household expectation. Existing data is preserved.")
    for item in value["people"].values():
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "signature"}
            or item["role"] not in {"adult", "child", "other"}
            or not signature(item["signature"])
        ):
            raise ValueError("Invalid person confirmation. Existing data is preserved.")
    if (
        any(not signature(v) for key in ("placements", "portable", "multiroom") for v in value[key].values())
        or value["structure"] is not None
        and not signature(value["structure"])
    ):
        raise ValueError("Invalid placement confirmation. Existing data is preserved.")
    if any(not text(v, 240) for v in value["relationships"].values()):
        raise ValueError("Invalid physical relationship note. Existing data is preserved.")
    for item in value["area_intent"].values():
        if not isinstance(item, dict) or set(item) != {"kind", "signature"} or item["kind"] not in {"room", "group"} or not signature(item["signature"]):
            raise ValueError("Invalid area confirmation. Existing data is preserved.")
    for item in value["presence"].values():
        if not isinstance(item, dict) or set(item) != {"plan", "signature"} or item["plan"] not in {"wanted", "untracked"} or not signature(item["signature"]):
            raise ValueError("Invalid presence choice. Existing data is preserved.")
    return value


def signature(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def write(store, value):
    # A private atomic file, with no registry copy or credentials.
    path = store.this_house_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def placement_signature(device, area=None, floor=None):
    return digest(
        {
            "id": device["id"],
            "name": device["name"],
            "area_id": device.get("area_id"),
            "connection": device.get("connection_fingerprint"),
            "area": area,
            "floor": floor,
            "entities": sorted((e["entity_id"], e.get("area_id")) for e in device["entities"]),
        }
    )


def equipment(device):
    return device.get("entry_type") != "service" and any(
        e["entity_id"].split(".")[0] in EQUIPMENT and e.get("entity_category") not in {"diagnostic", "config"} for e in device["entities"]
    )


async def inspect(core, store, checks=None):
    inventory = await collect_inventory(core)
    saved = load(store)
    people_error = None
    try:
        async with core.websocket() as ws:
            records = await ws.command("person/list")
        if not isinstance(records, dict) or any(not isinstance(records.get(k), list) for k in ("storage", "config")):
            raise CoreError("api", "Unexpected person records.")
    except CoreError:
        records = {"storage": [], "config": []}
        people_error = "People could not be read. Missing data is not evidence that a person is absent."
    all_entities = [e for d in inventory["devices"] for e in d["entities"]] + inventory["unattached_entities"]
    trackers = [
        {
            "entity_id": e["entity_id"],
            "name": e["name"],
            "device_id": e.get("device_id"),
            "disabled": bool(e.get("disabled_by")),
            "available": e.get("observed") is True and e.get("state") not in {None, "unknown", "unavailable"},
        }
        for e in all_entities
        if e["entity_id"].startswith("device_tracker.")
    ]
    people = []
    for source in ("storage", "config"):
        for person in records[source]:
            if (
                not isinstance(person, dict)
                or not text(person.get("id"))
                or not text(person.get("name"))
                or not isinstance(person.get("device_trackers", []), list)
            ):
                raise ValueError("Unexpected person data. Check Home Assistant.")
            tracker_ids = person.get("device_trackers", [])
            if any(not isinstance(t, str) or not t.startswith("device_tracker.") for t in tracker_ids):
                raise ValueError("Unexpected person trackers. Check Home Assistant.")
            token = digest([person["id"], person["name"], sorted(tracker_ids)])
            decision = saved["people"].get(person["id"])
            confirmed = bool(decision and decision["signature"] == token)
            presence = saved["presence"].get(person["id"])
            people.append(
                {
                    "id": person["id"],
                    "name": person["name"],
                    "trackers": tracker_ids,
                    "usable_tracker": any(t["entity_id"] in tracker_ids and t["available"] and not t["disabled"] for t in trackers),
                    "editable": source == "storage",
                    "signature": token,
                    "confirmed": confirmed,
                    "role": decision["role"] if confirmed else None,
                    "presence_plan": presence["plan"] if confirmed and decision["role"] != "other" and presence and presence["signature"] == token else None,
                    "changed": bool(decision and not confirmed),
                }
            )
    for tracker in trackers:
        tracker["people"] = [p["id"] for p in people if tracker["entity_id"] in p["trackers"]]
    floors = [{k: f.get(k) for k in ("floor_id", "name", "level")} for f in inventory["floors"]]
    areas = [{k: a.get(k) for k in ("area_id", "name", "floor_id")} for a in inventory["areas"]]
    structure = digest([sorted(floors, key=lambda f: f["floor_id"]), sorted(areas, key=lambda a: a["area_id"])])
    for area in areas:
        area["signature"] = digest(area)
        intent = saved["area_intent"].get(area["area_id"])
        area["kind"] = intent["kind"] if intent and intent["signature"] == area["signature"] else None
    area_ids = {a["area_id"] for a in areas}
    names = [d["name"].casefold() for d in inventory["devices"] if equipment(d) and d.get("model") != "Google Cast Group"]
    devices = []
    for device in inventory["devices"]:
        if not equipment(device):
            continue
        area = next((a for a in areas if a["area_id"] == device.get("area_id")), None)
        floor = next((f for f in floors if area and f["floor_id"] == area["floor_id"]), None)
        token = placement_signature(device, area, floor)
        reasons = [r for f in inventory["findings"] if device["id"] in f["device_ids"] and f["category"] != "needs_room" for r in f["reasons"]]
        if names.count(device["name"].casefold()) > 1:
            reasons.append(
                "Several HA equipment records share this name. Compare their integrations and models; "
                "these may be valid views of the same hardware. Nothing is merged or removed."
            )
        overrides = [e["entity_id"] for e in device["entities"] if e.get("area_id") and e["area_id"] != device.get("area_id")]
        if overrides:
            reasons.append(f"{len(overrides)} entities have a different room override; device placement will preserve those overrides.")
        multiroom = saved["multiroom"].get(device["id"]) == token and bool(saved["relationships"].get(device["id"]))
        placed = device.get("area_id") in area_ids
        if area and area["kind"] == "group" and not multiroom:
            placed = False
            reasons.append("Assigned to a group of rooms or whole level; choose its individual physical room.")
        shared = device.get("model") == "Google Cast Group"
        portable = saved["portable"].get(device["id"]) == token
        devices.append(
            {
                "id": device["id"],
                "name": device["name"],
                "manufacturer": device.get("manufacturer"),
                "model": device.get("model"),
                "integrations": sorted({e["domain"] for e in device["integrations"]}),
                "area_id": device.get("area_id"),
                "path": device["path"],
                "signature": token,
                "shared": shared,
                "portable": portable,
                "multiroom": multiroom,
                "needs_room": not placed and not shared and not portable and not multiroom,
                "confirmed": placed and saved["placements"].get(device["id"]) == token,
                "changed": device["id"] in saved["placements"] and saved["placements"][device["id"]] != token,
                "attention": bool(reasons),
                "reasons": list(dict.fromkeys(reasons)),
                "placed": placed,
                "status": device["status"],
                "entity_count": len(device["entities"]),
                "overrides": overrides,
                "relationship": saved["relationships"].get(device["id"], ""),
            }
        )
    members = [p for p in people if p["role"] in {"adult", "child"}]
    adults = sum(p["role"] == "adult" for p in members)
    expectation = saved["expectation"]
    complete = inventory["complete"] and inventory["sources"].get("floors", {}).get("status") == "ok" and not people_error
    return {
        "revision": saved["revision"],
        "complete": bool(complete),
        "people_error": people_error,
        "people": people,
        "trackers": trackers,
        "floors": floors,
        "areas": areas,
        "devices": devices,
        "services": [
            {
                "entity_id": e["entity_id"],
                "name": e["name"],
                "domain": e["entity_id"].split(".")[0],
                "area_id": e.get("area_id"),
                "availability": "disabled"
                if e.get("disabled_by")
                else "unknown"
                if not e.get("observed") or e.get("state") in {None, "unknown"}
                else "unavailable"
                if e["state"] == "unavailable"
                else "reporting",
            }
            for e in inventory["unattached_entities"]
            if e["entity_id"].split(".")[0] in (EQUIPMENT | {"calendar"}) - {"device_tracker"} and e.get("entity_category") not in {"diagnostic", "config"}
        ],
        "integration_issues": [
            {k: f.get(k) for k in ("title", "confidence", "reasons", "path")}
            for f in inventory["findings"]
            if (f.get("path") or "").startswith(("/config/integrations/", "/config/repairs"))
        ],
        "capabilities": readiness_report(inventory, people, checks) if checks is not None else [],
        "structure_signature": structure,
        "structure_confirmed": saved["structure"] == structure,
        "expectation": expectation,
        "changes": saved["changes"][-20:],
        "sources": inventory["sources"],
        "counts": {
            "people": len(people),
            "members": len(members),
            "adults": adults,
            "people_needing_review": sum(not p["confirmed"] for p in people),
            "floors": len(floors),
            "areas": len(areas),
            "areas_without_floor": sum(not a["floor_id"] for a in areas),
            "devices": len(devices),
            "registry_devices": len(inventory["devices"]),
            "placed": sum(d["placed"] for d in devices),
            "confirmed": sum(d["confirmed"] for d in devices),
            "needs_room": sum(d["needs_room"] for d in devices),
            "attention": sum(d["attention"] for d in devices),
            "members_without_tracker": sum(not p["usable_tracker"] for p in members),
            "intentionally_untracked": sum(p["presence_plan"] == "untracked" for p in members),
            "other_members_without_tracker": sum(not p["usable_tracker"] and p["presence_plan"] != "untracked" for p in members),
            "shared": sum(d["shared"] for d in devices),
            "portable": sum(d["portable"] for d in devices),
            "multiroom": sum(d["multiroom"] for d in devices),
            "expectation_matches": bool(expectation and expectation == {"people": len(members), "adults": adults}),
        },
    }


def fields(body, required):
    if set(body) != {"confirm", "revision", *required} or body.get("confirm") is not True or type(body.get("revision")) is not int:
        raise ValueError("Review and confirm the requested house change.")


async def act(core, store, action, body):
    saved = load(store)
    if type(body.get("revision")) is not int or body["revision"] != saved["revision"]:
        raise ValueError("House confirmations changed elsewhere. Refresh before saving.")
    view = await inspect(core, store)
    if not view["complete"]:
        raise ValueError("The house could not be read completely. Refresh before changing anything.")
    updated = copy.deepcopy(saved)
    change = {"action": action, "at": datetime.now(UTC).isoformat()}
    if action == "expectation":
        fields(body, {"people", "adults"})
        if type(body["people"]) is not int or type(body["adults"]) is not int or not 1 <= body["people"] <= 50 or not 0 <= body["adults"] <= body["people"]:
            raise ValueError("Choose a household size from 1 to 50 and an adult count within it.")
        updated["expectation"] = {"people": body["people"], "adults": body["adults"]}
        change.update(before=saved["expectation"], after=updated["expectation"])
    elif action == "person":
        fields(body, {"person_id", "role", "expected"})
        person = next((p for p in view["people"] if p["id"] == body["person_id"]), None)
        if not person or person["signature"] != body["expected"] or body["role"] not in {"adult", "child", "other"}:
            raise ValueError("That person changed or the household role is invalid. Refresh first.")
        updated["people"][person["id"]] = {"role": body["role"], "signature": person["signature"]}
        change.update(id=person["id"], after=body["role"])
    elif action == "presence":
        fields(body, {"person_id", "plan", "expected"})
        person = next((p for p in view["people"] if p["id"] == body["person_id"]), None)
        if not person or person["signature"] != body["expected"] or person["role"] not in {"adult", "child"} or body["plan"] not in {"wanted", "untracked"}:
            raise ValueError("Review the household member and choose whether presence is wanted.")
        updated["presence"][person["id"]] = {"plan": body["plan"], "signature": person["signature"]}
        change.update(id=person["id"], after=body["plan"])
    elif action == "area_intent":
        fields(body, {"area_id", "kind", "expected"})
        area = next((a for a in view["areas"] if a["area_id"] == body["area_id"]), None)
        if not area or area["signature"] != body["expected"] or body["kind"] not in {"room", "group"}:
            raise ValueError("That area changed or its purpose is invalid. Refresh first.")
        updated["area_intent"][area["area_id"]] = {"kind": body["kind"], "signature": area["signature"]}
        change.update(id=area["area_id"], after=body["kind"])
    elif action in {"floor", "area", "structure"}:
        fields(body, {"expected"} if action == "structure" else {"id", "name", "expected", "level" if action == "floor" else "floor_id"})
        if body["expected"] != view["structure_signature"]:
            raise ValueError("Floors or rooms changed in Home Assistant. Refresh and review again.")
        if action == "structure":
            if not view["areas"] or not view["floors"]:
                raise ValueError("Add the house's floors and rooms before confirming them.")
            updated["structure"] = view["structure_signature"]
        else:
            name = body["name"]
            if not text(name) or name != name.strip():
                raise ValueError("Use a short floor or room name without surrounding spaces.")
            key = "floor_id" if action == "floor" else "area_id"
            items = view["floors"] if action == "floor" else view["areas"]
            current = next((i for i in items if i[key] == body["id"]), None)
            if body["id"] is not None and current is None:
                raise ValueError("That floor or room no longer exists.")
            if any(i["name"].casefold() == name.casefold() and i[key] != body["id"] for i in items):
                raise ValueError("That name already exists. Review the existing record instead.")
            payload = {"name": name}
            if action == "floor":
                if body["level"] is not None and (type(body["level"]) is not int or not -100 <= body["level"] <= 200):
                    raise ValueError("Use a floor level between -100 and 200, or leave it blank.")
                payload["level"] = body["level"]
            else:
                if body["floor_id"] is not None and body["floor_id"] not in {f["floor_id"] for f in view["floors"]}:
                    raise ValueError("That floor no longer exists.")
                # HA create accepts an omitted floor, update also accepts null.
                if current or body["floor_id"] is not None:
                    payload["floor_id"] = body["floor_id"]
            async with core.websocket() as ws:
                result = await ws.command(
                    f"config/{action}_registry/{'update' if current else 'create'}", **({key: current[key]} if current else {}), **payload
                )
                identifier = current[key] if current else result.get(key) if isinstance(result, dict) else None
                fresh = await ws.command(f"config/{action}_registry/list")
            readback = next((i for i in fresh if i[key] == identifier), None)
            expected = {**payload, **({"floor_id": None} if action == "area" and "floor_id" not in payload else {})}
            if not readback or any(readback.get(k) != v for k, v in expected.items()):
                raise ValueError("HA may have changed, but readback did not match. Refresh before retrying.")
            change.update(id=identifier, before=current, after={k: readback.get(k) for k in (key, *expected)})
    elif action in {"placement", "relationship", "portable", "multiroom"}:
        fields(body, {"device_id", "expected"} | ({"area_id"} if action == "placement" else {"text"} if action == "relationship" else set()))
        device = next((d for d in view["devices"] if d["id"] == body["device_id"]), None)
        if not device or device["signature"] != body["expected"]:
            raise ValueError("That device or its room changed. Refresh and review again.")
        change["id"] = device["id"]
        if action == "portable":
            updated["portable"][device["id"]] = device["signature"]
            updated["multiroom"].pop(device["id"], None)
        elif action == "multiroom":
            if not saved["relationships"].get(device["id"]):
                raise ValueError("Record which rooms this equipment serves in its physical note first.")
            updated["multiroom"][device["id"]] = device["signature"]
            updated["portable"].pop(device["id"], None)
        elif action == "relationship":
            if not isinstance(body["text"], str) or body["text"] and not text(body["text"], 240):
                raise ValueError("Use a physical connection or function note of at most 240 characters.")
            if body["text"]:
                updated["relationships"][device["id"]] = body["text"]
            else:
                updated["relationships"].pop(device["id"], None)
        else:
            updated["portable"].pop(device["id"], None)
            updated["multiroom"].pop(device["id"], None)
            if body["area_id"] not in {a["area_id"] for a in view["areas"] if a["kind"] != "group"}:
                raise ValueError("Choose an existing room.")
            if body["area_id"] != device["area_id"]:
                result = await assign_area(core, device["id"], body["area_id"], device["area_id"])
                if not result["verified"]:
                    raise ValueError(result["error"])
                fresh = await inspect(core, store)
                device = next((d for d in fresh["devices"] if d["id"] == device["id"]), None)
                if not device or device["area_id"] != body["area_id"]:
                    raise ValueError("HA may have changed, but placement was not verified. Refresh before retrying.")
            updated["placements"][device["id"]] = device["signature"]
            change.update(before=next(d["area_id"] for d in view["devices"] if d["id"] == device["id"]), after=body["area_id"])
    else:
        raise ValueError("Unsupported house action.")
    # Confirmations are scoped to live signatures; availability never proves placement.
    updated["revision"] += 1
    updated["changes"] = [*updated["changes"], change][-100:]
    write(store, updated)
    return {"verified": True, "revision": updated["revision"]}
