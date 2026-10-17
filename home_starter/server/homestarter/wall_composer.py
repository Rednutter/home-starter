"""Deterministic shared wall interpretation. No title guessing, credentials or UI code."""

from datetime import date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from .context import departure
from .household import ENTITY, text

DEFAULTS = {
    "morning_start": 5,
    "morning_end": 10,
    "evening_start": 18,
    "night_start": 22,
    "imminent_minutes": 15,
    "prepare_minutes": 90,
    "horizon_days": 21,
    "hot_celsius": 32,
    "cold_celsius": 10,
    "suppressed_dates": [],
    "camera_links": {},
}
STATES = ("busy_morning", "quiet_daytime", "pre_activity", "active_movement", "evening", "overnight", "weekend", "abnormal_schedule", "exception")


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
        valid = all(p in people for p in link.get("people", []))
        leave = departure(e["start"], link) if link and valid and not e["all_day"] else None
        names = [people[p] for p in link.get("people", [])] if valid else []
        day = (e["start"].date() - local.date()).days
        when = "All day" if e["all_day"] else "Now" if e["start"] <= local else e["start"].strftime("%H:%M")
        if day > 0:
            when = ("Tomorrow" if day == 1 else e["start"].strftime("%a %d %b")) + ("" if e["all_day"] else " · " + when)
        row = {
            "id": e["key"],
            "title": e["title"],
            "when": when,
            "people": names,
            "detail": "Leave by " + leave.strftime("%H:%M") if leave else "",
            "location": e.get("location", ""),
            "ends_at": e["end"].isoformat(),
            "leave_at": leave.isoformat() if leave else None,
        }
        if day <= 0:
            rows.append(row)
            if leave and e["end"] > local:
                movements.append((leave, e["start"], row))
        elif day == 1 or link.get("early_attention") or link.get("wall_role") in ("preparation", "holiday"):
            future.append(row)
    rules = [] if abnormal else [r for r in view["briefing"] if r.get("when") == "This morning"]
    for r in rules:
        rows.insert(0, {**r, "people": [people[p] for p in r.get("people", []) if p in people]})
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
    exceptions, transient, weather = [], [], None
    camera_session = None
    for item in signals:
        domain, value, attrs = item["domain"], item.get("state"), item.get("attributes", {})
        if value in (None, "unknown", "unavailable"):
            continue
        label = item.get("name", "Household")
        if domain == "weather":
            weather = {"condition": value.replace("_", " "), "temperature": attrs.get("temperature"), "unit": attrs.get("temperature_unit", "°C")}
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
    # Row/session deadlines expire independently in the renderer. Expiring a
    # transient must not invalidate the underlying board until the next poll.
    return {
        "version": 1,
        "day_state": state,
        "baseline_state": baseline,
        "primary": primary,
        "day_summary": "Routine changed today"
        if abnormal
        else "Shared plans unavailable"
        if view.get("issues") and not rows
        else "Nothing urgent right now"
        if not rows
        else "Still to come today",
        "next_movement": cue,
        "today_items": rows[:today_limit],
        "future_attention": future[:future_limit],
        "household_exception": exceptions[:2],
        "active_context": transient[:2],
        "weather": weather,
        "display_session": active_session,
        "issues": view.get("issues", [])[:2],
        "valid_until": valid_until.isoformat(),
        "spans": {"today": "dominant" if rows and urgent else "compact" if rows else "hidden", "upcoming": "compact" if urgent else "expanded"},
    }
