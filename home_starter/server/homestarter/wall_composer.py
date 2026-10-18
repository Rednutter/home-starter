"""Deterministic shared wall interpretation. No title guessing, credentials or UI code."""

import re
from datetime import date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from .context import departure
from .household import ENTITY, text

DEFAULTS = {
    "morning_start": 5,
    "morning_end": 10,
    "evening_start": 18,
    "night_start": 21,
    "imminent_minutes": 15,
    "prepare_minutes": 90,
    "horizon_days": 21,
    "hot_celsius": 32,
    "cold_celsius": 10,
    "suppressed_dates": [],
    "camera_links": {},
}
STATES = ("busy_morning", "quiet_daytime", "pre_activity", "active_movement", "evening", "overnight", "weekend", "abnormal_schedule", "exception")


def short_location(value, title=""):
    """Keep a venue label, never a street/postal address or map URL."""
    if not isinstance(value, str) or re.search(r"https?://|geo:", value, re.I):
        return ""
    place, _, extra = value.partition("(")
    place = place.split(",", 1)[0].strip()
    if re.match(r"^\d+[\w/ -]*\s", place) and re.search(r"\b(street|st|road|rd|drive|dr|avenue|ave|lane|ln|highway|hwy)\b", place, re.I):
        return ""
    initials = "".join(w[0] for w in place.split() if w.casefold() not in {"the", "of", "and"} and w[0].isalpha()).upper()
    if 3 <= len(initials) <= 6 and re.search(r"\b" + re.escape(initials) + r"\b", title):
        return initials
    parts = extra.rstrip(")").split(",")
    city = parts[1].strip() if len(parts) > 2 else ""
    city = re.sub(
        r"\s+(?:NSW|VIC|QLD|SA|WA|TAS|ACT|NT|New South Wales|Victoria|Queensland|South Australia|Western Australia|Tasmania)\b.*$", "", city, flags=re.I
    )
    if city and len(city) < 25 and city.replace(" ", "").isalpha() and place.casefold().endswith(" " + city.casefold()):
        place = place[: -len(city)].strip()
        place = re.sub(r"\s+Gym$", "", place, flags=re.I)
        place += " · " + city
    place = re.sub(r"\s+FC$", "", place)
    place = re.sub(r"\s+(?:PTY\.?\s+LTD\.?|LLC|INC\.?|LIMITED)$", "", place, flags=re.I)
    return place if len(place) <= 48 else place[:45].rsplit(" ", 1)[0] + "…"


def horizon(future, rows, urgent, baseline, local, exceptions, evening_start=18):
    """Weight already selected facts independently of their visual allocation."""
    phase = "night" if baseline == "overnight" else "evening" if local.hour >= evening_start else "afternoon" if local.hour >= 12 else "morning"
    tomorrow = [r for r in future if r["day_offset"] == 1]
    ahead = [r for r in future if r["day_offset"] > 1]
    primary = "current" if urgent or exceptions else "today" if rows else "tomorrow" if tomorrow else "ahead" if ahead else "rest"
    weights = {
        "now": 5 if urgent or exceptions else 0,
        "today": 4 if urgent else 2 if rows else 1,
        "tomorrow": 5 if phase == "evening" else 4 if phase == "afternoon" else 3,
        "ahead": 1 if urgent else 3,
    }
    tomorrow = tomorrow[: 1 if urgent or baseline == "overnight" else 5]
    groups = []
    for row in ahead:
        day = date.fromisoformat(row["date"])
        weekend = day.weekday() >= 5 and row["day_offset"] <= 7
        key = (day - timedelta(days=day.weekday() - 5)).isoformat() if weekend else row["date"]
        if not groups or groups[-1]["date"] != key:
            groups.append({"date": key, "label": "Weekend" if weekend else row["day_label"], "items": []})
        groups[-1]["items"].append({**row, "time": day.strftime("%a") + " · " + row["time"]} if weekend else row)
    groups = groups[: 1 if urgent or baseline == "overnight" else 6]
    for group in groups:
        group["items"] = group["items"][: 1 if urgent or baseline == "overnight" else 3]
    return {"layout": primary, "phase": phase, "weights": weights, "tomorrow_items": tomorrow, "ahead_groups": groups}


def person_attribution(event, link, people):
    """Explicit links, mapped calendars, or an unambiguous leading name label."""
    if "people" in link:
        return link["people"], "event_link", None
    if event.get("person_ids"):
        return event["person_ids"], "calendar_mapping", None
    matches = []
    for person_id, name in people.items():
        match = re.fullmatch(re.escape(name) + r"\s*[-–—·:]\s*(\S.*)", event["title"], flags=re.I)
        if match:
            matches.append((person_id, match[1]))
    return ([matches[0][0]], "calendar_label", matches[0][1]) if len(matches) == 1 else ([], None, None)


def focus_window(rows, future, local, policy, urgent):
    """Select a date; priorities and visual placement are separate concerns."""
    imminent = any(
        r.get("time") != "All day" and r.get("starts_at") and 0 <= (moment(r["starts_at"]) - local).total_seconds() <= policy["prepare_minutes"] * 60
        for r in rows
    )
    preview = not urgent and not imminent and (local.hour >= policy["evening_start"] or local.weekday() == 6 and local.hour >= 15)
    return {
        "mode": "tomorrow_preview" if preview else "today",
        "preview": preview,
        "night": local.hour >= policy["night_start"] or local.hour < policy["morning_start"],
        "date": (local + timedelta(days=int(preview))).date().isoformat(),
        "label": "Tomorrow" if preview else "Today",
    }


def importance(row, local, preview=False):
    stamp = moment(row.get("leave_at") or row.get("starts_at"))
    minutes = (stamp - local).total_seconds() / 60 if stamp else None
    return (
        "upcoming"
        if preview
        else "immediate"
        if minutes is not None and -15 <= minutes <= 15
        else "soon"
        if minutes is not None and 0 < minutes <= 90
        else "context"
        if row.get("day_offset", 0) > 1
        else "upcoming"
    )


def reference_panels(rows, future, people, signals, local, cue, issues, exceptions, preparation, focus):
    """Compose useful islands inside stable time/weather, agenda and status anchors."""
    tomorrow = [r for r in future if r["day_offset"] == 1]
    selected = [*preparation, *tomorrow] if focus["preview"] else rows
    selected = [{**r, "importance": importance(r, local, focus["preview"])} for r in selected]
    cards = []
    for person_id, name in people.items():
        facts = [r for r in selected if person_id in r.get("person_ids", [])]
        if facts:
            avatar = next((s["entity_id"] for s in signals if s["domain"] == "person" and s.get("attributes", {}).get("id") == person_id), None)
            departure_id = next((r["id"] for r in facts if r.get("leave_at")), None)
            facts = [{**r, "title": r.get("person_title") or r["title"], "primary_departure": r.get("id") == departure_id} for r in facts]
            weight = max((r["importance"] for r in facts), key={"context": 0, "upcoming": 1, "soon": 2, "immediate": 3}.get)
            cards.append({"key": "person-" + person_id, "kind": "person", "title": name, "importance": weight, "avatar_entity": avatar, "items": facts[:3]})
    dated = [r for r in rows if r.get("time")]
    later = [r for r in future if r["day_offset"] > 1]
    week_days = {}
    for row in later:
        week_days.setdefault(row["date"], row)
    primary = tomorrow if focus["preview"] else dated or tomorrow or later
    label = "Tomorrow" if focus["preview"] else "Today" if dated else "Tomorrow" if tomorrow else "Coming up"
    timeline_cue = next((r for r in primary if r.get("leave_at")), None) if focus["preview"] else cue
    if timeline_cue:
        primary = [
            {
                **r,
                "time": moment(r["leave_at"]).astimezone(local.tzinfo).strftime("%I:%M").lstrip("0")
                + (" pm" if moment(r["leave_at"]).astimezone(local.tzinfo).hour >= 12 else ""),
                "detail": "Arrive " + r["time"],
            }
            if r["id"] == timeline_cue["id"] and r.get("leave_at")
            else r
            for r in primary
        ]
    secondary = dated if focus["preview"] else dated[1:] if len(dated) > 1 else tomorrow if dated else later
    secondary_label = "Tonight" if focus["preview"] else "Later today" if len(dated) > 1 else "Tomorrow" if dated and tomorrow else "Week ahead"
    context_cards = [
        {
            "kind": "context",
            "title": "Today",
            "summary": "Plans unavailable" if issues and not rows else "Quiet " + local.strftime("%A") if not rows else "Still to come",
            "items": dated[:3],
        },
        {
            "kind": "context",
            "title": "Tomorrow",
            "summary": "Plans unavailable" if issues and not tomorrow else (local + timedelta(days=1)).strftime("%A") if tomorrow else "No shared plans",
            "items": [*preparation, *tomorrow][:3],
        },
        {"kind": "context", "title": "This week", "summary": "No further shared plans" if not later else "", "items": list(week_days.values())[:3]},
    ]
    cards = cards[:3]
    unassigned = [r for r in selected if not r.get("person_ids")]
    if unassigned:
        cards.append(
            {
                "key": "shared-" + focus["date"],
                "kind": "context",
                "title": (local + timedelta(days=int(focus["preview"]))).strftime("%A"),
                "importance": "upcoming",
                "items": unassigned[:3],
            }
        )
    if not focus["preview"]:
        for card in context_cards:
            if len(cards) >= 3:
                break
            if not card["items"] or card["title"] == "Today" or card["title"] == "Tomorrow" and dated:
                continue
            if any(r["id"] in {item.get("id") for c in cards for item in c["items"]} for r in card["items"]):
                continue
            cards.append({**card, "key": "context-" + card["title"], "importance": "context"})
    sources = {s["entity_id"]: s for s in signals}
    climate = next((s for s in sources.values() if s["domain"] == "climate" and s.get("attributes", {}).get("fan_modes")), None)
    climate = climate or next((s for s in sources.values() if s["domain"] == "climate"), None)
    alarms = [s for s in sources.values() if s["domain"] == "alarm_control_panel"]
    lights = [s for s in sources.values() if s["domain"] == "light"]

    def usable(s):
        return s.get("state") not in (None, "unknown", "unavailable")

    security = (
        "Not selected"
        if not alarms
        else "Needs attention"
        if any(s["state"] == "triggered" for s in alarms)
        else "Armed"
        if all(str(s["state"]).startswith("armed_") for s in alarms)
        else "Disarmed"
        if all(s["state"] == "disarmed" for s in alarms)
        else "Status unavailable"
    )
    lighting = (
        "Not selected"
        if not lights
        else "Status unavailable"
        if not all(usable(s) for s in lights)
        else str(sum(s["state"] == "on" for s in lights)) + " on"
        if any(s["state"] == "on" for s in lights)
        else "All off"
    )
    climate_attrs = climate.get("attributes", {}) if climate and usable(climate) else {}
    temp = climate_attrs.get("current_temperature")
    selected_status = [*alarms, *lights, *([climate] if climate else [])]
    status = {
        "home": "Needs attention"
        if exceptions
        else "Status unavailable"
        if not selected_status
        else "Status incomplete"
        if not all(usable(s) for s in selected_status)
        else "All good",
        "climate": {
            "temperature": temp if type(temp) in (int, float) and isfinite(temp) else None,
            "unit": climate_attrs.get("temperature_unit", "°C"),
            "detail": " · ".join(str(v).replace("_", " ").capitalize() for v in (climate_attrs.get("hvac_action"), climate_attrs.get("fan_mode")) if v)
            or ("Not selected" if not climate else "Status unavailable"),
        },
        "security": security,
        "lights": lighting,
        "cameras": [
            {"entity": s["entity_id"], "name": s.get("name") or s.get("attributes", {}).get("friendly_name", "Camera"), "available": usable(s)}
            for s in sources.values()
            if s["domain"] == "camera"
        ],
    }
    return {
        "focus": focus,
        "cards": cards[:3],
        "timeline": {
            "label": label,
            "date_label": (local + timedelta(days=int(label == "Tomorrow"))).strftime("%a %d %b"),
            "items": primary[:5],
        },
        "secondary": {"label": secondary_label, "items": [] if focus.get("night") else secondary[:3]},
        "household_status": status,
    }


def validate_policy(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError("Unsupported wall presentation settings.")
    policy = {**DEFAULTS, **value}
    for key in ("morning_start", "morning_end", "evening_start", "night_start"):
        if type(policy[key]) is not int or not 0 <= policy[key] <= 23:
            raise ValueError("Wall day boundaries need whole hours.")
    if not policy["morning_start"] < policy["morning_end"] < policy["evening_start"] < policy["night_start"]:
        raise ValueError("Keep wall morning, evening and overnight boundaries in order.")
    for key, low, high in (
        ("imminent_minutes", 1, 60),
        ("prepare_minutes", 15, 240),
        ("horizon_days", 1, 21),
        ("hot_celsius", 20, 50),
        ("cold_celsius", -20, 20),
    ):
        if type(policy[key]) is not int or not low <= policy[key] <= high:
            raise ValueError("Review wall timing, horizon and temperature thresholds.")
    if policy["prepare_minutes"] < policy["imminent_minutes"]:
        raise ValueError("Preparation must begin before the imminent movement threshold.")
    dates = policy["suppressed_dates"]
    if not isinstance(dates, list) or len(dates) > 90 or any(not isinstance(d, str) or date.fromisoformat(d).isoformat() != d for d in dates):
        raise ValueError("Use explicit ISO dates for routine exceptions.")
    links = policy["camera_links"]
    if (
        not isinstance(links, dict)
        or len(links) > 20
        or any(
            not isinstance(k, str)
            or not k.startswith("event.")
            or not ENTITY.fullmatch(k)
            or not isinstance(v, str)
            or not v.startswith("camera.")
            or not ENTITY.fullmatch(v)
            for k, v in links.items()
        )
    ):
        raise ValueError("Link a real doorbell event to a selected camera entity.")
    return policy


def school_placement(panels, school, rows, future, settings, people, local):
    """School facts own the canvas; household chronology is shown once beside it."""
    from .school_timetable import attendance

    panels["school"] = school
    panels["week"] = []
    if not school:
        return panels
    consumed = set()
    for child in school["children"]:
        dated = [
            r
            for r in [*rows, *future]
            if r.get("date") == school["date"]
            and child["person"] in r.get("person_ids", [])
            and settings["events"].get(r["id"], {}).get("wall_role") in {"school", "preparation"}
        ]
        child["dated"] = [{**r, "title": r.get("person_title") or r["title"], "importance": importance(r, local, panels["focus"]["preview"])} for r in dated]
        day = date.fromisoformat(school["date"])
        child["rules"] = [
            r["text"]
            for r in settings["rules"]
            if child["person"] in r["people"] and r["start"] <= school["date"] <= r["end"] and day.weekday() in r["weekdays"]
        ]
        child["commitments"] = [
            r for r in [*rows, *future] if r.get("date") == school["date"] and child["person"] in r.get("person_ids", []) and r not in dated
        ][:1]
        consumed.update(r["id"] for r in dated if settings["events"].get(r["id"], {}).get("wall_role") == "preparation")
    for panel in ("timeline", "secondary"):
        panels[panel]["items"] = [r for r in panels[panel]["items"] if r["id"] not in consumed]
    selected = [r for r in [*rows, *future] if r.get("date") == school["date"] and r["id"] not in consumed]
    explicit_school = {p for r in selected if settings["events"].get(r["id"], {}).get("wall_role") == "school" for p in r.get("person_ids", [])}
    # Keep explicit appointments and departure cues; summarise native classes
    # separately so school attendance appears alongside the whole household.
    presented = {r["id"]: r for r in panels["timeline"]["items"]}
    selected = [presented.get(r["id"], r) for r in selected]
    selected.extend(attendance(school["children"], explicit_school, local))
    panels["timeline"].update(
        label=panels["focus"]["label"],
        date_label=date.fromisoformat(school["date"]).strftime("%a %d %b"),
        items=sorted(selected, key=lambda r: r.get("leave_at") or r.get("starts_at") or school["date"]),
    )
    timeline_ids = {r["id"] for r in panels["timeline"]["items"]}
    panels["secondary"]["items"] = [r for r in panels["secondary"]["items"] if r["id"] not in timeline_ids]
    # School columns replace generic copies of the same calendar appointments.
    panels["cards"] = []
    used = {r["id"] for panel in ("timeline", "secondary") for r in panels[panel]["items"]} | consumed
    days = {}
    for row in future:
        if row["date"] > school["date"] and row["id"] not in used:
            days.setdefault(row["date"], {"date": row["date"], "label": row["day_label"], "items": []})["items"].append(row)
    panels["week"] = [{**group, "items": group["items"][:2]} for group in list(days.values())[:6]]
    return panels


def moment(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def session(value, now, cameras):
    """Validate a short, plain-text/native-camera session; never persist its content."""
    if not isinstance(value, dict) or set(value) - {"kind", "title", "body", "camera", "seconds"}:
        raise ValueError("Unsupported temporary wall session.")
    kind = value.get("kind")
    if kind not in {"recipe", "camera", "weather", "plan", "answer", "timer", "departure"} or not text(value.get("title"), 100):
        raise ValueError("Choose a supported wall session and short title.")
    body = value.get("body", "")
    if not isinstance(body, str) or len(body) > (160 if kind == "camera" else 600) or body.count("\n") > 8 or any(ord(c) < 32 and c != "\n" for c in body):
        raise ValueError("Use plain text for the temporary wall content.")
    seconds = value.get("seconds", 120)
    if type(seconds) is not int or not 5 <= seconds <= 600:
        raise ValueError("Wall sessions expire after 5 to 600 seconds.")
    camera = value.get("camera")
    if kind == "camera" and camera not in cameras or kind != "camera" and camera is not None:
        raise ValueError("Choose a verified camera selected for this wall.")
    return {"kind": kind, "title": value["title"], "body": body, "camera": camera, "expires_at": (now + timedelta(seconds=seconds)).isoformat()}


def compose(view, events, settings, people, now, zone, signals=(), display_session=None):
    """Consume interpreted/selected household inputs; return inspectable presentation priorities."""
    local = now.astimezone(ZoneInfo(zone))
    policy = validate_policy(settings.get("wall", {}))
    links = settings["events"]
    abnormal = local.date().isoformat() in policy["suppressed_dates"] or any(
        e["start"] <= local < e["end"] and links.get(e["key"], {}).get("wall_role") == "holiday" for e in events
    )
    rows, future, movements = [], [], []
    for e in events:
        if e["end"] <= local or e["start"] > local + timedelta(days=policy["horizon_days"]):
            continue
        link = links.get(e["key"], {})
        person_ids, attribution, person_title = person_attribution(e, link, people)
        valid = all(p in people for p in person_ids)
        leave = departure(e["start"], link) if link and valid and not e["all_day"] else None
        names = [people[p] for p in person_ids] if valid else []
        start = e["start"].astimezone(local.tzinfo)
        day = (start.date() - local.date()).days
        when = "All day" if e["all_day"] else "Now" if e["start"] <= local else e["start"].strftime("%H:%M")
        if day > 0:
            when = ("Tomorrow" if day == 1 else e["start"].strftime("%a %d %b")) + ("" if e["all_day"] else " · " + when)
        row = {
            "id": e["key"],
            "title": e["title"],
            "when": when,
            "people": names,
            "person_ids": person_ids if valid else [],
            "person_title": person_title,
            "attribution": attribution,
            "detail": "Leave by " + leave.strftime("%H:%M") if leave else "",
            "location": short_location(e.get("location", ""), e["title"]),
            "date": start.date().isoformat(),
            "starts_at": start.isoformat(),
            "day_offset": day,
            "day_label": start.strftime("%A") if day <= 7 else start.strftime("%a %d %b"),
            "time": "All day" if e["all_day"] else start.strftime("%I:%M").lstrip("0") + (" pm" if start.hour >= 12 else ""),
            "early_start": not e["all_day"] and start.hour < 9,
            "ends_at": e["end"].isoformat(),
            "leave_at": leave.isoformat() if leave else None,
        }
        if day <= 0:
            rows.append(row)
            if leave and e["end"] > local:
                movements.append((leave, e["start"], row))
        elif day <= 7 or link.get("early_attention") or link.get("wall_role") in ("preparation", "holiday"):
            future.append(row)
    rows.sort(key=lambda r: r["starts_at"])
    future.sort(key=lambda r: r["starts_at"])
    rules = [] if abnormal else [r for r in view["briefing"] if r.get("when") == "This morning"]
    for r in rules:
        rows.insert(0, {**r, "person_ids": r.get("people", []), "people": [people[p] for p in r.get("people", []) if p in people]})
    movements.sort(key=lambda r: r[0])
    movement = next((m for m in movements if local < m[1]), next(iter(movements), None))
    minutes = (movement[0] - local).total_seconds() / 60 if movement else None
    state = (
        "abnormal_schedule"
        if abnormal
        else "overnight"
        if local.hour >= policy["night_start"] or local.hour < policy["morning_start"]
        else ("evening" if local.hour >= policy["evening_start"] else "weekend" if local.weekday() >= 5 else "quiet_daytime")
    )
    if rows and policy["morning_start"] <= local.hour < policy["morning_end"] and not abnormal:
        state = "busy_morning"
    if minutes is not None and minutes <= policy["prepare_minutes"]:
        state = "active_movement" if minutes <= policy["imminent_minutes"] else "busy_morning" if state == "busy_morning" else "pre_activity"
    focus = focus_window(rows, future, local, policy, state in ("busy_morning", "pre_activity", "active_movement"))
    exceptions, transient, weather = [], [], None
    camera_session = None
    for item in signals:
        domain, value, attrs = item["domain"], item.get("state"), item.get("attributes", {})
        if value in (None, "unknown", "unavailable"):
            continue
        label = item.get("name", "Household")
        if domain == "weather":
            weather = {"condition": value.replace("_", " "), "temperature": attrs.get("temperature"), "unit": attrs.get("temperature_unit", "°C")}
            forecast = next(
                (
                    r
                    for r in attrs.get("forecast", [])
                    if isinstance(r, dict) and moment(r.get("datetime")) and moment(r["datetime"]).astimezone(local.tzinfo).date().isoformat() == focus["date"]
                ),
                {},
            )
            high = forecast.get("temperature")
            weather["high"] = high if type(high) in (int, float) and isfinite(high) else None
            weather["precipitation_probability"] = forecast.get("precipitation_probability")
            low = forecast.get("templow")
            weather.update(
                preview=focus["preview"],
                focus_date=focus["date"],
                focus_label=focus["label"],
                low=low if type(low) in (int, float) and isfinite(low) else None,
                forecast_condition=forecast.get("condition"),
            )
            temp = attrs.get("temperature")
            celsius = (temp - 32) * 5 / 9 if isinstance(temp, (int, float)) and attrs.get("temperature_unit") == "°F" else temp
            if movement and value in ("rainy", "pouring", "lightning", "lightning-rainy", "snowy", "snowy-rainy"):
                exceptions.append({"title": "Check conditions before leaving", "detail": value.replace("_", " "), "kind": "weather"})
            elif (
                movement and isinstance(celsius, (int, float)) and isfinite(celsius) and (celsius >= policy["hot_celsius"] or celsius <= policy["cold_celsius"])
            ):
                exceptions.append({"title": "Prepare for the temperature", "detail": str(temp) + " " + weather["unit"], "kind": "weather"})
        elif domain == "timer" and value == "active":
            finish = moment(attrs.get("finishes_at"))
            if finish and finish > now:
                transient.append(
                    {"kind": "timer", "title": label, "detail": "Ends " + finish.astimezone(local.tzinfo).strftime("%H:%M"), "expires_at": finish.isoformat()}
                )
        elif domain == "media_player" and value == "playing":
            transient.append({"kind": "media", "title": attrs.get("media_title") or label, "detail": label})
        elif domain == "event" and attrs.get("device_class") == "doorbell":
            stamp = moment(value)
            if stamp and 0 <= (now - stamp).total_seconds() < 120:
                expires = stamp + timedelta(seconds=120)
                exceptions.append({"title": label, "detail": "Doorbell", "kind": "doorbell", "expires_at": expires.isoformat()})
                camera = policy["camera_links"].get(item["entity_id"])
                if camera and any(
                    s["entity_id"] == camera and s["domain"] == "camera" and s.get("state") not in (None, "unavailable", "unknown") for s in signals
                ):
                    camera_session = {"kind": "camera", "title": label, "body": "Doorbell", "camera": camera, "expires_at": expires.isoformat()}
        elif item.get("level") in (0, 1) and value in ("on", "triggered", "open", "opening", "unlocked"):
            exceptions.append({"title": label, "detail": "Needs attention", "kind": "household"})
        elif domain == "climate" and attrs.get("hvac_action") in ("heating", "cooling"):
            transient.append({"kind": "climate", "title": label, "detail": attrs["hvac_action"].capitalize()})
    bins = view.get("waste", {})
    if bins.get("configured") and bins.get("attention") not in (None, "quiet") and bins.get("summary"):
        exceptions.append({"title": bins["summary"], "detail": "Household collection", "kind": "bins"})
    baseline = state
    if exceptions:
        state = "exception"
    active_session = display_session if display_session and (moment(display_session.get("expires_at")) or now) > now else camera_session
    if any(e["kind"] == "household" for e in exceptions):
        active_session = None  # A temporary answer or camera must never obscure a safety exception.
    urgent = baseline in ("busy_morning", "pre_activity", "active_movement")
    primary = "exception" if exceptions else "movement" if movement and urgent else "today" if rows else "upcoming" if future else "quiet"
    today_limit, future_limit = (4, 1) if urgent else (2, 5) if state != "overnight" else (1, 1)
    outlook = horizon(future, rows, urgent, baseline, local, exceptions, policy["evening_start"])
    tomorrow_date = (local + timedelta(days=1)).date()
    tomorrow_changed = tomorrow_date.isoformat() in policy["suppressed_dates"] or any(
        e["start"].astimezone(local.tzinfo).date() <= tomorrow_date < e["end"].astimezone(local.tzinfo).date()
        and links.get(e["key"], {}).get("wall_role") == "holiday"
        for e in events
    )
    preparation = []
    preparation_rows = []
    if focus["preview"] and not tomorrow_changed:
        for rule in settings.get("rules", []):
            if (
                rule["start"] <= tomorrow_date.isoformat() <= rule["end"]
                and tomorrow_date.weekday() in rule["weekdays"]
                and all(p in people for p in rule["people"])
            ):
                preparation.append({"title": rule["text"], "people": [people[p] for p in rule["people"]]})
                preparation_rows.append(
                    {
                        "id": "rule-" + rule.get("id", str(len(preparation_rows))),
                        "title": rule["text"],
                        "people": [people[p] for p in rule["people"]],
                        "person_ids": rule["people"],
                        "when": "Tomorrow",
                        "date": tomorrow_date.isoformat(),
                        "day_offset": 1,
                    }
                )
        if preparation and outlook["layout"] in ("ahead", "rest"):
            outlook["layout"] = "tomorrow"
    cue = None
    if movement and urgent:
        cue = {
            **movement[2],
            "label": "Underway"
            if local >= movement[1]
            else "Leave now"
            if minutes <= 0
            else "Leave soon"
            if minutes <= policy["imminent_minutes"]
            else "Next movement",
        }
    if baseline == "overnight":
        transient = []  # The infrastructure owns actual monitor dimming, never CSS alone.
    valid_until = now + timedelta(seconds=75)
    from .school_timetable import select as school_select

    focus_day = date.fromisoformat(focus["date"])
    school_changed = focus["date"] in policy["suppressed_dates"] or any(
        e["start"].astimezone(local.tzinfo).date() <= focus_day < e["end"].astimezone(local.tzinfo).date()
        and links.get(e["key"], {}).get("wall_role") == "holiday"
        for e in events
    )
    school = school_select(view.get("school_sources", []), people, view.get("person_roles", {}), focus, local, school_changed)
    panels = reference_panels(rows, future, people, signals, local, cue, view.get("issues", []), exceptions, preparation_rows, focus)
    panels = school_placement(panels, school, rows, future, settings, people, local)
    if focus["night"]:
        panels["week"] = []
    # Row/session deadlines expire independently in the renderer. Expiring a
    # transient must not invalidate the underlying board until the next poll.
    return {
        "version": 1,
        "day_state": state,
        "baseline_state": baseline,
        "primary": primary,
        **outlook,
        **panels,
        "today_summary": "Plans unavailable" if view.get("issues") and not rows else "Quiet " + local.strftime("%A") if not rows else "Still to come today",
        "tomorrow_label": (local + timedelta(days=1)).strftime("%A"),
        "tomorrow_preparation": preparation[:2],
        "day_summary": "Routine changed today"
        if abnormal
        else "Shared plans unavailable"
        if view.get("issues") and not rows
        else "Quiet " + local.strftime("%A")
        if not rows
        else "Still to come today",
        "next_movement": cue,
        "today_items": rows[:today_limit],
        "future_attention": future[:future_limit] if urgent or baseline == "overnight" else future[:17],
        "household_exception": exceptions[:2],
        "active_context": transient[:2],
        "weather": weather,
        "display_session": active_session,
        "issues": view.get("issues", [])[:2],
        "valid_until": valid_until.isoformat(),
        "spans": {"today": "dominant" if rows and urgent else "compact" if rows else "hidden", "upcoming": "compact" if urgent else "expanded"},
    }
