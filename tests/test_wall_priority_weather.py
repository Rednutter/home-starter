"""Synthetic action and daily weather facts; no household payloads."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homestarter.wall_priority import select
from homestarter.wall_weather import compose, warning

ZONE = ZoneInfo("Australia/Sydney")
NOW = datetime(2026, 10, 21, 8, 20, tzinfo=ZONE)


def test_confirmed_school_departure_grouped_without_inferred_kit_or_travel():
    school = {
        "date": "2026-10-21",
        "children": [{"name": name, "school_leave_at": NOW.replace(hour=8, minute=30).isoformat()} for name in ["Casey", "Alex", "Taylor"]],
    }
    selected = select([], school, NOW)
    assert selected["title"] == "School run in 10 minutes"
    assert selected["people"] == ["Casey", "Alex", "Taylor"]
    assert selected["action"] == "Leave 08:30"
    assert select([], school, NOW.replace(hour=8, minute=14)) is None
    assert select([], school, NOW.replace(hour=8, minute=40)) is None
    assert select([], {**school, "date": "2026-10-22"}, NOW) is None


def test_overdue_before_immediate_before_shortly_and_no_completion_claim():
    def row(key, minutes):
        return {"id": key, "title": key, "leave_at": (NOW + timedelta(minutes=minutes)).isoformat()}

    selected = select([row("Soon", 10), row("Now", 0), row("Passed", -2)], None, NOW)
    assert selected["id"] == "Passed"
    assert selected["title"] == "Leave time passed for Passed"
    assert "late" not in selected["title"].lower()
    assert select([{"id": "No travel", "title": "Appointment", "starts_at": NOW.isoformat()}], None, NOW)["action"] == "Starts 08:20"
    assert select([row("Expired", -11)], None, NOW) is None


def test_daily_forecasts_are_dated_optional_and_shared_without_extrapolation():
    attrs = {
        "temperature": 13,
        "temperature_unit": "\u00b0C",
        "forecast": [
            {"datetime": "2026-10-20T14:00:00Z", "temperature": 26, "templow": 12, "condition": "sunny"},
            {"datetime": "2026-10-21T14:00:00Z", "temperature": 22, "templow": 10, "condition": "rainy"},
        ],
    }
    weather = compose("partlycloudy", attrs, {"date": "2026-10-21", "preview": False, "label": "Today"}, ZONE)
    assert weather["high"] == 26
    assert weather["days"]["2026-10-22"]["condition"] == "rainy"
    assert "2026-10-23" not in weather["days"]
    assert compose("sunny", attrs, {"date": "2026-10-23", "preview": True, "label": "Friday"}, ZONE)["high"] is None


def test_weather_levels_have_units_and_do_not_invent_official_warning_or_timing():
    assert warning({"temperature": 102}, {"temperature_unit": "\u00b0F"})["kind"] == "heat"
    assert warning({"temperature": 26, "precipitation": 40}, {"precipitation_unit": "in"}) is None
    assert warning({"wind_speed": 16}, {"wind_speed_unit": "m/s"})["kind"] == "wind"
    for row, attrs in [
        ({"condition": "lightning-rainy"}, {}),
        ({"condition": "hail"}, {}),
        ({"precipitation": 55}, {"precipitation_unit": "mm"}),
        ({"templow": 0}, {}),
    ]:
        value = warning(row, attrs)
        assert value
        assert "afternoon" not in value["message"]
        assert value["level"] != "official"
