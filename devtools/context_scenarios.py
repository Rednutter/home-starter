"""Fictional context examples, never copied from a household calendar."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def scenarios():
    zone = ZoneInfo("Australia/Sydney")
    monday = datetime(2026, 6, 8, 7, 10, tzinfo=zone)

    def event(title, start, minutes=60):
        return {"summary": title, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()}}

    future = [
        event(title, monday.replace(hour=hour) + timedelta(days=day))
        for title, day, hour in (
            ("Community rehearsal", 1, 17),
            ("Library return", 2, 16),
            ("Team practice", 3, 18),
            ("Friends visiting", 5, 12),
            ("School planning evening", 7, 18),
            ("Service appointment", 9, 10),
            ("Weekend walk", 12, 9),
            ("Club presentation", 15, 18),
            ("Neighbourhood picnic", 18, 12),
            ("Family lunch", 20, 12),
        )
    ]
    busy = [
        event(title, monday.replace(hour=hour, minute=minute))
        for title, hour, minute in (
            ("School arrival", 8, 40),
            ("Project meeting", 9, 30),
            ("Clinic appointment", 11, 15),
            ("Training", 17, 20),
        )
    ]
    return [
        {"id": "busy-morning", "now": monday, "events": busy + future, "rule": True},
        {"id": "quiet-morning", "now": monday, "events": [event("Afternoon appointment", monday.replace(hour=16))] + future},
        {"id": "daytime", "now": monday.replace(hour=12), "events": [event("Evening rehearsal", monday.replace(hour=18))] + future},
        {"id": "afternoon", "now": monday.replace(hour=16), "events": [event("Training", monday.replace(hour=17, minute=20))] + future},
        {"id": "evening-finished", "now": monday.replace(hour=21), "events": busy + future},
        {"id": "weekend", "now": monday.replace(day=13, hour=11), "events": future},
        {"id": "no-calendar", "now": monday, "events": [], "status": "Household calendar not selected"},
        {"id": "calendar-unavailable", "now": monday, "events": [], "status": "Calendar temporarily unavailable"},
    ]
