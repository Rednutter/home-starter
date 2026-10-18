"""Reproducible fictional household scenarios; never publish to real household state."""

import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homestarter.context import build
from homestarter.wall_composer import compose

ZONE = "Australia/Sydney"


def scenario(name):
    now = datetime(2026, 10, 19, 7, 30, tzinfo=ZoneInfo(ZONE))
    settings = {"rules": [], "events": {}}
    events, signals = [], []
    people = {"example_child": "Casey"}

    def event(title, start, minutes=60, *, leave=None, role="commitment", attention=False, all_day=False):
        key = hashlib.sha256(title.encode()).hexdigest()
        value = {"key": key, "title": title, "start": start, "end": start + timedelta(minutes=minutes), "all_day": all_day, "location": ""}
        events.append(value)
        settings["events"][key] = {
            "people": ["example_child"],
            "travel_minutes": 10 if leave else None,
            "buffer_minutes": 5,
            "round_minutes": 5,
            "routine_time": leave,
            "wall_role": role,
            "early_attention": attention,
        }
        return value

    if name in ("busy_school_morning", "weekday_morning_horizon"):
        event("School", now.replace(hour=8, minute=50), leave="08:30")
        event("Training", now.replace(hour=17, minute=30), leave="16:55")
        settings["rules"] = [
            {"id": "sports_kit", "text": "Sports kit and hat", "people": ["example_child"], "start": "2026-10-19", "end": "2026-10-19", "weekdays": [0]}
        ]
        if name == "weekday_morning_horizon":
            event("Music lesson", now.replace(hour=16) + timedelta(days=1))
            event("Weekend match", now.replace(hour=10) + timedelta(days=5))
    elif name in ("quiet_sunday", "sunday_evening"):
        now = now.replace(day=18, hour=19 if name == "sunday_evening" else 10, minute=0)
        event("Exercise", now.replace(hour=7) + timedelta(days=1))
        event("Work commitment", now.replace(hour=8, minute=30) + timedelta(days=1))
        event("Practice match", now.replace(hour=17) + timedelta(days=1))
        for day in (2, 3, 4, 5):
            event("Later commitment", now.replace(hour=16) + timedelta(days=day))
    elif name == "quiet_weekday_daytime":
        now = now.replace(hour=12, minute=0)
        event("Dental check-up", now + timedelta(days=1), role="preparation")
    elif name in ("pre_pickup", "active_movement", "weather_exception"):
        now = now.replace(hour=14, minute=30) if name != "active_movement" else now.replace(hour=15, minute=5)
        event("School pickup", now.replace(hour=15, minute=30), leave="15:10")
        if name == "weather_exception":
            signals.append({"domain": "weather", "entity_id": "weather.fixture", "state": "rainy", "attributes": {"temperature": 12, "temperature_unit": "°C"}})
    elif name == "evening_finished":
        now = now.replace(hour=20, minute=0)
        event("Finished practice", now.replace(hour=16), minutes=60)
        event("Bring permission form", now.replace(hour=8) + timedelta(days=1), role="preparation")
    elif name == "weekend_planning":
        now = now.replace(day=24, hour=10, minute=0)
        event("Melbourne tournament — arrange travel", now + timedelta(days=13), role="preparation", attention=True)
    elif name == "pupil_free_weekday":
        event("Pupil-free day", now.replace(hour=0, minute=0), minutes=24 * 60, role="holiday", all_day=True)
        settings["rules"] = [
            {"id": "normal_school", "text": "Normal school kit", "people": ["example_child"], "start": "2026-10-19", "end": "2026-10-19", "weekdays": [0]}
        ]
    elif name == "bins_tonight":
        now = now.replace(hour=20)
    elif name == "doorbell_takeover":
        signals.extend(
            [
                {
                    "domain": "event",
                    "entity_id": "event.example_doorbell",
                    "name": "Front door",
                    "state": now.isoformat(),
                    "attributes": {"device_class": "doorbell"},
                },
                {"domain": "camera", "entity_id": "camera.example_door", "state": "idle", "attributes": {}},
            ]
        )
        settings["wall"] = {"camera_links": {"event.example_doorbell": "camera.example_door"}}
    elif name == "active_timer_media":
        now = now.replace(hour=12)
        signals.extend(
            [
                {
                    "domain": "timer",
                    "entity_id": "timer.example_oven",
                    "name": "Oven timer",
                    "state": "active",
                    "attributes": {"finishes_at": (now + timedelta(minutes=8)).isoformat()},
                },
                {
                    "domain": "media_player",
                    "entity_id": "media_player.example_shared",
                    "name": "Kitchen audio",
                    "state": "playing",
                    "attributes": {"media_title": "Afternoon radio"},
                },
            ]
        )
    elif name == "completely_quiet":
        now = now.replace(hour=12)
    else:
        raise ValueError(name)
    view = build(events, now, ZONE, settings, people, briefing_limit=20)
    view["issues"] = []
    if name == "bins_tonight":
        view["waste"] = {"configured": True, "attention": "tonight", "summary": "Bins tonight — green and yellow"}
    return {
        "name": name,
        "now": now,
        "settings": settings,
        "events": events,
        "signals": signals,
        "view": view,
        "people": people,
        "model": compose(view, events, settings, people, now, ZONE, signals),
    }


SCENARIOS = (
    "busy_school_morning",
    "weekday_morning_horizon",
    "quiet_sunday",
    "sunday_evening",
    "quiet_weekday_daytime",
    "pre_pickup",
    "active_movement",
    "evening_finished",
    "weekend_planning",
    "pupil_free_weekday",
    "weather_exception",
    "bins_tonight",
    "doorbell_takeover",
    "active_timer_media",
    "completely_quiet",
)
