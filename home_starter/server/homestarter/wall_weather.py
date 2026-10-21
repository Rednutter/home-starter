"""One dated native forecast model shared by header and chronology."""

from datetime import datetime
from math import isfinite


def number(value):
    return value if type(value) in (int, float) and isfinite(value) else None


def warning(row, attrs):
    """Describe supported daily facts, never invent timing or official alerts."""
    condition = row.get("condition", "")
    high, low = number(row.get("temperature")), number(row.get("templow"))
    if attrs.get("temperature_unit") == "\u00b0F":
        high = (high - 32) * 5 / 9 if high is not None else None
        low = (low - 32) * 5 / 9 if low is not None else None
    rain, wind = number(row.get("precipitation")), number(row.get("wind_speed"))
    unit = attrs.get("wind_speed_unit")
    kmh = wind * 3.6 if unit == "m/s" and wind is not None else wind * 1.609344 if unit == "mph" and wind is not None else wind if unit == "km/h" else None
    if condition in ("lightning", "lightning-rainy"):
        return {"kind": "storm", "level": "noteworthy", "label": "Storm", "message": "Thunderstorms forecast"}
    if condition == "hail":
        return {"kind": "hail", "level": "significant", "label": "Hail", "message": "Hail forecast"}
    if rain is not None and attrs.get("precipitation_unit") == "mm" and rain >= 25:
        return {"kind": "rain", "level": "significant" if rain >= 50 else "noteworthy", "label": "Heavy rain", "message": f"{rain:g} mm forecast"}
    if kmh is not None and kmh >= 50:
        return {"kind": "wind", "level": "significant" if kmh >= 90 else "noteworthy", "label": "Strong wind", "message": f"Wind {kmh:.0f} km/h forecast"}
    if high is not None and high >= 35:
        return {"kind": "heat", "level": "significant" if high >= 40 else "noteworthy", "label": "Very hot", "message": "High temperatures forecast"}
    if low is not None and low <= 2:
        return {"kind": "cold", "level": "noteworthy", "label": "Very cold", "message": "Cold overnight low forecast"}
    return None


def forecasts(attrs, zone):
    result = {}
    for row in attrs.get("forecast", []):
        if not isinstance(row, dict):
            continue
        try:
            at = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                continue
            day = at.astimezone(zone).date().isoformat()
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        result.setdefault(
            day,
            {
                "date": day,
                "condition": row.get("condition"),
                "high": number(row.get("temperature")),
                "low": number(row.get("templow")),
                "warning": warning(row, attrs),
                "precipitation_probability": number(row.get("precipitation_probability")),
            },
        )
    return result


def compose(value, attrs, focus, zone):
    days = forecasts(attrs, zone)
    day = days.get(focus["date"], {})
    return {
        "condition": value.replace("_", " "),
        "temperature": number(attrs.get("temperature")),
        "unit": attrs.get("temperature_unit", "\u00b0C"),
        "high": day.get("high"),
        "low": day.get("low"),
        "forecast_condition": day.get("condition"),
        "warning": day.get("warning"),
        "precipitation_probability": day.get("precipitation_probability"),
        "days": days,
        "preview": focus["preview"],
        "focus_date": focus["date"],
        "focus_label": focus["label"],
    }
