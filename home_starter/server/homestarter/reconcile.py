"""Private inventory comparison. Observation never changes HA or settings."""

from __future__ import annotations

import copy

from .household import HouseholdStore


def snapshot(inventory: dict, items: list[dict]) -> dict:
    known = {}
    semantics = {i["entity_id"]: i for i in items}
    for device in inventory["devices"]:
        known["device:" + device["id"]] = {
            "kind": "device",
            "label": device["name"],
            "area_id": device["area_id"],
            "status": device["status"],
            "connection": device.get("connection_fingerprint"),
        }
    entities = [e for d in inventory["devices"] for e in d["entities"]] + inventory["unattached_entities"]
    for entity in entities:
        item = semantics[entity["entity_id"]]
        attrs = item.get("attributes", {})
        known["entity:" + (entity.get("registry_id") or entity["entity_id"])] = {
            "kind": "entity",
            "label": entity["name"],
            "entity_id": entity["entity_id"],
            "area_id": entity.get("area_id"),
            "available": item["available"],
            "unavailable": bool(
                entity.get("observed") and not entity.get("disabled_by") and not entity.get("hidden_by") and entity.get("state") == "unavailable"
            ),
            "function": item["function"],
            "capabilities": {k: attrs[k] for k in ("supported_features", "hvac_modes", "fan_modes", "preset_modes") if k in attrs},
        }
    for entry in inventory.get("integrations", []):
        if entry.get("source") == "ignore":
            continue
        known["integration:" + entry["entry_id"]] = {
            "kind": "integration",
            "label": entry["domain"],
            "status": entry.get("state"),
            "disabled": entry.get("disabled_by") is not None,
        }
    return known


def observe(store: HouseholdStore, house: dict, inventory: dict, items: list[dict]) -> dict:
    saved = store.read(store.observation_path, None)
    if saved is not None and (
        not isinstance(saved, dict) or saved.get("version") != 1 or not isinstance(saved.get("known"), dict) or not isinstance(saved.get("pending"), dict)
    ):
        raise ValueError("Unsupported inventory history. Existing runtime data is preserved.")
    if saved is None or saved.get("epoch") != house["epoch"]:
        saved = {"version": 1, "epoch": house["epoch"], "revision": 0, "known": {}, "pending": {}}
    if not inventory["complete"]:
        return {**saved, "complete": False, "baseline_created": False}
    current = snapshot(inventory, items)
    pending = copy.deepcopy(saved["pending"])
    initial = saved["revision"] == 0
    if not initial:
        for key in sorted(saved["known"].keys() | current.keys()):
            old, new = saved["known"].get(key), current.get(key)
            if old == new:
                continue
            # Keep the last unreviewed starting point: a later availability change
            # must not hide a registry rename or another still-pending difference.
            old = pending[key]["before"] if key in pending else old
            if old == new:
                pending.pop(key, None)
                continue
            category = (
                "new"
                if old is None
                else "missing"
                if new is None
                else "renamed"
                if (old.get("entity_id") != new.get("entity_id") or old["label"] != new["label"])
                else "capability"
                if (old.get("capabilities") != new.get("capabilities"))
                else "connection"
                if (old.get("connection") != new.get("connection"))
                else "changed"
            )
            pending[key] = {"key": key, "category": category, "before": old, "after": new, "label": (new or old)["label"], "kind": (new or old)["kind"]}
    value = {**saved, "known": current, "pending": pending}
    if initial or value != saved:
        value["revision"] += 1
        store.write(store.observation_path, value)
    return {**value, "complete": True, "baseline_created": initial}


def acknowledge(store: HouseholdStore, house: dict, revision: int) -> None:
    value = store.read(store.observation_path, None)
    if not value or value["epoch"] != house["epoch"] or value["revision"] != revision:
        raise ValueError("The house changed. Refresh and review the differences first.")
    if value["pending"]:
        value["pending"] = {}
        value["revision"] += 1
        store.write(store.observation_path, value)
