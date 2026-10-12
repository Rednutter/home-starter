from __future__ import annotations

import copy
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter.activity import activity_entity, consume, update_activity
from homestarter.core import CoreError
from homestarter.household import HouseholdStore, empty_household, validate_household
from homestarter.server import create_app
from homestarter.surfaces import CATALOGUE, admitted, card_for, classify, fingerprint, generate, preferences, publish


def household(profile="phone", audience="adult"):
    house = empty_household()
    house["people"] = [{"id": "alex", "name": "Alex", "audience": audience}]
    house["surfaces"] = [{"id": "phone", "name": "Home", "profile": profile, "person_id": "alex", "area_id": "kitchen", "audience": "everyone"}]
    return house


def inventory():
    entities = [
        {"entity_id": entity_id, "name": name, "state": state, "area_id": area, "observed": True, "entity_category": category}
        for entity_id, name, state, area, category in (
            ("light.kitchen", "Kitchen lights", "off", "kitchen", None),
            ("climate.kitchen", "Air conditioning", "cool", "kitchen", None),
            ("light.bedroom", "Bedroom", "on", "bedroom", None),
            ("sensor.battery", "Battery", "20", "kitchen", "diagnostic"),
            ("sensor.service_temperature", "Server CPU", "22", "kitchen", "diagnostic"),
            ("sensor.room_temperature", "Kitchen temperature", "21.5", "kitchen", None),
            ("binary_sensor.leak", "Kitchen leak", "off", "kitchen", None),
            ("lock.front", "Front door", "locked", "kitchen", None),
            ("media_player.lounge", "Music", "playing", "bedroom", None),
            ("weather.home", "Weather", "sunny", None, None),
            ("calendar.family", "Family", "off", None, None),
            ("switch.reboot", "Reboot", "on", None, None),
            ("script.goodnight", "Goodnight", "off", None, None),
            ("sensor.washer", "Washer", "idle", "kitchen", None),
        )
    ]
    attributes = {
        "sensor.battery": {"device_class": "battery"},
        "sensor.room_temperature": {"device_class": "temperature"},
        "sensor.service_temperature": {"device_class": "temperature"},
        "binary_sensor.leak": {"device_class": "moisture"},
        "climate.kitchen": {"hvac_action": "cooling"},
    }
    states = [{"entity_id": e["entity_id"], "state": e["state"], "attributes": attributes.get(e["entity_id"], {})} for e in entities]
    return {
        "devices": [],
        "unattached_entities": entities,
        "areas": [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "bedroom", "name": "Bedroom"}],
    }, states


def items(house=None):
    inv, states = inventory()
    return classify(inv, states, (house or household())["overrides"])


def test_model_persists_preferences_separately_and_rejects_stale_save(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = household()
    house["preferences"] = {"alex": {"pin": ["light.kitchen"], "hide": [], "order": []}, "surface:phone": {"pin": [], "hide": ["lock.front"], "order": []}}
    saved = store.save(house)
    assert HouseholdStore(str(tmp_path)).load() == saved
    assert preferences(saved, saved["surfaces"][0])["hide"] == ["lock.front"]
    with pytest.raises(ValueError, match="changed elsewhere"):
        store.save(house)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda h: h["people"].append(h["people"][0]),
        lambda h: h["surfaces"][0].update(profile="desktop"),
        lambda h: h["surfaces"][0].update(person_id="missing"),
        lambda h: h["overrides"].update({"light.kitchen": {"service": "lock.unlock"}}),
        lambda h: h["preferences"].update({"missing": {"pin": [], "hide": [], "order": []}}),
    ],
)
def test_invalid_household_fails_closed(mutation):
    house = household()
    mutation(house)
    with pytest.raises(ValueError):
        validate_household(house)


def test_corrupt_store_is_preserved(tmp_path):
    store = HouseholdStore(str(tmp_path))
    store.path.write_text("broken")
    with pytest.raises(ValueError):
        store.save(household())
    assert store.path.read_text() == "broken"


def test_semantics_diagnostics_and_ambiguous_controls_never_auto_admit():
    classified = {i["id"]: i for i in items()}
    for entity in ("sensor.battery", "sensor.service_temperature", "switch.reboot", "script.goodnight", "sensor.washer"):
        assert classified[entity]["level"] == 5
    assert classified["binary_sensor.leak"]["level"] == 0
    assert classified["sensor.room_temperature"]["function"] == "climate"
    assert classified["lock.front"]["audience"] == "adult"
    assert all(set(i) >= {"scope", "importance", "frequency", "visibility", "interaction", "audience", "surfaces", "area_id"} for i in classified.values())


def test_explicit_actions_work_but_diagnostic_override_cannot_bypass_admin():
    house = household()
    house["overrides"] = {"script.goodnight": {"include": True, "name": "Goodnight"}, "sensor.battery": {"include": True, "audience": "everyone"}}
    classified = {i["id"]: i for i in items(house)}
    assert classified["script.goodnight"]["level"] == 2
    assert classified["sensor.battery"]["audience"] == "admin"
    card = card_for(classified["script.goodnight"], house["surfaces"][0])
    assert card["tap_action"]["target"] == {"entity_id": "script.goodnight"}
    assert card["tap_action"]["confirmation"]


def test_safety_cannot_be_hidden_and_pins_cannot_bypass_audience_or_location():
    house = household("specialist", "everyone")
    house["preferences"]["alex"] = {"pin": ["light.bedroom", "lock.front"], "hide": ["binary_sensor.leak"], "order": []}
    surface = house["surfaces"][0]
    pref = preferences(house, surface)
    eligible = {i["id"] for i in items() if admitted(i, surface, house, pref)}
    assert "binary_sensor.leak" in eligible
    assert "light.bedroom" not in eligible
    assert "lock.front" not in eligible


@pytest.mark.parametrize("profile", ["phone", "tablet", "specialist", "wall", "kitchen", "entry", "bedside"])
def test_all_surface_profiles_generate_native_sections(profile):
    house = household(profile)
    config = generate(house, house["surfaces"][0], items(), inventory()[0]["areas"])["config"]
    assert all(v["type"] == "sections" for v in config["views"])
    assert "custom:" not in str(config)
    assert "sensor.battery" not in str(config)
    assert len([v for v in config["views"] if not v.get("subview")]) <= 5
    if profile == "specialist":
        sections = config["views"][0]["sections"]
        ac = next(s for s in sections if s["cards"][0]["heading"] == "Air conditioning")
        assert ac["cards"][1]["type"] == "thermostat"
    if profile == "wall":
        assert not any(v.get("subview") for v in config["views"])
        assert all(word not in str(config) for word in ("perform-action", "toggle", "thermostat", "media-control", "button", "more-info"))


def test_reorder_and_hide_preserve_control_targets_and_room_privacy():
    house = household()
    house["preferences"]["alex"] = {"pin": ["light.kitchen"], "hide": ["light.bedroom", "lock.front"], "order": ["room:bedroom", "room:kitchen"]}
    config = generate(house, house["surfaces"][0], items(), inventory()[0]["areas"])["config"]
    assert "light.bedroom" not in str(config)
    assert "lock.front" not in str(config)
    assert "sensor.battery" not in str(config)
    light = next(i for i in items() if i["id"] == "light.kitchen")
    card = card_for(light, house["surfaces"][0])
    assert card["entity"] == "light.kitchen" and card["icon_tap_action"] == {"action": "toggle"}
    lock = next(i for i in items() if i["id"] == "lock.front")
    assert card_for(lock, house["surfaces"][0])["icon_tap_action"] == {"action": "more-info"}
    assert "lock.unlock" not in str(config)


def test_catalogue_is_honest_about_absent_sources():
    assert len(CATALOGUE) == 25
    assert CATALOGUE["calling_contact"][1] == "source_required"
    assert CATALOGUE["media_favourites"][1] == "source_required"
    assert CATALOGUE["camera"][1] == "source_required"
    assert CATALOGUE["room_summary"][0] == "vertical-stack"


def test_safety_cannot_be_hidden_by_global_name_inclusion_or_audience():
    inv, states = inventory()
    inv["unattached_entities"].append({"entity_id": "alarm_control_panel.home", "name": "Alarm", "state": "triggered", "observed": True})
    states.append({"entity_id": "alarm_control_panel.home", "state": "triggered", "attributes": {}})
    house = household("kitchen", "everyone")
    house["overrides"] = {
        "binary_sensor.leak": {"include": False, "audience": "admin", "name": "Water leak"},
        "alarm_control_panel.home": {"include": False, "audience": "admin"},
        "light.kitchen": {"include": False},
    }
    classified = classify(inv, states, house["overrides"])
    leak = next(i for i in classified if i["id"] == "binary_sensor.leak")
    assert leak["usable"] is True and leak["audience"] == "everyone"
    generated = generate(house, house["surfaces"][0], classified, inv["areas"])
    ids = {i["id"] for i in generated["admitted"]}
    assert {"binary_sensor.leak", "alert:alarm_control_panel.home"} <= ids
    assert "light.kitchen" not in ids


@pytest.mark.parametrize("profile", ["phone", "tablet", "specialist", "kitchen", "entry", "bedside", "wall"])
def test_shared_security_alarm_is_only_an_informational_interruption(profile):
    inv, states = inventory()
    inv["unattached_entities"].append({"entity_id": "alarm_control_panel.home", "name": "Alarm", "state": "disarmed", "observed": True})
    states.append({"entity_id": "alarm_control_panel.home", "state": "disarmed", "attributes": {}})
    house = household(profile, "everyone")
    generated = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"])
    assert not any(v["title"] == "Security" for v in generated["config"]["views"])
    alert = next(i for i in generated["admitted"] if i["id"] == "alert:alarm_control_panel.home")
    assert alert["interaction"] == "status" and alert["visibility"] == "when_abnormal"
    assert alert["function"] == "safety" and profile in alert["surfaces"]
    assert "alarm_control_panel.home" in str(generated["config"]["views"][0])
    assert "alarm_control_panel.alarm_disarm" not in str(generated["config"])


def test_reviewed_whole_house_action_is_suitable_for_specialist_but_not_wall():
    house = household("specialist")
    house["surfaces"][0]["audience"] = "adult"
    house["overrides"] = {"script.goodnight": {"include": True}}
    classified = items(house)
    action = next(i for i in classified if i["id"] == "script.goodnight")
    assert "specialist" in action["surfaces"] and "wall" not in action["surfaces"]
    generated = generate(house, house["surfaces"][0], classified, inventory()[0]["areas"])
    assert "script.goodnight" in str(generated["config"]["views"][0])
    house["surfaces"][0]["profile"] = "wall"
    wall = generate(house, house["surfaces"][0], classified, inventory()[0]["areas"])
    assert "script.goodnight" not in str(wall["config"])


def test_explicit_whole_house_light_control_is_available_at_entry():
    house = household("entry")
    house["overrides"] = {"light.kitchen": {"scope": "whole_house"}}
    classified = items(house)
    light = next(i for i in classified if i["id"] == "light.kitchen")
    assert "entry" in light["surfaces"]
    generated = generate(house, house["surfaces"][0], classified, inventory()[0]["areas"])
    quick = next(s for s in generated["config"]["views"][0]["sections"] if s["cards"][0]["heading"] == "Quick actions")
    assert any(c.get("entity") == "light.kitchen" for c in quick["cards"])


def test_missing_room_is_not_whole_house_and_has_deliberate_detail_access():
    inv, states = inventory()
    inv["unattached_entities"][0]["area_id"] = None
    classified = classify(inv, states, {})
    light = next(i for i in classified if i["id"] == "light.kitchen")
    assert light["scope"] == "local"
    house = household()
    generated = generate(house, house["surfaces"][0], classified, inv["areas"])
    main = str(generated["config"]["views"][0])
    assert "Other controls" in main and "Quick actions" not in main
    detail = next(v for v in generated["config"]["views"] if v["path"] == "other-controls")
    assert "light.kitchen" in str(detail)
    fixed = household("specialist")
    assert not admitted(light, fixed["surfaces"][0], fixed, preferences(fixed, fixed["surfaces"][0]))
    fixed["preferences"]["alex"] = {"pin": [light["id"]], "hide": [], "order": []}
    assert not admitted(light, fixed["surfaces"][0], fixed, preferences(fixed, fixed["surfaces"][0]))
    house["preferences"]["alex"] = {"pin": [light["id"]], "hide": [], "order": []}
    pinned = generate(house, house["surfaces"][0], classified, inv["areas"])
    assert "Quick actions" in str(pinned["config"]["views"][0])


RULE = {"id": "washer", "name": "Washer", "entity_id": "sensor.washer", "from_state": "running", "to_state": "complete"}


def row(state, when):
    return {"entity_id": "sensor.washer", "state": state, "last_changed": when}


def test_activity_exact_transitions_dedup_restart_and_sydney_midnight():
    start = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)  # Sydney 23:00
    record = consume(RULE, {}, [], "Australia/Sydney", start)
    history = [
        row("running", "2026-10-12T12:10:00Z"),
        row("complete", "2026-10-12T12:20:00Z"),
        row("running", "2026-10-12T12:30:00Z"),
        row("complete", "2026-10-12T12:40:00Z"),
    ]
    record = consume(RULE, record, history, "Australia/Sydney", datetime(2026, 10, 12, 12, 50, tzinfo=UTC))
    assert record["runs_today"] == 2
    # A persisted record and overlapped history must not double count.
    record = consume(RULE, copy.deepcopy(record), history, "Australia/Sydney", datetime(2026, 10, 12, 12, 55, tzinfo=UTC))
    assert record["runs_today"] == 2
    record = consume(RULE, record, history, "Australia/Sydney", datetime(2026, 10, 12, 13, 1, tzinfo=UTC))
    assert record["runs_today"] == 0 and record["last_run"] == "2026-10-12T12:40:00+00:00"


def test_unknown_breaks_completion_and_rule_change_resets_baseline():
    now = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    record = consume(RULE, {}, [], "Australia/Sydney", now)
    history = [row("running", "2026-10-12T10:10:00Z"), row("unavailable", "2026-10-12T10:11:00Z"), row("complete", "2026-10-12T10:12:00Z")]
    later = datetime(2026, 10, 12, 10, 15, tzinfo=UTC)
    record = consume(RULE, record, history, "Australia/Sydney", later)
    assert record["runs_today"] == 0
    changed = dict(RULE, from_state="cleaning")
    assert consume(changed, record, history, "Australia/Sydney", later)["since"] == later.isoformat()


class DashboardCore:
    def __init__(self):
        self.dashboards = []
        self.config = None
        self.calls = []
        self.lie = False

    def websocket(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def command(self, kind, **payload):
        self.calls.append((kind, payload))
        if kind == "lovelace/dashboards/list":
            return self.dashboards
        if kind == "lovelace/dashboards/create":
            self.dashboards.append(payload)
        if kind == "lovelace/config/save" and not self.lie:
            self.config = payload["config"]
        if kind == "lovelace/config":
            return self.config


async def test_publish_readback_and_external_edit_guard():
    core = DashboardCore()
    house = household()
    generated = generate(house, house["surfaces"][0], items(), inventory()[0]["areas"])
    result = await publish(core, generated, None, {})
    assert result["verified"]
    records = {result["url_path"]: result}
    assert await publish(core, generated, result["fingerprint"], records) == result
    core.config = {"title": "External edits"}
    writes = len(core.calls)
    with pytest.raises(ValueError, match="changed"):
        await publish(core, generated, result["fingerprint"], records)
    assert all(c[0] not in ("lovelace/config/save", "lovelace/dashboards/create") for c in core.calls[writes:])
    with pytest.raises(ValueError, match="belongs"):
        await publish(core, generated, None, {})


async def test_publish_success_shaped_no_change_is_not_verified():
    core = DashboardCore()
    core.lie = True
    house = household()
    with pytest.raises(CoreError, match="verified"):
        await publish(core, generate(house, house["surfaces"][0], items(), inventory()[0]["areas"]), None, {})


class ActivityCore:
    def __init__(self):
        self.history = [[row("running", "2026-10-12T10:00:00Z")]]
        self.saved = []
        self.fail = False
        self.extra = []

    async def config(self):
        return {"time_zone": "Australia/Sydney"}

    async def states(self):
        return [row("running", "2026-10-12T10:00:00Z")] + self.extra

    async def rest_get(self, path):
        assert "filter_entity_id=sensor.washer" in path
        if self.fail:
            raise CoreError("api", "No recorder")
        return self.history

    async def activity_state(self, entity_id, payload):
        self.saved.append((entity_id, payload))


async def test_activity_monitor_catches_short_cycle_and_recreates_only_owned_state(tmp_path):
    core, store = ActivityCore(), HouseholdStore(str(tmp_path))
    await update_activity(core, store, [RULE], datetime(2026, 10, 12, 10, 0, tzinfo=UTC))
    core.history[0] += [row("complete", "2026-10-12T10:01:00Z"), row("running", "2026-10-12T10:02:00Z"), row("complete", "2026-10-12T10:03:00Z")]
    result = await update_activity(core, HouseholdStore(str(tmp_path)), [RULE], datetime(2026, 10, 12, 10, 5, tzinfo=UTC))
    assert result[0]["runs_today"] == 2 and result[0]["ran_today"] is True
    core.fail = True
    await update_activity(core, store, [RULE], datetime(2026, 10, 12, 10, 6, tzinfo=UTC))
    assert core.saved[-1][1]["state"] == "unknown"
    core.extra = [{"entity_id": activity_entity(RULE), "attributes": {}, "state": "100"}]
    with pytest.raises(CoreError, match="already in use"):
        await update_activity(core, store, [RULE])


async def test_household_api_admin_revision_and_publish_confirmation(make_env, tmp_path):
    env = await make_env("ready")
    settings = replace(env.settings, data_dir=str(tmp_path))
    app = create_app(settings, env.session)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert (await client.get("/api/household")).status == 403
        assert (await client.get("/api/household", headers={"X-Remote-User-Id": "ordinary"})).status == 403
        headers = {"X-Remote-User-Id": "fixture-user-id"}
        # Mock's actual owner ID is intentional fixture data.
        headers["X-Remote-User-Id"] = env.mock.users[0]["id"]
        assert (await client.get("/api/household", headers=headers)).status == 200
        house = household()
        response = await client.post("/api/household", json=house, headers=headers)
        assert response.status == 200
        assert (await response.json())["household"]["revision"] == 1
        assert (await client.post("/api/household", json=house, headers=headers)).status == 409
        preview = await client.get("/api/surfaces/phone/preview", headers=headers)
        assert preview.status == 200
        assert (await preview.json())["url_path"] == "home-starter-phone"
        assert (await client.post("/api/surfaces/phone/publish", json={"confirm": False}, headers=headers)).status == 400
        assert (await client.post("/api/surfaces/phone/publish", json={"preview_token": "wrong", "confirm": True}, headers=headers)).status == 409
    finally:
        await client.close()


def test_fingerprint_ignores_dictionary_order():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
