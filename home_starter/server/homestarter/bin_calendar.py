"""Owned HA Local Calendar projection of confirmed Council collection dates.

Only journalled entries/UIDs can be updated. Uncertain writes are read back before
retry; external edits and unrelated calendars are preserved.
"""

import asyncio
from datetime import date, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import waste


def path(store):
    return store.path.parent / "bin-calendar.json"


def load(store, house):
    value = store.read(path(store), None)
    if value is not None and (value.get("version") != 1 or value.get("epoch") != house["epoch"]):
        raise ValueError("Bin calendar ownership needs review; existing calendar preserved.")
    return value


def desired(value, zone, now):
    status = waste.view(value, zone, now)
    if status["status"] not in ("current", "last_known_valid"):
        return {}
    today = now.astimezone(ZoneInfo(zone)).date()
    labels = {s["id"]: s["label"] for s in value["confirmed"]["services"]}
    result = {}
    for annual in value["schedules"]:
        for day, types in annual["dates"].items():
            at = date.fromisoformat(day)
            if at.weekday() != value["confirmed"]["day"] or not today <= at <= today + timedelta(days=42):
                continue
            result[day] = {
                "start": day,
                "end": (at + timedelta(days=1)).isoformat(),
                "summary": " + ".join(labels[t] for t in types),
                "description": "Home Starter Council collection / " + day,
            }
    return dict(sorted(result.items()))


async def native(core):
    async with core.websocket() as ws:
        entries = await ws.command("config_entries/get", domain="local_calendar")
        registry = await ws.command("config/entity_registry/list")
    return entries, registry


async def check(core, record):
    entries, registry = await native(core)
    matches = [e for e in entries if e["entry_id"] == record["entry_id"]]
    if len(matches) != 1 or matches[0].get("title") != record["title"] or matches[0].get("state") != "loaded":
        raise ValueError("Owned bin calendar changed or unavailable; existing entries preserved.")
    entities = [e for e in registry if e.get("config_entry_id") == record["entry_id"] and e["entity_id"].startswith("calendar.")]
    if len(entities) != 1 or entities[0].get("disabled_by") or entities[0]["entity_id"] != record["entity"]:
        raise ValueError("Owned bin calendar entity changed; review required.")


async def read(core, entity, start, end):
    query = urlencode({"start": start, "end": end})
    rows = await core.rest_get("/calendars/" + entity + "?" + query)
    if not isinstance(rows, list):
        raise ValueError("Native bin calendar could not be read.")
    return rows


def matches(row, event):
    return (
        row.get("start") == {"date": event["start"]}
        and row.get("end") == {"date": event["end"]}
        and row.get("summary") == event["summary"]
        and row.get("description") == event["description"]
    )


def wire_event(event):
    # HA websocket RFC5545 fields differ from its REST readback representation.
    return {"dtstart": event["start"], "dtend": event["end"], "summary": event["summary"], "description": event["description"]}


async def reconcile(core, store, house, now):
    if not hasattr(core, "_bin_calendar_lock"):
        core._bin_calendar_lock = asyncio.Lock()
    async with core._bin_calendar_lock:
        zone = (await core.config())["time_zone"]
        wanted = desired(waste.load(store, house), zone, now)
        if not wanted:
            return
        record = load(store, house)
        if record is None:
            entries, _ = await native(core)
            title = "Home Starter Bins"
            if any(e.get("title") == title for e in entries):
                raise ValueError("An unowned Home Starter Bins calendar exists; review before creating another.")
            record = {"version": 1, "epoch": house["epoch"], "entry_id": None, "entity": None, "title": title, "events": {}}
            store.write(path(store), record)
            flow = await core.local_calendar_flow({})
            if flow.get("type") != "form" or flow.get("step_id") != "user":
                raise ValueError("Native Local Calendar setup needs attention.")
            created = await core.local_calendar_flow({"calendar_name": title}, flow["flow_id"])
            if created.get("type") != "create_entry" or not created.get("result", {}).get("entry_id"):
                raise ValueError("Native bin calendar creation is uncertain; inspect before retry.")
            record["entry_id"] = created["result"]["entry_id"]
            store.write(path(store), record)
        if record["entry_id"] is None:
            raise ValueError("Previous bin calendar creation is uncertain; inspect before retry.")
        if record["entity"] is None:
            _, registry = await native(core)
            entities = [e for e in registry if e.get("config_entry_id") == record["entry_id"] and e["entity_id"].startswith("calendar.")]
            if len(entities) != 1:
                raise ValueError("Native bin calendar is preparing.")
            record["entity"] = entities[0]["entity_id"]
            store.write(path(store), record)
        await check(core, record)
        first, last = min(wanted), (date.fromisoformat(max(wanted)) + timedelta(days=1)).isoformat()
        rows = await read(core, record["entity"], first + "T00:00:00", last + "T00:00:00")
        for day, event in wanted.items():
            if store.load() != house:
                return
            saved = record["events"].get(day)
            if saved:
                found = (
                    [r for r in rows if r.get("uid") == saved.get("uid")]
                    if saved.get("uid")
                    else [r for r in rows if r.get("description") == saved["event"]["description"]]
                )
                if len(found) != 1:
                    raise ValueError("Bin event write is uncertain or event was removed; review before retry.")
                row = found[0]
                if saved.get("pending") and matches(row, saved["pending"]):
                    saved["event"] = saved.pop("pending")
                    store.write(path(store), record)
                if not matches(row, saved["event"]):
                    raise ValueError("A bin event was edited outside Home Starter; existing event preserved.")
                saved["uid"] = row["uid"]
                if saved["event"] != event:
                    saved["pending"] = event
                    store.write(path(store), record)
                    async with core.websocket() as ws:
                        await ws.command("calendar/event/update", entity_id=record["entity"], uid=saved["uid"], event=wire_event(event))
                    saved["event"] = event
                    saved.pop("pending", None)
            else:
                if any(r.get("start") == {"date": day} for r in rows):
                    raise ValueError("An unowned collection event occupies this date; preserved for review.")
                saved = {"uid": None, "event": event}
                record["events"][day] = saved
                store.write(path(store), record)
                async with core.websocket() as ws:
                    await ws.command("calendar/event/create", entity_id=record["entity"], event=wire_event(event))
            rows = await read(core, record["entity"], first + "T00:00:00", last + "T00:00:00")
            verified = [r for r in rows if matches(r, event) and r.get("uid")]
            if len(verified) != 1:
                raise ValueError("Bin event readback failed; inspect before retry.")
            saved["uid"] = verified[0]["uid"]
            store.write(path(store), record)
        return record


async def wall_rows(core, store, house, zone, now):
    """Native readback only; no cached event or prior-evening phantom event."""
    record = load(store, house)
    if not record:
        return []
    if not record.get("entity"):
        raise ValueError("Native bin calendar is preparing or needs attention.")
    await check(core, record)
    value = waste.load(store, house)
    wanted = desired(value, zone, now)
    if not wanted:
        return []
    rows = await read(core, record["entity"], min(wanted) + "T00:00:00", (date.fromisoformat(max(wanted)) + timedelta(days=1)).isoformat() + "T00:00:00")
    result = []
    dates = {day: types for annual in value["schedules"] for day, types in annual["dates"].items()}
    from datetime import datetime, time

    local = now.astimezone(ZoneInfo(zone))
    for day, event in wanted.items():
        saved = record["events"].get(day)
        if not saved or len([r for r in rows if r.get("uid") == saved["uid"] and matches(r, event)]) != 1:
            continue
        at = date.fromisoformat(day)
        if at == local.date() and local.hour >= 12:
            continue
        title = "Bins today" if at == local.date() else "Bins out tonight" if at == local.date() + timedelta(days=1) and local.hour >= 18 else "Bin collection"
        start = datetime.combine(at, time(), local.tzinfo)
        result.append(
            {
                "id": "bins-" + saved["uid"],
                "title": title,
                "date": day,
                "starts_at": start.isoformat(),
                "ends_at": (start + timedelta(days=1)).isoformat(),
                "time": "All day",
                "day_offset": (at - local.date()).days,
                "day_label": at.strftime("%A") if (at - local.date()).days <= 7 else at.strftime("%a %d %b"),
                "detail": event["summary"],
                "bin_types": dates[day],
                "people": [],
                "person_ids": [],
            }
        )
    return result
