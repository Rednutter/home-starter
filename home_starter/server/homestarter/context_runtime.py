"""Read selected native sources; opt-in wall projections use owned ephemeral HA states."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from . import context, household_services, readiness, this_house, waste
from .core import CoreError
from .inventory import collect_inventory
from .surfaces import admitted, classify, fingerprint, preferences


async def snapshot(core, store):
    house = store.load()
    saved = readiness.load(store, house)
    inventory = await collect_inventory(core)
    states = await core.states()
    zone = (await core.config())["time_zone"]
    members = (await this_house.inspect(core, store))["people"]
    return house, saved, inventory, states, zone, members


def wall_cameras(saved, house, surface, inventory, states, now):
    if not inventory["complete"]:
        return []
    choice = saved["choices"].get("cameras", {})
    if choice.get("intent") != "wanted" or surface["id"] not in choice.get("screens", []) or not readiness.proof_valid(saved, "cameras", inventory, now):
        return []
    hidden = preferences(house, surface)["hide"]
    excluded = set(saved["devices"])
    candidates = {e["entity_id"] for e in readiness.entities(inventory) if e.get("device_id") not in excluded}
    available = {s["entity_id"] for s in states if s.get("state") not in ("unknown", "unavailable")}
    return [e for e in choice["sources"] if e.startswith("camera.") and e in candidates & available and e not in hidden]


async def inspect(core, store, surface=None, now=None, *, person_id=None, inputs=None, display_session=None):
    now = now or datetime.now(UTC)
    house, saved, inventory, states, zone, members = inputs or await snapshot(core, store)
    settings = saved["context"]
    service_map = household_services.load(store, house)
    calendars = {row["entity_id"]: row for row in service_map["calendars"]}
    people = {p["id"]: p["name"] for p in members if p["confirmed"] and p["role"] in {"adult", "child"}}
    policy = readiness.policy_for(saved, house, inventory, states)
    linked_person = None
    if person_id is not None:
        member = saved["members"].get(person_id, {})
        # Explicit native Person source links, never matching names or a room.
        linked = set(member.get("presence", [])) & set(policy.get("presence", []))
        ids = {s.get("attributes", {}).get("id") for s in states if s["entity_id"] in linked and s["entity_id"].startswith("person.")}
        confirmed = {p["id"] for p in members if p["confirmed"] and p["role"] == member.get("kind")}
        candidates = ids & confirmed if person_id in {p["id"] for p in house["people"]} else set()
        linked_person = next(iter(candidates)) if len(candidates) == 1 and (not surface or surface["id"] in policy.get("presence_screens", [])) else None
        settings = {
            "rules": [r for r in settings["rules"] if linked_person and linked_person in r["people"]],
            "events": {k: v for k, v in settings["events"].items() if linked_person and linked_person in v["people"]},
        }
    elif surface and surface.get("person_id"):
        # Legacy screen profiles have no verified native Person link. Do not guess it
        # from names or let a personal wall acquire another member's explicit notes.
        settings = {"rules": [r for r in settings["rules"] if not r["people"]], "events": {}}
    result = {"revision": saved["revision"], "epoch": house["epoch"], "settings": settings, "people": people, "events": [], "zone": zone}
    from .wall_composer import validate_policy

    result["wall_policy"] = validate_policy(settings.get("wall", {}))
    candidates = readiness.discover(inventory, states)["cameras"]
    result["wall_camera_sources"] = [s for s in candidates if s["id"] in policy.get("cameras", []) and s["id"].startswith("camera.")]
    result["wall_doorbell_sources"] = [s for s in candidates if s["id"] in policy.get("cameras", []) and s["id"].startswith("event.")]
    items = classify(inventory, states, house["overrides"])
    admitted_ids = None
    if surface:
        scoped = {**surface, "person_id": person_id} if person_id is not None else surface
        if person_id is not None and saved["members"].get(person_id, {}).get("kind") == "child":
            scoped = {**scoped, "audience": "everyone"}
        admitted_ids = {i["id"] for i in items if readiness.allowed(i, scoped, house, policy) and admitted(i, scoped, house, preferences(house, scoped))}
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
        for source in choice["sources"]:
            if source not in policy.get(key, []) or admitted_ids is not None and source not in admitted_ids:
                issues.append(("Calendar" if key == "calendars" else "Collection source") + " unavailable or excluded")
                continue
            try:
                raw = await core.rest_get("/calendars/" + source + "?" + query)
                if key == "waste" and isinstance(raw, list):
                    raw = [e for e in raw if isinstance(e, dict) and readiness.collection_event(e, source, inventory)]
                parsed, invalid = context.parse_events(raw, readiness.selection_signature({"sources": [source]}, inventory), zone)
                mapped = bool(linked_person and person_id in calendars.get(source, {}).get("people", []))
                events.extend(e for e in parsed if person_id is None or mapped or e["key"] in settings["events"])
                if invalid:
                    issues.append("Some calendar entries could not be read")
                expiries.append(datetime.fromisoformat(saved["verified"][key]["at"]) + timedelta(days=1))
            except (CoreError, ValueError, KeyError, TypeError):
                issues.append(("Calendar" if key == "calendars" else "Collection source") + " temporarily unavailable")
    # Keep source-specific event keys for existing annotations; deduplicate overlapping upstream feeds.
    unique = {}
    for e in events:
        duplicate = (" ".join(e["title"].casefold().split()), e["start"].astimezone(UTC), e["end"].astimezone(UTC), e["all_day"])
        unique.setdefault(duplicate, e)
    events = sorted(unique.values(), key=lambda e: e["start"].astimezone(UTC))
    briefing_limit = 20 if surface and surface["profile"] == "wall" else 7
    content = context.build(events, now, zone, settings, people, briefing_limit=briefing_limit)
    if person_id is not None and not linked_person:
        issues.append("Personal context not linked")
    # No old cached event is retained after a read failure. Accepted rules remain explicit.
    if issues:
        content["near"] = "\n\n".join(issues) + ("\n\n" + content["near"] if events or content["rule_count"] else "")
        if not events:
            content["ahead"] = (
                "Upcoming calendar context unavailable"
                if any("unavailable" in s or "verification" in s for s in issues)
                else "Choose and verify calendars from your consolidated account in Home Readiness"
            )
    result.update(content, issues=issues, checked_at=now.isoformat(), valid_until=min([now + timedelta(seconds=150), *expiries]).isoformat())
    try:
        bins = waste.view(waste.load(store, house), zone, now)
        if person_id is None and bins["configured"] and (not surface or surface["id"] in bins["screens"]):
            result["waste"] = bins
            if bins["summary"]:
                result["near"] = bins["summary"] + "\n\n" + result["near"]
                if bins.get("attention") != "quiet":
                    rows = result["briefing"]
                    index = next((n for n, row in enumerate(rows) if row.get("priority", 2) >= 2), len(rows))
                    rows.insert(index, {"id": "bins", "title": bins["summary"], "when": "Household collection", "detail": "", "proximity": "now"})
                    result["briefing"] = rows[:briefing_limit]
    except (ValueError, OSError, KeyError, TypeError):
        result["issues"].append("Bin schedule needs checking")
    if surface and surface["profile"] == "wall":
        from .wall_composer import compose

        signals = [{**i, **next((s for s in states if s["entity_id"] == i["entity_id"]), {})} for i in items if i["id"] in admitted_ids]
        cameras = wall_cameras(saved, house, surface, inventory, states, now)
        signals.extend({**s, "domain": "camera"} for s in states if s["entity_id"] in cameras)
        result["wall"] = compose(result, events, settings, people, now, zone, signals, display_session)
    result["events"] = [
        {"key": e["key"], "title": e["title"], "start": e["start"].isoformat(), "all_day": e["all_day"], "proximity": context.proximity(e, now)}
        for e in events
        if context.proximity(e, now) != "elapsed"
    ]
    return result


async def update(core, store, sessions=None):
    house = store.load()
    records = store.read(store.publication_path, {})
    targets = [
        s
        for s in house["surfaces"]
        if s["profile"] in ("wall", "specialist")
        and records.get("home-starter-" + s["id"].replace("_", "-"), {}).get("context") in (1, 2)
        and records["home-starter-" + s["id"].replace("_", "-")].get("context_epoch") == house["epoch"]
    ]
    if not targets:
        return
    inputs = await snapshot(core, store)
    states = {s["entity_id"]: s for s in await core.states()}
    for surface in targets:
        if sessions is not None and surface["id"] in sessions:
            from .wall_composer import moment

            pending = sessions[surface["id"]]
            expiry = moment(pending.get("content", {}).get("expires_at"))
            if pending.get("epoch") != house["epoch"] or not expiry or expiry <= datetime.now(UTC):
                sessions.pop(surface["id"], None)
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
        pending = (sessions or {}).get(surface["id"], {})
        active = pending.get("content") if pending.get("epoch") == house["epoch"] else None
        view = await inspect(core, store, surface, inputs=inputs, display_session=active)
        attributes = {k: view[k] for k in ("near", "ahead", "phase", "today_count", "ahead_count", "checked_at", "valid_until")}
        if records[path].get("context") == 2:
            attributes["briefing"] = view["briefing"]
            if "wall" in view:
                attributes["wall"] = view["wall"]
        attributes.update(home_starter_context=owner, friendly_name="Household context")
        current = store.load()
        if current != house or readiness.load(store, current)["revision"] != view["revision"]:
            continue  # A concurrent opt-out/reset/save must not receive the older read.
        await core.context_state(entity, {"state": "attention" if view["issues"] else "current", "attributes": attributes})
        if records[path].get("context") == 2:
            for person in house["people"]:
                personal_entity = context.entity_id(surface["id"], person["id"])
                previous = states.get(personal_entity)
                personal_owner = {**owner, "person_id": person["id"]}
                previous_owner = previous.get("attributes", {}).get("home_starter_context") if previous else None
                if previous and (
                    not isinstance(previous_owner, dict)
                    or previous_owner.get("surface") != surface["id"]
                    or previous_owner.get("person_id") != person["id"]
                    or type(previous_owner.get("epoch")) is not int
                    or previous_owner["epoch"] > house["epoch"]
                ):
                    raise CoreError("api", "Personal context address is already owned by another source.")
                personal = await inspect(core, store, surface, person_id=person["id"], inputs=inputs)
                if store.load() != house or readiness.load(store, house)["revision"] != personal["revision"]:
                    break
                await core.context_state(
                    personal_entity,
                    {
                        "state": "attention" if personal["issues"] else "current",
                        "attributes": {
                            "home_starter_context": personal_owner,
                            "friendly_name": "Personal household context",
                            "briefing": personal["briefing"],
                            "checked_at": personal["checked_at"],
                            "valid_until": personal["valid_until"],
                        },
                    },
                )
