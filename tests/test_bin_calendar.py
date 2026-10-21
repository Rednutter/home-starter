"""Native calendar ownership and idempotence with fictional Council dates."""

import asyncio
import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from homestarter import bin_calendar, waste
from homestarter.household import HouseholdStore
from waste_scenarios import configured

NOW = datetime(2026, 10, 14, 19, tzinfo=ZoneInfo("Australia/Melbourne"))


class Core:
    def __init__(self):
        self.entries = [{"entry_id": "unowned", "title": "Bin Calendar", "state": "loaded"}]
        self.registry = [{"entity_id": "calendar.bins", "config_entry_id": "unowned"}]
        self.rows = []
        self.creates = 0
        self.uncertain = False

    async def config(self):
        return {"time_zone": "Australia/Melbourne"}

    async def local_calendar_flow(self, body, flow_id=None):
        if flow_id is None:
            return {"type": "form", "step_id": "user", "flow_id": "fixture"}
        self.entries.append({"entry_id": "owned", "title": body["calendar_name"], "state": "loaded"})
        self.registry.append({"entity_id": "calendar.home_starter_bins", "config_entry_id": "owned"})
        return {"type": "create_entry", "result": {"entry_id": "owned"}}

    def websocket(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def command(self, kind, **args):
        if kind == "config_entries/get":
            return self.entries
        if kind == "config/entity_registry/list":
            return self.registry
        assert args["entity_id"] == "calendar.home_starter_bins"
        if kind == "calendar/event/create":
            self.creates += 1
            assert set(args["event"]) == {"dtstart", "dtend", "summary", "description"}
            event = copy.deepcopy(args["event"])
            event["start"], event["end"] = event.pop("dtstart"), event.pop("dtend")
            event["start"], event["end"] = {"date": event["start"]}, {"date": event["end"]}
            self.rows.append({**event, "uid": "uid-" + str(self.creates)})
            if self.uncertain:
                self.uncertain = False
                raise TimeoutError()
            return None
        if kind == "calendar/event/update":
            assert set(args["event"]) == {"dtstart", "dtend", "summary", "description"}
            event = copy.deepcopy(args["event"])
            event["start"], event["end"] = {"date": event.pop("dtstart")}, {"date": event.pop("dtend")}
            row = next(r for r in self.rows if r["uid"] == args["uid"])
            row.update(event)
            if self.uncertain:
                self.uncertain = False
                raise TimeoutError()
            return None
        raise AssertionError(kind)

    async def rest_get(self, path):
        assert path.startswith("/calendars/calendar.home_starter_bins?")
        return copy.deepcopy(self.rows)


@pytest.fixture
def store(tmp_path):
    result = HouseholdStore(tmp_path)
    result.save(result.load())
    waste.save(result, configured(result.load(), NOW))
    return result


async def test_reconcile_is_native_idempotent_concurrent_and_preserves_unowned_calendar(store):
    core = Core()
    await asyncio.gather(*(bin_calendar.reconcile(core, store, store.load(), NOW) for _ in range(2)))
    count = core.creates
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert count == core.creates == 6
    assert len(core.entries) == 2
    assert core.entries[0]["title"] == "Bin Calendar"
    assert all(row["start"]["date"] > NOW.date().isoformat() for row in core.rows)
    assert all("reminder" not in row["summary"].lower() for row in core.rows)
    assert len({r["uid"] for r in core.rows}) == count


async def test_uncertain_event_create_recovers_by_native_uid_without_duplicate(store):
    core = Core()
    core.uncertain = True
    with pytest.raises(TimeoutError):
        await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert core.creates == 1
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert core.creates == 6


async def test_external_edits_or_removals_are_preserved_and_require_review(store):
    core = Core()
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    core.rows[0]["summary"] = "Owner changed this"
    with pytest.raises(ValueError, match="edited outside"):
        await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert core.rows[0]["summary"] == "Owner changed this"
    rows = await bin_calendar.wall_rows(core, store, store.load(), "Australia/Melbourne", NOW)
    assert len(rows) == 5


async def test_collection_action_is_derived_without_previous_evening_event(store):
    core = Core()
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    rows = await bin_calendar.wall_rows(core, store, store.load(), "Australia/Melbourne", NOW)
    assert rows[0]["title"] == "Bins out tonight"
    assert rows[0]["date"] == "2026-10-15"
    morning = NOW.replace(day=15, hour=8)
    assert (await bin_calendar.wall_rows(core, store, store.load(), "Australia/Melbourne", morning))[0]["title"] == "Bins today"
    assert (await bin_calendar.wall_rows(core, store, store.load(), "Australia/Melbourne", morning.replace(hour=12)))[0]["date"] == "2026-10-22"


async def test_uncertain_calendar_creation_never_starts_a_second_calendar(store):
    core = Core()
    store.write(bin_calendar.path(store), {"version": 1, "epoch": store.load()["epoch"], "entry_id": None})
    with pytest.raises(ValueError, match="uncertain"):
        await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert len(core.entries) == 1


async def test_uncertain_update_recovers_by_the_same_uid(store):
    core = Core()
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    before = [r["uid"] for r in core.rows]
    value = waste.load(store, store.load())
    value["schedules"][0]["dates"]["2026-10-15"] = ["organics", "general"]
    waste.save(store, value)
    core.uncertain = True
    with pytest.raises(TimeoutError):
        await bin_calendar.reconcile(core, store, store.load(), NOW)
    await bin_calendar.reconcile(core, store, store.load(), NOW)
    assert [r["uid"] for r in core.rows] == before
    assert core.creates == 6
    assert core.rows[0]["summary"] == "Green + General waste"
    assert "pending" not in bin_calendar.load(store, store.load())["events"]["2026-10-15"]
