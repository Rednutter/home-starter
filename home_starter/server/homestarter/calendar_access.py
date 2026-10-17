"""Calendar visibility is a local consent decision, independent of Google authentication."""

from .household_services import path
from .music_runtime import private_write

MODES = {"show", "context", "ignore", "review"}


def suggestion(name):
    import re

    if re.search(r"\b(bin|waste|collection|ics)\b", name, re.I):
        return "ignore", "Collection dates already have a dedicated household service."
    if re.search(r"\b(family|holidays?|birthdays?|schools?|girls|boys|sports?|heja)\b", name, re.I):
        return "show", "Likely a shared household calendar; confirm before showing."
    return "context", "Keep private context available without showing events at home."


def load(store, house):
    value = store.read(path(store, "calendar-access.json"), None)
    if value is not None and (
        not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1 or type(value.get("epoch")) is not int
    ):
        raise ValueError("Unsupported calendar choices. Existing choices are preserved.")
    if value is None or isinstance(value, dict) and value.get("epoch") != house["epoch"]:
        value = {"version": 1, "epoch": house["epoch"], "revision": 0, "calendars": {}}
        # Preserve calendars previously explicitly selected for household display.
        # This is a one-time migration, never a rule for future discovery.
        previous = store.read(store.readiness_path, {})
        if previous.get("epoch") == house["epoch"]:
            choice = previous.get("choices", {}).get("calendars", {})
            if choice.get("intent") == "wanted":
                value["calendars"] = {s: "show" for s in choice.get("sources", []) if valid_id(s)}
        if value["calendars"]:
            private_write(path(store, "calendar-access.json"), value)
        return value
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "epoch", "revision", "calendars"}
        or value["version"] != 1
        or type(value["revision"]) is not int
        or not isinstance(value["calendars"], dict)
        or any(not valid_id(k) or v not in MODES for k, v in value["calendars"].items())
    ):
        raise ValueError("Calendar choices need checking. Existing choices are preserved.")
    return value


def valid_id(value):
    import re

    return isinstance(value, str) and re.fullmatch(r"calendar\.[a-z0-9_]+", value)


def discover(store, house, states):
    value = load(store, house)
    if not path(store, "calendar-access.json").exists():
        # Freeze the one-time legacy migration before any subsequent discovery
        # or readiness editor can accidentally promote a new source.
        private_write(path(store, "calendar-access.json"), value)
    rows = [
        {
            "id": s["entity_id"],
            "name": s.get("attributes", {}).get("friendly_name") or "Calendar",
            "mode": value["calendars"].get(s["entity_id"], "review"),
            "available": s.get("state") not in {"unknown", "unavailable"},
            "suggested": suggestion(s.get("attributes", {}).get("friendly_name", ""))[0],
            "reason": suggestion(s.get("attributes", {}).get("friendly_name", ""))[1],
        }
        for s in states
        if valid_id(s.get("entity_id"))
    ]
    counts = {mode: sum(r["mode"] == mode for r in rows) for mode in MODES}
    return {**value, "rows": rows, "counts": counts, "state": "needs_review" if counts["review"] else "connected" if rows else "not_detected"}


def save(store, house, states, body):
    current = load(store, house)
    if not isinstance(body, dict) or set(body) != set(current) or any(body[k] != current[k] for k in ("version", "epoch", "revision")):
        raise ValueError("Calendar choices changed. Reload before saving.")
    modes = body["calendars"]
    known = set(current["calendars"]) | {s["entity_id"] for s in states if valid_id(s.get("entity_id"))}
    if not isinstance(modes, dict) or any(k not in known or v not in MODES for k, v in modes.items()):
        raise ValueError("Choose Show at home, Use for context or Ignore for discovered calendars.")
    # Partial updates retain choices for temporarily missing calendars.
    value = {**current, "calendars": {**current["calendars"], **modes}}
    if value != current:
        value["revision"] += 1
        private_write(path(store, "calendar-access.json"), value)
    return discover(store, house, states)


def permitted(choices, source, *, context=False, person=None, mappings=()):
    mode = choices.get(source, "review")
    if mode == "show":
        return True
    if mode != "context":
        return False
    return context or bool(person and any(r["entity_id"] == source and person in r["people"] for r in mappings))


def filter_native_cards(value, allowed):
    """Remove denied native calendar content without regenerating other controls."""
    import re

    if isinstance(value, list):
        return [filtered for item in value if (filtered := filter_native_cards(item, allowed)) is not None]
    if not isinstance(value, dict):
        return value
    kind = value.get("type", "")
    entity = value.get("entity")
    if valid_id(entity) and entity not in allowed and kind in {"entity", "tile", "button", "conditional", "markdown"}:
        return None
    if kind == "markdown":
        references = set(re.findall(r"calendar\.[a-z0-9_]+", str(value.get("content", ""))))
        if references - allowed:
            return None
    result = {k: filter_native_cards(v, allowed) for k, v in value.items()}
    if kind == "conditional" and result.get("card") is None:
        return None
    if kind in {"calendar", "entities", "glance"} and isinstance(result.get("entities"), list):
        result["entities"] = [
            row for row in result["entities"] if not valid_id(source := row.get("entity") if isinstance(row, dict) else row) or source in allowed
        ]
        if not result["entities"]:
            return None
    return result


async def refresh_publications(core, store, house, inventory, states):
    """Update only native calendar cards on unmodified owned dashboards."""
    import copy
    import json
    import re

    from . import household_services, readiness
    from .core import CoreError
    from .surfaces import fingerprint

    access = load(store, house)["calendars"]
    mappings = household_services.load(store, house)["calendars"]
    policy = readiness.policy_for(readiness.load(store, house), house, inventory, states, store)
    records = store.read(store.publication_path, {})
    by_id = {s["entity_id"]: s for s in states if valid_id(s.get("entity_id"))}
    issues = []
    async with core.websocket() as ws:
        for surface in house["surfaces"]:
            url = "home-starter-" + surface["id"].replace("_", "-")
            record = records.get(url)
            if not record:
                continue
            try:
                current = await ws.command("lovelace/config", url_path=url, force=True)
                if fingerprint(current) != record.get("fingerprint"):
                    issues.append(surface["name"] + ": existing dashboard edits require review")
                    continue
                updated = copy.deepcopy(current)
                for view in updated.get("views", []):
                    person = surface.get("person_id")
                    view_path = view.get("path", "")
                    root = view_path == "home"
                    for member in house["people"]:
                        prefix = "person-" + member["id"].encode().hex()
                        if view_path == prefix or view_path.startswith(prefix + "-"):
                            person = member["id"]
                            root = view_path == prefix
                            break
                    allowed = {
                        source
                        for source in by_id
                        if permitted(access, source, person=person, mappings=mappings)
                        and any(source in policy.get(key, []) and surface["id"] in policy.get(key + "_screens", []) for key in ("calendars", "waste"))
                    }
                    filtered = filter_native_cards(view, allowed)
                    view.clear()
                    view.update(filtered or {})
                    # The custom touch/wall shell uses live context projections.
                    # Never rewrite its templates or replace climate/navigation.
                    custom = "custom:button-card" in json.dumps(view)
                    if root and not custom and view.get("type") == "sections":
                        present = set(re.findall(r"calendar\.[a-z0-9_]+", json.dumps(view)))
                        cards = [
                            {
                                "type": "calendar",
                                "entities": [source],
                                "initial_view": "listWeek",
                                "title": by_id[source].get("attributes", {}).get("friendly_name") or "Calendar",
                            }
                            for source in sorted(allowed)
                            if source not in present
                        ]
                        if cards:
                            today = next((s for s in view.get("sections", []) if any(c.get("heading") == "Today" for c in s.get("cards", []))), None)
                            if today:
                                today["cards"].extend(cards)
                            else:
                                view.setdefault("sections", []).append({"type": "grid", "cards": [{"type": "heading", "heading": "Today"}, *cards]})
                if updated == current:
                    continue
                await ws.command("lovelace/config/save", url_path=url, config=updated)
                readback = await ws.command("lovelace/config", url_path=url, force=True)
                if readback != updated:
                    issues.append(surface["name"] + ": dashboard readback needs attention")
                    continue
                records[url] = {**record, "fingerprint": fingerprint(readback)}
                store.write(store.publication_path, records)
            except (CoreError, ValueError, KeyError, TypeError):
                issues.append(surface["name"] + ": calendar screen update needs attention")
    return issues
