"""Read selected native sources; opt-in wall projections use owned ephemeral HA states."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from . import context, readiness, this_house, waste
from .core import CoreError
from .inventory import collect_inventory
from .surfaces import admitted, classify, fingerprint, preferences


async def inspect(core, store, surface=None, now=None):
    now = now or datetime.now(UTC)
    house = store.load()
    saved = readiness.load(store, house)
    settings = saved["context"]
    inventory = await collect_inventory(core)
    states = await core.states()
    zone = (await core.config())["time_zone"]
    members = (await this_house.inspect(core, store))["people"]
    people = {p["id"]: p["name"] for p in members if p["confirmed"] and p["role"] in {"adult", "child"}}
    if surface and surface.get("person_id"):
        # Legacy screen profiles have no verified native Person link. Do not guess it
        # from names or let a personal wall acquire another member's explicit notes.
        settings = {"rules": [r for r in settings["rules"] if not r["people"]], "events": {}}
    result = {"revision": saved["revision"], "epoch": house["epoch"], "settings": settings, "people": people, "events": [], "zone": zone}
    items = classify(inventory, states, house["overrides"])
    policy = readiness.policy_for(saved, house, inventory, states)
    admitted_ids = None
    if surface:
        admitted_ids = {i["id"] for i in items if readiness.allowed(i, surface, house, policy) and admitted(i, surface, house, preferences(house, surface))}
    events, issues, expiries = [], [], []
    from zoneinfo import ZoneInfo

    local = now.astimezone(ZoneInfo(zone))
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    query = urlencode({"start": start.isoformat(), "end": (start + timedelta(days=22)).isoformat()})
    try:
        provider = waste.load(store, house)["confirmed"]
        provider_confirmed = bool(provider and (not surface or surface["id"] in provider["screens"]))
    except (ValueError, OSError, KeyError, TypeError):
        provider_confirmed = False
    for key in ("calendars", "waste"):
        if key == "waste" and provider_confirmed:
            continue  # Retain legacy choices, but never duplicate provider context as an event.
        choice = saved["choices"].get(key, {})
        if choice.get("intent") != "wanted" or not choice.get("sources"):
            if key == "calendars":
                issues.append("Household calendar not selected")
            continue
        if surface and surface["id"] not in choice.get("screens", []):
            if key == "calendars":
                issues.append("Calendar not selected for this display")
            continue
        if not inventory["complete"] or not readiness.proof_valid(saved, key, inventory, now):
            issues.append(("Calendar" if key == "calendars" else "Collection source") + " needs verification")
            continue
        source = choice["sources"][0]
        if source not in policy.get(key, []) or admitted_ids is not None and source not in admitted_ids:
            issues.append(("Calendar" if key == "calendars" else "Collection source") + " unavailable or excluded")
            continue
        try:
            raw = await core.rest_get("/calendars/" + source + "?" + query)
            if key == "waste" and isinstance(raw, list):
                raw = [e for e in raw if isinstance(e, dict) and readiness.collection_event(e, source, inventory)]
            parsed, invalid = context.parse_events(raw, readiness.selection_signature({"sources": [source]}, inventory), zone)
            # A selected collection source is already admitted by the existing verifier.
            events.extend(parsed)
            if invalid:
                issues.append("Some calendar entries could not be read")
            expiries.append(datetime.fromisoformat(saved["verified"][key]["at"]) + timedelta(days=1))
        except (CoreError, ValueError, KeyError, TypeError):
            issues.append(("Calendar" if key == "calendars" else "Collection source") + " temporarily unavailable")
    events = sorted({e["key"]: e for e in events}.values(), key=lambda e: e["start"].astimezone(UTC))
    content = context.build(events, now, zone, settings, people)
    # No old cached event is retained after a read failure. Accepted rules remain explicit.
    if issues:
        content["near"] = "\n\n".join(issues) + ("\n\n" + content["near"] if events or content["rule_count"] else "")
        if not events:
            content["ahead"] = (
                "Upcoming calendar context unavailable"
                if any("unavailable" in s or "verification" in s for s in issues)
                else "Choose and verify one consolidated calendar in Home Readiness"
            )
    result.update(content, issues=issues, checked_at=now.isoformat(), valid_until=min([now + timedelta(seconds=150), *expiries]).isoformat())
    try:
        bins = waste.view(waste.load(store, house), zone, now)
        if bins["configured"] and (not surface or surface["id"] in bins["screens"]):
            result["waste"] = bins
            if bins["summary"]:
                result["near"] = bins["summary"] + "\n\n" + result["near"]
    except (ValueError, OSError, KeyError, TypeError):
        result["issues"].append("Bin schedule needs checking")
    result["events"] = [
        {"key": e["key"], "title": e["title"], "start": e["start"].isoformat(), "all_day": e["all_day"], "proximity": context.proximity(e, now)}
        for e in events
        if context.proximity(e, now) != "elapsed"
    ]
    return result


async def update(core, store):
    house = store.load()
    records = store.read(store.publication_path, {})
    targets = [
        s
        for s in house["surfaces"]
        if s["profile"] == "wall"
        and records.get("home-starter-" + s["id"].replace("_", "-"), {}).get("context") == 1
        and records["home-starter-" + s["id"].replace("_", "-")].get("context_epoch") == house["epoch"]
    ]
    if not targets:
        return
    states = {s["entity_id"]: s for s in await core.states()}
    for surface in targets:
        entity = context.entity_id(surface["id"])
        old = states.get(entity)
        owner = {"surface": surface["id"], "epoch": house["epoch"]}
        previous_owner = (old.get("attributes") or {}).get("home_starter_context") if old else None
        if old and (
            not isinstance(previous_owner, dict)
            or previous_owner.get("surface") != surface["id"]
            or type(previous_owner.get("epoch")) is not int
            or previous_owner["epoch"] > house["epoch"]
        ):
            raise CoreError("api", "Context entity address is already owned by another source.")
        path = "home-starter-" + surface["id"].replace("_", "-")
        async with core.websocket() as ws:
            live = await ws.command("lovelace/config", url_path=path, force=True)
        if fingerprint(live) != records[path]["fingerprint"]:
            # Do not republish an externally edited dashboard, or send it new data.
            continue
        view = await inspect(core, store, surface)
        attributes = {k: view[k] for k in ("near", "ahead", "phase", "today_count", "ahead_count", "checked_at", "valid_until")}
        attributes.update(home_starter_context=owner, friendly_name="Household context")
        current = store.load()
        if current != house or readiness.load(store, current)["revision"] != view["revision"]:
            continue  # A concurrent opt-out/reset/save must not receive the older read.
        await core.context_state(entity, {"state": "attention" if view["issues"] else "current", "attributes": attributes})
