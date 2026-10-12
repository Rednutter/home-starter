"""Explicit recorder completion transitions, restart-safe counts in HA's timezone."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from .core import CoreClient, CoreError
from .household import HouseholdStore


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("History timestamps must include a timezone.")
    return result.astimezone(UTC)


def activity_entity(rule: dict) -> str:
    return "sensor.home_starter_activity_" + hashlib.sha256(rule["id"].encode()).hexdigest()[:12]


def consume(rule: dict, record: dict, rows: list[dict], zone: str, now: datetime) -> dict:
    """Only adjacent, observed explicit transitions count. Unknown breaks continuity."""
    record = dict(record)
    signature = [rule[k] for k in ("entity_id", "from_state", "to_state")]
    if record.get("signature") != signature:
        record = {
            "signature": signature,
            "since": now.isoformat(),
            "cursor": now.isoformat(),
            "previous": None,
            "last_run": None,
            "day": now.astimezone(ZoneInfo(zone)).date().isoformat(),
            "runs_today": 0,
        }
    day = now.astimezone(ZoneInfo(zone)).date().isoformat()
    if record["day"] != day:
        record.update(day=day, runs_today=0)
    cursor = timestamp(record["cursor"])
    for row in sorted(rows, key=lambda r: timestamp(r.get("last_changed") or r["last_updated"])):
        when = timestamp(row.get("last_changed") or row["last_updated"])
        if row.get("entity_id") != rule["entity_id"] or when <= cursor or when > now:
            continue
        current = row.get("state")
        if record["previous"] == rule["from_state"] and current == rule["to_state"]:
            record["last_run"] = when.isoformat()
            if when.astimezone(ZoneInfo(zone)).date().isoformat() == day:
                record["runs_today"] += 1
        record["previous"] = None if current in (None, "unknown", "unavailable") else current
        record["cursor"] = when.isoformat()
        cursor = when
    record["status"] = "tracking"
    return record


async def update_activity(core: CoreClient, store: HouseholdStore, rules: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    if not rules:
        return []
    zone = (await core.config())["time_zone"]
    ZoneInfo(zone)  # Fail closed rather than roll days in the server's timezone.
    records = store.read(store.activity_path, {})
    states = {s["entity_id"]: s for s in await core.states()}
    output = []
    for rule in rules:
        previous = records.get(rule["id"], {})
        signature = [rule[k] for k in ("entity_id", "from_state", "to_state")]
        if previous.get("signature") != signature:
            previous = consume(rule, {}, [], zone, now)
            previous["previous"] = states.get(rule["entity_id"], {}).get("state")
            if previous["previous"] in ("unknown", "unavailable"):
                previous["previous"] = None
        start = max(timestamp(previous["cursor"]) - timedelta(seconds=1), timestamp(previous["since"]))
        # Recorder supplies every state change, including short cycles between polls.
        query = urlencode({"filter_entity_id": rule["entity_id"], "end_time": now.isoformat()})
        try:
            history = await core.rest_get("/history/period/" + quote(start.isoformat(), safe="") + "?" + query)
            if not isinstance(history, list) or any(not isinstance(group, list) for group in history):
                raise ValueError("Unexpected recorder history.")
            rows = [r for group in history for r in group]
            if not rows:
                raise CoreError("api", "No recorder history available for this appliance.")
            record = consume(rule, previous, rows, zone, now)
            record["checked_at"] = now.isoformat()
        except (CoreError, ValueError, KeyError, TypeError):
            record = dict(previous, status="history_unavailable")
        records[rule["id"]] = record
        # Persist the consumed cursor before publishing state: a failed REST write must not double-count.
        store.write(store.activity_path, records)
        entity_id = activity_entity(rule)
        existing = states.get(entity_id)
        if existing and (existing.get("attributes") or {}).get("home_starter_activity_id") != rule["id"]:
            raise CoreError("api", "Activity screen name is already in use. Choose a different activity ID.")
        current_day = now.astimezone(ZoneInfo(zone)).date().isoformat()
        count = record["runs_today"] if record["day"] == current_day else 0
        available = record["status"] == "tracking"
        attributes = {
            "friendly_name": rule["name"] + " activity today",
            "home_starter_activity_id": rule["id"],
            "last_run": record["last_run"],
            "runs_today": count,
            "ran_today": bool(count) if available else None,
            "tracking_since": record["since"],
            "coverage": record["status"],
            "source": rule["entity_id"],
            "icon": "mdi:check-circle-outline",
        }
        payload = {"state": str(count) if available else "unknown", "attributes": attributes}
        if not existing or existing.get("state") != payload["state"] or existing.get("attributes") != attributes:
            await core.activity_state(entity_id, payload)
        output.append({"id": rule["id"], "name": rule["name"], "entity_id": entity_id, **attributes})
    return output
