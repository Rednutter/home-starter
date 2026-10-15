"""Owned native Template helpers, expiring source state and Council refresh."""

from datetime import UTC, datetime, timedelta

from . import waste
from .core import CoreError
from .wodonga import fingerprint

SPECS = {
    "sensor.home_starter_next_bin_collection": ("Home Starter next bin collection", "next_date"),
    "sensor.home_starter_next_bin_types": ("Home Starter next bin types", "types_label"),
    "sensor.home_starter_bin_collection_day": ("Home Starter bin collection day", "day"),
    "sensor.home_starter_bin_days_until": ("Home Starter bin days until", "days_until"),
    "binary_sensor.home_starter_bin_night": ("Home Starter bin night", "bin_night"),
    "sensor.home_starter_bin_context": ("Home Starter bin context", "attention"),
}


def entry_signature(entry):
    return fingerprint({k: entry[k] for k in ("entry_id", "domain", "title", "modified_at")})


def helper_config(entity):
    name, field = SPECS[entity]
    available = (
        "{{ 0 <= as_timestamp(now()) - as_timestamp(state_attr('"
        + waste.SOURCE_ENTITY
        + "','checked_at'),0) < 180 and as_timestamp(now()) < as_timestamp(state_attr('"
        + waste.SOURCE_ENTITY
        + "','valid_until'),0)"
    )
    if field != "attention":
        available += " and state_attr('" + waste.SOURCE_ENTITY + "','usable') == true"
    available += " }}"
    return {"name": name, "state": "{{ state_attr('" + waste.SOURCE_ENTITY + "','" + field + "') }}", "additional_options": {"availability": available}}


async def native(core):
    async with core.websocket() as ws:
        entries = await ws.command("config_entries/get", domain="template")
        registry = await ws.command("config/entity_registry/list")
    return entries, registry


def check_owned(value, entries, registry):
    if set(value["helpers"]) != set(SPECS):
        return "Native bin entities are not yet fully prepared."
    for entity, record in value["helpers"].items():
        entry = next((e for e in entries if e["entry_id"] == record["entry_id"]), None)
        if (
            not record["entry_id"]
            or not entry
            or entry.get("domain") != "template"
            or entry.get("disabled_by")
            or entry.get("state") != "loaded"
            or entry_signature(entry) != record["signature"]
        ):
            return "An owned bin helper is missing, edited or unavailable. Inspect it in HA; existing edits are preserved."
        matches = [e for e in registry if e.get("config_entry_id") == record["entry_id"]]
        if len(matches) != 1 or matches[0]["entity_id"] != entity or matches[0].get("disabled_by"):
            return "A bin entity registry identity changed or is unavailable."
    return None


async def prepare(core, store, house):
    value = waste.load(store, house)
    if not value["confirmed"]:
        raise ValueError("Confirm the household waste service first.")
    entries, registry = await native(core)
    states = {s["entity_id"]: s for s in await core.states()}
    old = states.get(waste.SOURCE_ENTITY)
    if old and (old.get("attributes") or {}).get("home_starter_waste") != {"epoch": house["epoch"], "version": 1}:
        raise ValueError("Bin source address is already in use; no state was overwritten.")
    for entity in SPECS:
        if entity not in value["helpers"] and (entity in states or any(e["entity_id"] == entity for e in registry)):
            raise ValueError("A reserved bin entity address already exists. Inspect it in HA before continuing.")
    for entity in SPECS:
        if entity in value["helpers"]:
            if not value["helpers"][entity]["entry_id"]:
                raise ValueError("A prior helper creation is uncertain. Inspect native helpers before retrying; no duplicates were created.")
            continue
        record = {"entry_id": None, "flow_id": None, "signature": None}
        value["helpers"][entity] = record
        waste.save(store, value)
        flow = await core.template_flow({"handler": "template", "show_advanced_options": True})
        if flow.get("type") != "menu" or not flow.get("flow_id"):
            raise ValueError("Native Template helper setup did not open as expected.")
        record["flow_id"] = flow["flow_id"]
        waste.save(store, value)
        flow = await core.template_flow({"next_step_id": entity.split(".")[0]}, record["flow_id"])
        if flow.get("type") != "form" or flow.get("step_id") != entity.split(".")[0]:
            raise ValueError("Native Template helper flow changed; inspect it before retrying.")
        flow = await core.template_flow(helper_config(entity), record["flow_id"])
        if flow.get("type") != "create_entry" or not flow.get("result", {}).get("entry_id"):
            raise ValueError("Native bin helper creation was not verified. Inspect its flow in HA.")
        record.update(entry_id=flow["result"]["entry_id"], signature=entry_signature(flow["result"]), flow_id=None)
        waste.save(store, value)
    entries, registry = await native(core)
    problem = check_owned(value, entries, registry)
    if problem:
        raise ValueError(problem)
    return value


async def inspect(core, store, now=None):
    house = store.load()
    value = waste.load(store, house)
    result = waste.view(value, (await core.config())["time_zone"], now)
    result["screen_choices"] = [{"id": s["id"], "name": s["name"]} for s in house["surfaces"]]
    result["entity_issue"] = None
    if value["confirmed"]:
        try:
            result["entity_issue"] = check_owned(value, *(await native(core)))
        except CoreError:
            result["entity_issue"] = "Native bin entity inspection is unavailable."
    result["entities_ready"] = bool(value["confirmed"]) and result["entity_issue"] is None
    return result


async def project(core, store, house, now=None):
    now = now or datetime.now(UTC)
    value = waste.load(store, house)
    if not value["confirmed"]:
        return
    entries, registry = await native(core)
    problem = check_owned(value, entries, registry)
    if problem:
        raise ValueError(problem)
    data = waste.view(value, (await core.config())["time_zone"], now)
    old = next((s for s in await core.states() if s["entity_id"] == waste.SOURCE_ENTITY), None)
    owner = {"epoch": house["epoch"], "version": 1}
    if old and old.get("attributes", {}).get("home_starter_waste") != owner:
        raise ValueError("Bin source address is owned by another source.")
    next_collection = data["next"] or {}
    usable = data["status"] in {"current", "last_known_valid"}
    attributes = {
        "home_starter_waste": owner,
        "friendly_name": "Home Starter bin schedule source",
        "provider": data["provider"],
        "freshness": data["status"],
        "sources": data["sources"],
        "calculated": True,
        "checked_at": now.isoformat(),
        "source_checked_at": data["checked_at"],
        "last_verified": data["verified_at"],
        "valid_until": (now + timedelta(seconds=150)).isoformat(),
        "usable": usable,
        "next_date": next_collection.get("date"),
        "types": next_collection.get("types", []),
        "types_label": " · ".join({s["id"]: s["label"] for s in data["services"]}[t] for t in next_collection.get("types", [])),
        "day": data["day"],
        "days_until": data["days_until"],
        "following": data["following"],
        "bin_night": data["bin_night"],
        "attention": data["attention"] or "quiet",
        "summary": data["summary"],
        "renewal_due": data["renewal_due"],
    }
    if store.load() != house or waste.load(store, house)["revision"] != value["revision"]:
        return
    await core.context_state(waste.SOURCE_ENTITY, {"state": data["status"], "attributes": attributes})


async def tick(provider, core, store, now=None):
    now = now or datetime.now(UTC)
    house = store.load()
    value = waste.load(store, house)
    if not value["confirmed"]:
        return
    interval = timedelta(hours=1 if value["error"] else 24)
    if not value["checked_at"] or now - waste.timestamp(value["checked_at"]) >= interval:
        await waste.refresh(provider, core, store, house, now)
    await project(core, store, house, now)
