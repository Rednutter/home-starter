"""Fictional collection data for deterministic waste tests; never a council schedule."""

import calendar
from datetime import UTC, date, datetime

from homestarter import waste


def annual(year=2026):
    return {
        "year": year,
        "valid_from": f"{year}-01-01",
        "valid_to": f"{year}-12-31",
        "dates": {
            date(year, m, d).isoformat(): ["organics", "recycling"]
            if ((date(year, m, d) - date(year, 1, 1)).days + date(year, 1, 1).weekday()) // 7 % 2
            else ["organics", "general"]
            for m in range(1, 13)
            for d in range(1, calendar.monthrange(year, m)[1] + 1)
            if date(year, m, d).weekday() < 5
        },
        "source_type": "annual_calendar",
        "source_id": f"https://www.wodonga.vic.gov.au/fictional-test-calendar-{year}.pdf",
        "version": "a" * 64,
    }


def configured(house, now=None, year=2026):
    now = now or datetime.now(UTC)
    return {
        **waste.empty(house),
        "confirmed": {
            "provider": "wodonga",
            "day": 3,
            "zone": "fixture-zone",
            "location_source": "arcgis",
            "map_version": "fixture-1",
            "screens": [s["id"] for s in house["surfaces"]],
            "services": copy_services(),
        },
        "schedules": [annual(year)],
        "checked_at": now.isoformat(),
        "verified_at": now.isoformat(),
    }


class FictionalProvider:
    id = "wodonga"

    def __init__(self):
        self.services = copy_services()
        self.years = [2026]
        self.error = None
        self.day = 3
        self.zone = "fixture-zone"

    async def location(self, config):
        if self.error:
            raise self.error
        return {"day": self.day, "zone": self.zone, "location_source": "arcgis", "map_version": "fixture-1"}

    async def fetch(self, year):
        if self.error:
            raise self.error
        return [annual(y) for y in self.years]


def copy_services():
    return [
        {"id": "organics", "label": "Green", "cadence": "weekly"},
        {"id": "recycling", "label": "Recycling", "cadence": "fortnightly"},
        {"id": "general", "label": "General waste", "cadence": "fortnightly"},
    ]
