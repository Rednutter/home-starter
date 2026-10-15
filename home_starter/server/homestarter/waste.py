"""Household waste intent, bounded source cache and time-local relevance.

HA remains the location source. No addresses, coordinates, events or secrets stored.
"""

import asyncio
import calendar
import copy
import re
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .core import CoreError
from .household import ID
from .wodonga import ARCGIS, FAQ, SourceError

SOURCE_ENTITY = "sensor.home_starter_bin_source"


def empty(house):
    return {
        "version": 1,
        "epoch": house["epoch"],
        "revision": 0,
        "confirmed": None,
        "schedules": [],
        "checked_at": None,
        "verified_at": None,
        "error": None,
        "helpers": {},
    }


def path(store):
    return store.path.parent / "waste-collection.json"


def screen_policy(policy, confirmed):
    """Replace legacy bin presentation only on explicitly selected provider screens."""
    result = copy.deepcopy(policy)
    screens = (confirmed or {}).get("screens", [])
    result["bin_context_screens"] = list(screens)
    if "waste_screens" in result:
        result["waste_screens"] = [s for s in result["waste_screens"] if s not in screens]
    return result


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Waste evidence requires an aware timestamp.")
    return result.astimezone(UTC)


def validate_annual(row):
    if not isinstance(row, dict) or set(row) != {"year", "valid_from", "valid_to", "dates", "source_type", "source_id", "version"}:
        raise ValueError("Unsupported annual waste schedule.")
    year = row["year"]
    if type(year) is not int or not 2000 <= year <= 2100 or row["valid_from"] != f"{year}-01-01" or row["valid_to"] != f"{year}-12-31":
        raise ValueError("Invalid annual waste validity period.")
    from .wodonga import safe_url

    safe_url(row["source_id"])
    if row["source_type"] != "annual_calendar" or not re.fullmatch(r"[a-f0-9]{64}", row["version"]):
        raise ValueError("Invalid annual waste provenance.")
    expected = {date(year, m, d).isoformat() for m in range(1, 13) for d in range(1, calendar.monthrange(year, m)[1] + 1) if date(year, m, d).weekday() < 5}
    if (
        not isinstance(row["dates"], dict)
        or set(row["dates"]) != expected
        or any(
            not isinstance(types, list)
            or not 1 <= len(types) <= 12
            or any(not isinstance(t, str) or not ID.fullmatch(t) for t in types)
            or len(set(types)) != len(types)
            for types in row["dates"].values()
        )
    ):
        raise ValueError("Waste calendar is incomplete.")


def load(store, house):
    value = store.read(path(store), None)
    if value is None:
        return empty(house)
    if not isinstance(value, dict) or set(value) != set(empty(house)) or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Unsupported waste data; existing files preserved.")
    if any(type(value[k]) is not int or value[k] < 0 for k in ("epoch", "revision")) or value["epoch"] > house["epoch"]:
        raise ValueError("Waste data has an unsupported epoch/revision.")
    if value["epoch"] < house["epoch"]:
        return empty(house)
    if value["confirmed"] is not None:
        c = value["confirmed"]
        if (
            not isinstance(c, dict)
            or set(c) != {"provider", "day", "zone", "location_source", "map_version", "screens", "services"}
            or c["provider"] != "wodonga"
            or type(c["day"]) is not int
            or not 0 <= c["day"] < 5
        ):
            raise ValueError("Invalid waste service intent.")
        services = c["services"]
        if (
            not isinstance(services, list)
            or not 1 <= len(services) <= 12
            or any(
                not isinstance(s, dict)
                or set(s) != {"id", "label", "cadence"}
                or not isinstance(s["id"], str)
                or not ID.fullmatch(s["id"])
                or not isinstance(s["label"], str)
                or not 0 < len(s["label"]) <= 60
                or any(ord(ch) < 32 for ch in s["label"])
                or s["cadence"] not in {"weekly", "fortnightly", "provider_schedule"}
                for s in services
            )
            or len({s["id"] for s in services}) != len(services)
        ):
            raise ValueError("Invalid waste services.")
        if (
            c["location_source"] not in {"arcgis", "owner"}
            or not isinstance(c["zone"], str)
            or len(c["zone"]) > 80
            or not isinstance(c["map_version"], str)
            or len(c["map_version"]) > 80
        ):
            raise ValueError("Invalid collection-area evidence.")
        if (
            not isinstance(c["screens"], list)
            or len(c["screens"]) > 50
            or len(set(c["screens"])) != len(c["screens"])
            or any(not ID.fullmatch(s) for s in c["screens"])
        ):
            raise ValueError("Invalid waste display choices.")
    if not isinstance(value["schedules"], list) or len(value["schedules"]) > 3:
        raise ValueError("Invalid annual schedule cache.")
    for row in value["schedules"]:
        validate_annual(row)
        if value["confirmed"] and any(not set(types) <= {s["id"] for s in value["confirmed"]["services"]} for types in row["dates"].values()):
            raise ValueError("Annual schedule contains an unknown service.")
    if len({r["year"] for r in value["schedules"]}) != len(value["schedules"]):
        raise ValueError("Conflicting annual waste schedules.")
    for key in ("checked_at", "verified_at"):
        if value[key] is not None:
            timestamp(value[key])
    if value["error"] is not None and (
        not isinstance(value["error"], dict)
        or set(value["error"]) != {"kind", "message"}
        or value["error"]["kind"] not in {"unavailable", "changed", "location"}
        or not isinstance(value["error"]["message"], str)
        or len(value["error"]["message"]) > 300
    ):
        raise ValueError("Invalid waste failure evidence.")
    if not isinstance(value["helpers"], dict) or len(value["helpers"]) > 6:
        raise ValueError("Invalid waste entity ownership.")
    for key, item in value["helpers"].items():
        if (
            not re.fullmatch(r"(?:sensor|binary_sensor)\.home_starter_[a-z_]+", key)
            or not isinstance(item, dict)
            or set(item) != {"entry_id", "flow_id", "signature"}
            or any(v is not None and (not isinstance(v, str) or not 0 < len(v) <= 100) for v in item.values())
        ):
            raise ValueError("Invalid waste helper ownership.")
    return value


def save(store, value):
    value["revision"] += 1
    store.write(path(store), value)


async def candidate(provider, core, manual_day=None, now=None):
    now = now or datetime.now(UTC)
    config = await core.config()
    if manual_day is None:
        location = await provider.location(config)
    elif type(manual_day) is int and 0 <= manual_day < 5:
        location = {"day": manual_day, "zone": "Owner-confirmed day", "location_source": "owner", "map_version": ""}
    else:
        raise ValueError("Choose a weekday collection day.")
    schedules = await provider.fetch(now.astimezone(ZoneInfo(config["time_zone"])).year)
    for row in schedules:
        validate_annual(row)
    if not any(r["year"] == now.astimezone(ZoneInfo(config["time_zone"])).year for r in schedules):
        raise SourceError("The current annual schedule is not available.")
    return {
        "confirmed": {"provider": provider.id, **location, "screens": [], "services": copy.deepcopy(provider.services)},
        "schedules": schedules,
        "checked_at": now.isoformat(),
        "verified_at": now.isoformat(),
        "error": None,
    }


async def refresh(provider, core, store, house, now=None):
    now = now or datetime.now(UTC)
    value = load(store, house)
    if not value["confirmed"]:
        return value
    current = value["confirmed"]
    try:
        async with asyncio.timeout(50):
            new = await candidate(provider, core, current["day"] if current["location_source"] == "owner" else None, now)
        if any(new["confirmed"][k] != current[k] for k in ("day", "zone", "location_source")):
            raise SourceError("Collection area/day changed; review the proposed service again.", "location")
        # A changed past/current printed date is a conflict, not a silent correction.
        old_dates = {k: t for r in value["schedules"] for k, t in r["dates"].items()}
        if any(k in old_dates and old_dates[k] != t for r in new["schedules"] for k, t in r["dates"].items()):
            raise SourceError("Council changed the dated collection pattern; confirm the revised schedule.")
        merged = {r["year"]: r for r in value["schedules"] if r["year"] >= now.year - 1}
        merged.update({r["year"]: r for r in new["schedules"]})
        value.update(schedules=[merged[y] for y in sorted(merged)[-3:]], checked_at=new["checked_at"], verified_at=new["verified_at"], error=None)
        value["confirmed"]["map_version"] = new["confirmed"]["map_version"]
    except (CoreError, TimeoutError, OSError):
        value["checked_at"] = now.isoformat()
        value["error"] = {"kind": "unavailable", "message": "Council refresh timed out or is unavailable; last verified schedule preserved."}
    except (SourceError, KeyError, TypeError, ValueError) as error:
        value["checked_at"] = now.isoformat()
        value["error"] = {
            "kind": getattr(error, "kind", "changed"),
            "message": str(error) if isinstance(error, SourceError) else "Council response was malformed; last verified schedule preserved.",
        }
    save(store, value)
    return value


def view(value, zone, now=None):
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(zone))
    c = value["confirmed"]
    result = {
        "revision": value["revision"],
        "epoch": value["epoch"],
        "configured": bool(c),
        "status": "unconfigured",
        "provider": "Wodonga Council",
        "day": calendar.day_name[c["day"]] if c else None,
        "screens": c["screens"] if c else [],
        "next": None,
        "following": None,
        "days_until": None,
        "bin_night": False,
        "attention": None,
        "title": None,
        "summary": "",
        "checked_at": value["checked_at"],
        "verified_at": value["verified_at"],
        "renewal_due": False,
        "message": "Choose and confirm a collection service.",
        "sources": [],
        "entities": list(value["helpers"]),
        "services": c["services"] if c else [],
    }
    if not c:
        return result
    result["sources"] = [
        {
            "type": "arcgis" if c["location_source"] == "arcgis" else "owner_confirmation",
            "id": ARCGIS if c["location_source"] == "arcgis" else "collection_day",
            "zone": c["zone"],
            "version": c["map_version"],
        },
        {"type": "council_policy", "id": FAQ, "public_holidays": "normal_collection"},
        *[{k: r[k] for k in ("source_type", "source_id", "year", "version", "valid_from", "valid_to")} for r in value["schedules"]],
    ]
    result["calculated"] = True
    error = value["error"]
    age = now - timestamp(value["verified_at"]) if value["verified_at"] else timedelta.max
    status = (
        "needs_checking"
        if error and error["kind"] != "unavailable"
        else "stale"
        if not timedelta(0) <= age <= timedelta(days=7)
        else "last_known_valid"
        if error
        else "current"
    )
    schedules = {r["year"]: r for r in value["schedules"]}
    today = local.date()
    delta = (c["day"] - today.weekday()) % 7
    if delta == 0 and local.hour >= 6:
        delta = 7
    next_date = today + timedelta(days=delta)
    annual = schedules.get(next_date.year)
    if not annual or next_date.isoformat() not in annual["dates"]:
        status = "stale"
    result["status"] = status
    result["renewal_due"] = not schedules.get(today.year + 1) and (date(today.year, 12, 31) - today).days <= 45
    if status in {"needs_checking", "stale", "unavailable"}:
        result.update(
            attention="needs_checking",
            title="Bin schedule needs checking",
            summary="Bin schedule needs checking",
            message=(error or {}).get("message") or "Annual schedule expired or verification is older than seven days. Last verified data is preserved.",
        )
        return result

    def collection(d):
        row = schedules.get(d.year)
        return {"date": d.isoformat(), "types": row["dates"][d.isoformat()]} if row and d.isoformat() in row["dates"] else None

    result.update(
        next=collection(next_date),
        following=collection(next_date + timedelta(days=7)),
        days_until=delta,
        message=(
            "Last verified schedule available, currently not refreshable."
            if error
            else "Owner-confirmed collection day and official annual schedule verified."
            if c["location_source"] == "owner"
            else "Official collection day and annual schedule verified."
        ),
    )
    if delta == 1 and local.hour >= 18:
        result.update(bin_night=True, attention="tonight", title="Bins tonight")
    elif delta == 0:
        result.update(attention="morning", title="Bins out this morning")
    if result["attention"]:
        labels = {s["id"]: s["label"] for s in c["services"]}
        result["summary"] = result["title"] + "\n\n" + " · ".join(labels[t] for t in result["next"]["types"])
        if error:
            result["summary"] += "\n\n" + result["message"]
    return result


def confirm(store, house, body, prepared, now=None):
    now = now or datetime.now(UTC)
    value = load(store, house)
    if (
        set(body) != {"action", "revision", "epoch", "confirm", "preview_token", "screens"}
        or body["confirm"] is not True
        or type(body["revision"]) is not int
        or type(body["epoch"]) is not int
        or body["revision"] != value["revision"]
        or body["epoch"] != house["epoch"]
    ):
        raise ValueError("Review the current waste service and confirm it explicitly.")
    if not prepared or body["preview_token"] != prepared["token"] or not timedelta(0) <= now - timestamp(prepared["at"]) <= timedelta(minutes=10):
        raise ValueError("Waste preview expired. Check the service again.")
    screens = body["screens"]
    if not isinstance(screens, list) or len(set(screens)) != len(screens) or any(s not in {x["id"] for x in house["surfaces"]} for s in screens):
        raise ValueError("Choose saved screens for bin context.")
    value.update(copy.deepcopy(prepared["candidate"]))
    value["confirmed"]["screens"] = screens
    save(store, value)
    return value


def card():
    """Native conditional card: quiet state consumes no household screen space."""
    return {
        "type": "conditional",
        "conditions": [{"entity": "sensor.home_starter_bin_context", "state_not": ["quiet", "unknown", "unavailable"]}],
        "card": {
            "type": "markdown",
            "entity_id": [SOURCE_ENTITY],
            "content": "{% if as_timestamp(now()) < as_timestamp(state_attr('"
            + SOURCE_ENTITY
            + "', 'valid_until'),0) %}{{ state_attr('"
            + SOURCE_ENTITY
            + "','summary') or '' }}{% else %}Bin schedule needs checking{% endif %}",
        },
    }
