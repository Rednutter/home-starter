"""Fictional waste schedules and geography only."""

import calendar
import copy
import json
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import context_runtime, waste, waste_runtime
from homestarter.core import CoreError
from homestarter.household import HouseholdStore
from homestarter.server import K_STATE, create_app
from homestarter.surfaces import generate
from homestarter.wodonga import SourceError, dated_cells, match_area, safe_url
from waste_scenarios import FictionalProvider, annual, configured

ZONE = "Australia/Melbourne"
NOW = datetime(2026, 10, 14, 19, tzinfo=ZoneInfo(ZONE))


@pytest.fixture
def store(tmp_path):
    result = HouseholdStore(tmp_path)
    house = result.load()
    house["surfaces"] = [{"id": "fixture_panel", "name": "Fixture panel", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}]
    result.save(house)
    return result


def test_missing_waste_is_lazy_and_preserves_existing_files(store):
    before = {p.name: p.read_bytes() for p in store.path.parent.iterdir() if p.is_file()}
    result = waste.view(waste.load(store, store.load()), ZONE, NOW)
    assert result["status"] == "unconfigured" and not waste.path(store).exists()
    assert before == {p.name: p.read_bytes() for p in store.path.parent.iterdir() if p.is_file()}


@pytest.mark.parametrize(
    "when,attention,day,stream",
    [
        ("2026-10-14T17:59:00", None, "2026-10-15", "recycling"),
        ("2026-10-14T18:00:00", "tonight", "2026-10-15", "recycling"),
        ("2026-10-15T00:00:00", "morning", "2026-10-15", "recycling"),
        ("2026-10-15T05:59:00", "morning", "2026-10-15", "recycling"),
        ("2026-10-15T06:00:00", "morning", "2026-10-15", "recycling"),
        ("2026-10-15T12:00:00", None, "2026-10-22", "general"),
        ("2026-10-18T19:00:00", None, "2026-10-22", "general"),
        ("2026-10-21T19:00:00", "tonight", "2026-10-22", "general"),
    ],
)
def test_time_local_green_weekly_alternating_streams_and_useful_expiry(store, when, attention, day, stream):
    now = datetime.fromisoformat(when).replace(tzinfo=ZoneInfo(ZONE))
    result = waste.view(configured(store.load(), now), ZONE, now)
    assert result["next"] == {"date": day, "types": ["organics", stream]}
    assert result["attention"] == attention
    assert result["bin_night"] is (attention == "tonight")
    assert bool(result["summary"]) is bool(attention)
    assert "done" not in result["summary"].lower()


@pytest.mark.parametrize(
    "year,month,day,expected", [(2026, 12, 31, "2027-01-07"), (2028, 2, 28, "2028-02-29"), (2026, 12, 24, "2026-12-25"), (2026, 1, 1, "2026-01-01")]
)
def test_year_boundary_leap_year_and_unshifted_public_holidays(store, year, month, day, expected):
    now = datetime(year, month, day, 19 if (month, day) != (1, 1) else 5, tzinfo=ZoneInfo(ZONE))
    value = configured(store.load(), now, year)
    value["confirmed"]["day"] = date.fromisoformat(expected).weekday()
    if year == 2026 and expected.startswith("2027"):
        value["schedules"].append(annual(2027))
    result = waste.view(value, ZONE, now)
    assert result["next"]["date"] == expected


def test_annual_validity_never_extends_parity_past_year(store):
    now = datetime(2027, 1, 1, 19, tzinfo=ZoneInfo(ZONE))
    value = configured(store.load(), now, 2026)
    result = waste.view(value, ZONE, now)
    assert result["status"] == "stale" and result["next"] is None
    assert result["summary"] == "Bin schedule needs checking"


def test_outage_keeps_dated_answer_until_bounded_staleness(store):
    value = configured(store.load(), NOW)
    value["error"] = {"kind": "unavailable", "message": "Council unavailable"}
    for days, status in [(1, "last_known_valid"), (7, "last_known_valid"), (8, "stale")]:
        result = waste.view(value, ZONE, NOW + timedelta(days=days))
        assert result["status"] == status
        assert bool(result["next"]) is (days <= 7)
    value["error"] = {"kind": "changed", "message": "Conflicting source"}
    assert waste.view(value, ZONE, NOW)["next"] is None
    assert value["schedules"] == [annual()]


async def test_source_renewal_and_restart_preserve_existing_settings(store):
    value = configured(store.load(), NOW)
    waste.save(store, value)
    existing = store.path.read_bytes()

    class Core:
        async def config(self):
            return {"time_zone": ZONE}

    provider = FictionalProvider()
    provider.years = [2026, 2027]
    refreshed = await waste.refresh(provider, Core(), store, store.load(), NOW)
    assert {r["year"] for r in refreshed["schedules"]} == {2026, 2027}
    assert not waste.view(refreshed, ZONE, NOW)["renewal_due"]
    assert waste.load(HouseholdStore(store.path.parent), store.load()) == refreshed
    assert store.path.read_bytes() == existing
    provider.error = SourceError("No network", "unavailable")
    outage = await waste.refresh(provider, Core(), store, store.load(), NOW + timedelta(days=1))
    assert outage["verified_at"] == refreshed["verified_at"] and outage["schedules"] == refreshed["schedules"]


async def test_zone_change_preserves_last_valid_but_requires_confirmation(store):
    value = configured(store.load(), NOW)
    waste.save(store, value)

    class Core:
        async def config(self):
            return {"time_zone": ZONE}

    provider = FictionalProvider()
    provider.day = 4
    result = await waste.refresh(provider, Core(), store, store.load(), NOW)
    assert result["confirmed"]["day"] == 3 and result["error"]["kind"] == "location"
    assert waste.view(result, ZONE, NOW)["status"] == "needs_checking"


class NativeCore:
    def __init__(self):
        self.entries = []
        self.registry = []
        self.observed = []
        self.flows = {}
        self.fail = False
        self.creations = 0
        self.writes = []

    async def config(self):
        return {"time_zone": ZONE}

    async def states(self):
        return self.observed

    def websocket(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def command(self, kind, **fields):
        if kind == "config_entries/get":
            return self.entries
        if kind == "config/entity_registry/list":
            return self.registry
        raise AssertionError("Unexpected native operation")

    async def template_flow(self, body, flow_id=None):
        if flow_id is None:
            flow_id = "fixture_flow_" + str(len(self.flows))
            self.flows[flow_id] = {}
            return {"type": "menu", "flow_id": flow_id}
        if "next_step_id" in body:
            self.flows[flow_id]["kind"] = body["next_step_id"]
            return {"type": "form", "step_id": body["next_step_id"], "flow_id": flow_id}
        self.creations += 1
        entry = {
            "entry_id": "fixture_entry_" + str(self.creations),
            "title": body["name"],
            "domain": "template",
            "modified_at": 1,
            "state": "loaded",
            "disabled_by": None,
        }
        entity = next(k for k, v in waste_runtime.SPECS.items() if v[0] == body["name"])
        self.entries.append(entry)
        self.registry.append({"entity_id": entity, "config_entry_id": entry["entry_id"], "disabled_by": None})
        if self.fail:
            raise CoreError("unreachable", "Fixture uncertain create result")
        return {"type": "create_entry", "result": entry}

    async def context_state(self, entity, payload):
        self.writes.append((entity, payload))
        self.observed = [{"entity_id": entity, **payload}]


async def test_owned_native_entities_are_idempotent_and_expiring(store):
    waste.save(store, configured(store.load(), NOW))
    core = NativeCore()
    await waste_runtime.prepare(core, store, store.load())
    assert core.creations == 6
    before = waste.path(store).read_bytes()
    await waste_runtime.prepare(core, store, store.load())
    assert core.creations == 6 and waste.path(store).read_bytes() == before
    await waste_runtime.project(core, store, store.load(), NOW)
    entity, payload = core.writes[-1]
    assert entity == waste.SOURCE_ENTITY and payload["attributes"]["bin_night"] is True
    assert waste.timestamp(payload["attributes"]["valid_until"]) == NOW.astimezone(UTC) + timedelta(seconds=150)
    assert payload["attributes"]["types"] == ["organics", "recycling"]
    for target in waste_runtime.SPECS:
        assert "now()" in waste_runtime.helper_config(target)["additional_options"]["availability"]


async def test_uncertain_creation_never_creates_a_duplicate(store):
    waste.save(store, configured(store.load(), NOW))
    core = NativeCore()
    core.fail = True
    with pytest.raises(CoreError):
        await waste_runtime.prepare(core, store, store.load())
    assert core.creations == 1
    with pytest.raises(ValueError, match="uncertain"):
        await waste_runtime.prepare(core, store, store.load())
    assert core.creations == 1 and not core.writes


@pytest.mark.parametrize("collision", ["helper", "source"])
async def test_native_entity_collisions_are_not_overwritten(store, collision):
    waste.save(store, configured(store.load(), NOW))
    core = NativeCore()
    entity = next(iter(waste_runtime.SPECS)) if collision == "helper" else waste.SOURCE_ENTITY
    core.observed = [{"entity_id": entity, "state": "existing", "attributes": {}}]
    before = copy.deepcopy(core.observed)
    with pytest.raises(ValueError):
        await waste_runtime.prepare(core, store, store.load())
    assert core.creations == 0 and core.observed == before and not core.writes


@pytest.mark.parametrize("edit", ["modified", "renamed", "disabled", "missing"])
async def test_edited_missing_or_renamed_helpers_stop_projection(store, edit):
    waste.save(store, configured(store.load(), NOW))
    core = NativeCore()
    await waste_runtime.prepare(core, store, store.load())
    if edit == "modified":
        core.entries[0]["modified_at"] = 2
    elif edit == "renamed":
        core.registry[0]["entity_id"] = "sensor.fixture_renamed"
    elif edit == "disabled":
        core.entries[0]["disabled_by"] = "user"
    else:
        core.entries.pop()
    with pytest.raises(ValueError):
        await waste_runtime.project(core, store, store.load(), NOW)
    assert not core.writes


def test_normalized_service_contract_can_represent_a_council_specific_stream(store):
    value = configured(store.load(), NOW)
    value["confirmed"]["services"].append({"id": "textiles", "label": "Textiles", "cadence": "provider_schedule"})
    value["schedules"][0]["dates"]["2026-10-15"].append("textiles")
    waste.save(store, value)
    result = waste.view(waste.load(store, store.load()), ZONE, NOW)
    assert result["next"]["types"] == ["organics", "recycling", "textiles"] and "Textiles" in result["summary"]


async def test_context_consumes_waste_as_context_not_an_event(make_env):
    env = await make_env("ready")
    store = HouseholdStore(env.settings.data_dir)
    house = store.load()
    value = configured(house, NOW)
    value["confirmed"]["screens"] = ["fixture_screen"]
    waste.save(store, value)
    result = await context_runtime.inspect(env.core, store, now=NOW)
    assert result["near"].startswith("Bins tonight") and result["events"] == []
    excluded = await context_runtime.inspect(
        env.core, store, {"id": "excluded", "person_id": None, "audience": "everyone", "profile": "wall", "area_id": None, "name": "Excluded fixture"}, NOW
    )
    assert "waste" not in excluded and "Bins tonight" not in excluded["near"]


@pytest.mark.parametrize("error", [TimeoutError(), SourceError("Annual response changed"), SourceError("No network", "unavailable")])
async def test_refresh_failures_never_erase_last_verified_data(store, error):
    waste.save(store, configured(store.load(), NOW))
    core = NativeCore()
    provider = FictionalProvider()
    provider.error = error
    result = await waste.refresh(provider, core, store, store.load(), NOW)
    assert result["schedules"] == [annual()] and result["verified_at"] == NOW.isoformat()
    assert result["error"]["kind"] == ("changed" if isinstance(error, SourceError) and error.kind == "changed" else "unavailable")


@pytest.mark.parametrize(
    "url",
    [
        "http://www.arcgis.com/item",
        "https://localhost/file",
        "https://arcgis.com.evil.example/file",
        "https://example@example.invalid/file",
        "https://www.arcgis.com:8123/file",
    ],
)
def test_source_addresses_are_bounded(url):
    with pytest.raises(SourceError):
        safe_url(url)


def test_local_polygon_lookup_holes_boundary_and_ambiguity():
    feature = {
        "attributes": {"OBJECTID": 7, "type": "Collection Thursday"},
        "geometry": {"rings": [[[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]], [[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]]},
    }
    assert match_area([feature], 3, 3) == {"day": 3, "zone": "7"}
    for features, lat, lon in [([feature], 1.5, 1.5), ([feature], 0, 1), ([feature, feature], 3, 3), ([feature], 10, 10)]:
        with pytest.raises(SourceError):
            match_area(features, lat, lon)


def geometry(year):
    texts = [(str(year), 28, 556), ("Wodonga", 28, 518), ("Organics", 310, 180), ("Recycling", 310, 150), ("General Waste", 310, 120)]
    boxes = []
    boxes.extend([(308, 148, 330, 154, "recycling"), (308, 118, 345, 124, "general")])
    for month in range(1, 13):
        hx = 30 + 95 * ((month - 1) % 4)
        hy = 460 - 82 * ((month - 1) // 4)
        texts.extend([(calendar.month_name[month], hx + 30, hy + 9), ("Mo Tu We Th Fr Sa Su", hx, hy)])
        texts.append(("1", hx + 1.3 + 11 * date(year, month, 1).weekday(), hy - 9.9))
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            d = date(year, month, day)
            if d.weekday() > 4:
                continue
            row = ((day - 1 + date(year, month, 1).weekday()) // 7) % 5
            x, y = hx + 3 + 11 * d.weekday(), hy - 7 - row * 11.68
            boxes.append((x - 2, y - 2, x + 2, y + 2, annual(year)["dates"][d.isoformat()][1]))
    return texts, boxes


@pytest.mark.parametrize("year", [2026, 2027, 2028])
def test_dated_calendar_geometry_covers_entire_year(year):
    assert dated_cells(*geometry(year))["dates"] == {k: v[1] for k, v in annual(year)["dates"].items()}


@pytest.mark.parametrize("failure", ["missing_month", "missing_cell", "conflict", "wrong_council", "repeat_week", "wrong_year_grid", "legend"])
def test_calendar_partial_changed_or_conflicting_geometry_fails_closed(failure):
    texts, boxes = geometry(2026)
    if failure == "missing_month":
        texts = [t for t in texts if t[0] != "July"]
    elif failure == "wrong_council":
        texts = [t for t in texts if t[0] != "Wodonga"]
    elif failure == "missing_cell":
        boxes.pop(2)
    elif failure == "conflict":
        boxes.append((*boxes[2][:4], "general" if boxes[2][4] == "recycling" else "recycling"))
    elif failure == "wrong_year_grid":
        texts = [("2027", x, y) if t == "2026" else (t, x, y) for t, x, y in texts]
    elif failure == "legend":
        boxes[0] = (*boxes[0][:4], "general")
    else:
        boxes = [(*b[:4], "general") for b in boxes]
    with pytest.raises(SourceError):
        dated_cells(texts, boxes)


def test_confirmation_requires_current_revision_explicit_consent_and_saved_screens(store):
    house = store.load()
    value = configured(house, NOW)
    prepared = {
        "token": "fictional-preview",
        "at": NOW.isoformat(),
        "candidate": {k: value[k] for k in ("confirmed", "schedules", "checked_at", "verified_at", "error")},
    }
    body = {"action": "confirm", "revision": 0, "epoch": house["epoch"], "confirm": True, "preview_token": prepared["token"], "screens": ["fixture_panel"]}
    for extra in ({"confirm": False}, {"revision": 1}, {"screens": ["unknown"]}, {"address": "fictional-rejected-field"}):
        with pytest.raises(ValueError):
            waste.confirm(store, house, {**body, **extra}, prepared, NOW)
    with pytest.raises(ValueError):
        waste.confirm(store, house, body, prepared, NOW + timedelta(minutes=11))
    result = waste.confirm(store, house, body, prepared, NOW)
    assert result["confirmed"]["screens"] == ["fixture_panel"]
    assert all(k not in waste.path(store).read_text().lower() for k in ("latitude", "longitude", "password", "address"))


@pytest.mark.parametrize("change", ["future_version", "unknown_field", "partial_annual"])
def test_invalid_storage_is_preserved_and_never_rewritten(store, change):
    value = configured(store.load(), NOW)
    if change == "future_version":
        value["version"] = 999
    elif change == "unknown_field":
        value["private_payload"] = {}
    else:
        value["schedules"][0]["dates"].pop("2026-01-01")
    store.write(waste.path(store), value)
    before = waste.path(store).read_bytes()
    with pytest.raises(ValueError):
        waste.load(store, store.load())
    assert waste.path(store).read_bytes() == before


def test_dashboard_bin_context_is_conditional_and_explicitly_selected(store):
    house = store.load()
    surface = house["surfaces"][0]
    without = generate(house, surface, [], [])
    with_bins = generate(house, surface, [], [], policy={"bin_context_screens": [surface["id"]]})
    assert "sensor.home_starter_bin_context" not in json.dumps(without)
    assert "sensor.home_starter_bin_context" in json.dumps(with_bins)
    assert "state_not" in json.dumps(with_bins)
    assert "calendar." not in json.dumps(with_bins)


def test_provider_screen_policy_preserves_unselected_legacy_calendar_choices():
    original = {"waste": ["calendar.fixture_bins"], "waste_screens": ["old", "selected"], "calendars_screens": ["selected"]}
    result = waste.screen_policy(original, {"screens": ["selected", "new"]})
    assert result["bin_context_screens"] == ["selected", "new"]
    assert result["waste_screens"] == ["old"] and original["waste_screens"] == ["old", "selected"]
    assert result["waste"] == original["waste"] and result["calendars_screens"] == ["selected"]
    assert waste.screen_policy(original, None)["waste_screens"] == original["waste_screens"]


async def test_provider_does_not_suppress_legacy_waste_on_unselected_screens(make_env):
    from homestarter import readiness

    env = await make_env("ready")
    store = HouseholdStore(env.settings.data_dir)
    house = store.load()
    waste.save(store, configured(house, NOW))
    saved = readiness.empty(house["epoch"])
    saved["choices"]["waste"] = {"intent": "wanted", "sources": ["calendar.fixture_bins"], "screens": ["other"], "answers": {}, "permissions": {}}
    store.write(store.readiness_path, saved)
    base = {"person_id": None, "audience": "everyone", "profile": "wall", "area_id": None, "name": "Fixture"}
    excluded = await context_runtime.inspect(env.core, store, {**base, "id": "other"}, NOW)
    selected = await context_runtime.inspect(env.core, store, {**base, "id": "fixture_panel"}, NOW)
    assert "Collection source needs verification" in excluded["issues"]
    assert "Collection source needs verification" not in selected["issues"]


async def test_waste_routes_require_admin_and_preview_writes_nothing(make_env):
    env = await make_env("ready")
    app = create_app(env.settings, env.session)
    async with TestClient(TestServer(app)) as client:
        state = app[K_STATE]
        state.waste_provider = FictionalProvider()
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/waste")).status == 403
        before = state.household.path.read_bytes()
        result = await client.post("/api/waste", headers=headers, json={"action": "preview", "day": 3})
        assert result.status == 200
        proposal = (await result.json())["proposal"]
        assert proposal["day"] == "Thursday"
        assert not waste.path(state.household).exists() and state.household.path.read_bytes() == before
        response = await client.post("/api/waste", headers=headers, json={"action": "confirm", "confirm": True, "password": None})
        assert response.status in (409, 503)
