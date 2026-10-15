"""Deterministic household chronology. Calendar payloads stay in memory, never settings."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .household import ID, text


def empty():
    return {"rules": [], "events": {}}


def validate(value):
    if not isinstance(value, dict) or set(value) != {"rules", "events"}:
        raise ValueError("Unsupported household context settings.")
    if not isinstance(value["rules"], list) or len(value["rules"]) > 30 or not isinstance(value["events"], dict) or len(value["events"]) > 100:
        raise ValueError("Too many household context choices.")

    def people(items):
        return isinstance(items, list) and len(items) <= 30 and all(isinstance(p, str) and ID.fullmatch(p) for p in items) and len(set(items)) == len(items)

    ids = []
    for rule in value["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"id", "text", "people", "start", "end", "weekdays"}:
            raise ValueError("A morning rule needs text, people, dates and weekdays.")
        if not isinstance(rule["id"], str) or not ID.fullmatch(rule["id"]) or not text(rule["text"], 160) or not people(rule["people"]):
            raise ValueError("Use short rule text and existing household people.")
        try:
            valid_dates = date.fromisoformat(rule["start"]) <= date.fromisoformat(rule["end"])
        except (ValueError, TypeError):
            valid_dates = False
        if (
            not valid_dates
            or not isinstance(rule["weekdays"], list)
            or not rule["weekdays"]
            or any(type(d) is not int or d not in range(7) for d in rule["weekdays"])
        ):
            raise ValueError("Review the rule date range and applicable weekdays.")
        ids.append(rule["id"])
    if len(set(ids)) != len(ids):
        raise ValueError("Rule IDs must be unique.")
    for key, link in value["events"].items():
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[a-f0-9]{64}", key)
            or not isinstance(link, dict)
            or set(link) != {"people", "travel_minutes", "buffer_minutes", "round_minutes", "routine_time"}
        ):
            raise ValueError("Choose an observed event and explicit departure settings.")
        if not people(link["people"]) or link["round_minutes"] not in (5, 10) or type(link["round_minutes"]) is not int:
            raise ValueError("Choose people and a five- or ten-minute departure boundary.")
        if link["travel_minutes"] is not None and (type(link["travel_minutes"]) is not int or not 0 <= link["travel_minutes"] <= 720):
            raise ValueError("Travel time must be an explicit number of minutes, or absent.")
        if type(link["buffer_minutes"]) is not int or not 0 <= link["buffer_minutes"] <= 180:
            raise ValueError("Review the practical departure margin.")
        if link["routine_time"] is not None and (
            not isinstance(link["routine_time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", link["routine_time"])
        ):
            raise ValueError("Use a local routine departure time, or leave it blank.")
    return copy.deepcopy(value)


def event_key(source, event):
    return hashlib.sha256(json.dumps([source, event.get("summary"), event.get("start"), event.get("end")], sort_keys=True).encode()).hexdigest()


def parse_events(raw, source, zone):
    """HA calendar dates are local and all-day ends exclusive; timed dates must be aware."""
    tz = ZoneInfo(zone)
    if not isinstance(raw, list):
        raise ValueError("Calendar did not return an event list.")
    result, invalid = [], 0
    for event in raw[:2000]:
        try:
            if not isinstance(event, dict) or not text(event.get("summary"), 300):
                raise ValueError("Invalid event title")
            start, end = event["start"], event["end"]
            all_day = "date" in start
            if all_day:
                a = datetime.combine(date.fromisoformat(start["date"]), time(), tz)
                b = datetime.combine(date.fromisoformat(end["date"]), time(), tz)
            else:
                a, b = datetime.fromisoformat(start["dateTime"]), datetime.fromisoformat(end["dateTime"])
                if a.tzinfo is None or b.tzinfo is None:
                    raise ValueError("Missing event timezone")
                a, b = a.astimezone(tz), b.astimezone(tz)
            if b.astimezone(UTC) <= a.astimezone(UTC):
                raise ValueError("Invalid event interval")
            result.append({"key": event_key(source, event), "title": event["summary"], "start": a, "end": b, "all_day": all_day})
        except (ValueError, KeyError, TypeError):
            invalid += 1
    # Sources may repeat occurrences; retain distinct intervals, never merge by name.
    result = list({e["key"]: e for e in result}.values())
    return sorted(result, key=lambda e: (e["start"].astimezone(UTC), e["title"], e["key"])), invalid + max(0, len(raw) - 2000)


def departure(start, choice):
    """Explicit travel/margin plus an optional earlier routine; round toward safety."""
    if not choice:
        return None
    calculated = (
        (start.astimezone(UTC) - timedelta(minutes=choice["travel_minutes"] + choice["buffer_minutes"])).astimezone(start.tzinfo)
        if choice["travel_minutes"] is not None
        else None
    )
    routine = datetime.combine(start.date(), time.fromisoformat(choice["routine_time"]), start.tzinfo) if choice["routine_time"] else None
    if routine and routine > start:
        return None  # Do not silently turn a contradictory routine into the previous day.
    candidates = [d for d in (calculated, routine) if d is not None]
    if not candidates:
        return None
    result = min(candidates)
    return result.replace(minute=result.minute - result.minute % choice["round_minutes"], second=0, microsecond=0)


def safe(value):
    # Calendar/rule text is data, never dashboard HTML, links or template source.
    return re.sub(r"([\\`*_\[\]()#!|])", r"\\\1", html.escape(value, quote=True))


def build(events, now, zone, settings, people):
    now = now.astimezone(ZoneInfo(zone))
    morning = 5 <= now.hour < 10
    phase = "morning" if morning else "daytime" if 10 <= now.hour < 15 else "afternoon" if 15 <= now.hour < 20 else "night"
    relevant = [e for e in events if e["end"].astimezone(UTC) > now.astimezone(UTC) and e["start"].date() <= now.date() + timedelta(days=21)]
    today = [e for e in relevant if e["start"].date() <= now.date()]
    future = [e for e in relevant if e["start"].date() > now.date()]
    # Near commitments own the space; quiet periods use the same rows further ahead.
    ahead_limit = 2 if morning and len(today) >= 3 else 6 if morning and len(today) == 2 else max(4, 14 - min(len(today), 10))
    notes = []
    if morning:
        for rule in settings["rules"]:
            if rule["start"] <= now.date().isoformat() <= rule["end"] and now.weekday() in rule["weekdays"] and all(p in people for p in rule["people"]):
                names = ", ".join(people[p] for p in rule["people"])
                notes.append((safe(names) + " — " if names else "") + safe(rule["text"]))

    def row(e, later=False):
        link = settings["events"].get(e["key"])
        valid_link = link and all(p in people for p in link["people"])
        names = ", ".join(people[p] for p in link["people"]) if valid_link else ""
        approaching = e["start"].astimezone(UTC) > now.astimezone(UTC)
        label = "All day" if e["all_day"] else "Now" if not approaching else e["start"].strftime("%H:%M")
        if later:
            label = e["start"].strftime("%a %d %b") + (" · All day" if e["all_day"] else " · " + e["start"].strftime("%H:%M"))
        line = f"**{label}**  {safe(e['title'])}" + (" — " + safe(names) if names else "")
        if not later and not e["all_day"] and e["start"].astimezone(UTC) - now.astimezone(UTC) <= timedelta(hours=2):
            line = f"### {label} · {safe(e['title'])}" + (" — " + safe(names) if names else "")
        leave = departure(e["start"], link) if valid_link and not e["all_day"] and approaching else None
        if leave:
            line += "  \nLeave by " + (leave.strftime("%a ") if leave.date() != e["start"].date() else "") + leave.strftime("%H:%M")
        return line

    near = "\n\n".join(notes + [row(e) for e in today[:8]])
    if len(today) > 8:
        near += f"\n\n+ {len(today) - 8} more scheduled today"
    next_rows = [row(e, True) for e in future[:ahead_limit]]
    return {
        "phase": phase,
        "near": near or ("No more scheduled today" if now.hour >= 15 else "Nothing scheduled today"),
        "ahead": "\n\n".join(next_rows) or "No upcoming events in the next three weeks",
        "today_count": len(today),
        "ahead_count": len(next_rows),
        "rule_count": len(notes),
        "scheduled_remaining": len(relevant),
    }


def proximity(event, now):
    local = now.astimezone(event["start"].tzinfo)
    if event["end"].astimezone(UTC) <= local.astimezone(UTC):
        return "elapsed"
    if event["start"].astimezone(UTC) <= local.astimezone(UTC):
        return "now"
    days = (event["start"].date() - local.date()).days
    return "later_today" if days == 0 else "tomorrow" if days == 1 else "next_few_days" if days <= 3 else "coming_weeks"


def entity_id(surface_id):
    return "sensor.home_starter_context_" + hashlib.sha256(surface_id.encode()).hexdigest()[:12]


def wall_cards(surface_id):
    entity = entity_id(surface_id)
    fresh = (
        "{% set fresh = 0 <= as_timestamp(now()) - as_timestamp(state_attr('"
        + entity
        + "', 'checked_at'), 0) < 180 and as_timestamp(now()) < as_timestamp(state_attr('"
        + entity
        + "', 'valid_until'), 0) %}"
    )

    def card(attribute, fallback):
        return {
            "type": "markdown",
            "entity_id": [entity],
            "content": fresh + "{% if fresh %}{{ state_attr('" + entity + "', '" + attribute + "') or '' }}{% else %}" + fallback + "{% endif %}",
        }

    return [card("near", "Calendar context unavailable"), card("ahead", "Upcoming context unavailable")]
