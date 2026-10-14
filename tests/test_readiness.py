"""Synthetic households prove question selection, source admission and honest readiness."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import readiness as r
from homestarter.household import HouseholdStore, empty_household
from homestarter.server import K_STATE, create_app
from homestarter.surfaces import classify, generate
from test_touch import cards

SCENARIOS = {
    "complex_family": (
        2,
        3,
        ["hassio", "music_assistant", "cast", "airtouch5", "shelly", "camera", "calendar"],
        {"music", "climate", "cameras", "calendars", "lighting"},
    ),
    "apartment": (2, 0, ["light", "cast", "google_assistant"], {"music", "voice", "lighting"}),
    "fresh_family": (2, 2, ["light", "switch", "tuya"], {"lighting"}),
    "enthusiast": (1, 0, ["media_player", "asterisk", "camera", "zha", "esphome"], {"music", "communications", "cameras", "lighting"}),
    "minimal": (1, 0, ["light", "conversation"], {"lighting"}),
}


def scenario(name):
    adults, children, integrations, asked = SCENARIOS[name]
    house = empty_household()
    house["people"] = [{"id": f"adult{n}", "name": f"Adult {n}", "audience": "adult"} for n in range(1, adults + 1)] + [
        {"id": f"child{n}", "name": f"Child {n}", "audience": "everyone"} for n in range(1, children + 1)
    ]
    profiles = ["wall", "tablet", "phone"] if name == "complex_family" else ["phone"]
    house["surfaces"] = [{"id": p, "name": "Example " + p, "profile": p, "person_id": None, "area_id": "room1", "audience": "everyone"} for p in profiles]
    areas = [{"area_id": f"room{n}", "name": f"Bedroom {n}"} for n in range(1, max(2, children) + 1)]
    inv = {
        "complete": True,
        "devices": [],
        "unattached_entities": [],
        "areas": areas,
        "integrations": [{"domain": d, "entry_id": "example-" + d, "state": "loaded"} for d in integrations],
    }
    states = []

    def add(entity, platform, attributes=None, area="room1", state="off"):
        inv["unattached_entities"].append(
            {
                "entity_id": entity,
                "name": "Example " + entity.split(".")[0],
                "platform": platform,
                "registry_id": "registry-" + entity,
                "observed": True,
                "area_id": area,
                "state": state,
            }
        )
        states.append({"entity_id": entity, "state": state, "attributes": attributes or {}})

    add("light.example", "shelly" if "shelly" in integrations else "esphome")
    if any(i in integrations for i in ("cast", "music_assistant", "media_player")):
        add("media_player.example", "music_assistant" if "music_assistant" in integrations else "cast", state="idle")
    if "airtouch5" in integrations:
        add("climate.example", "airtouch5", {"supported_features": 1, "hvac_modes": ["off", "heat"]}, state="heat")
    if "camera" in integrations:
        add("camera.example", "example_camera", state="idle")
        add("event.example_doorbell", "example_camera", {"device_class": "doorbell"}, state="2026-01-01T00:00:00+00:00")
    if "calendar" in integrations:
        add("calendar.example", "google", area=None)
    # A registry device with no room is unresolved even when its native light works.
    device = {
        "id": "device-unassigned",
        "name": "Example unassigned device",
        "area_id": None,
        "status": "attention",
        "entities": [],
        "connection_fingerprint": "example-connection",
    }
    inv["devices"].append(device)
    return house, inv, states, asked


def choice(intent="wanted", sources=(), screens=("phone",), answers=None, permissions=None):
    return {"intent": intent, "sources": list(sources), "screens": list(screens), "answers": answers or {}, "permissions": permissions or {}}


def body(value):
    return {k: copy.deepcopy(value[k]) for k in ("revision", "epoch", "choices", "members", "devices")}


@pytest.mark.parametrize("name", SCENARIOS)
async def test_household_scenario_discover_ask_record_configure_verify_revisit(name, tmp_path):
    house, inv, states, expected_questions = scenario(name)
    store = HouseholdStore(str(tmp_path))
    saved_house = store.save(house)
    initial = r.empty(saved_house["epoch"])
    music = {"state": "ready" if name == "complex_family" else "available"}
    report = r.report(saved_house, initial, inv, states, music)
    rows = {row["id"]: row for row in report["rows"]}
    assert {key for key in r.CAPABILITIES if rows[key]["questions"]} == expected_questions
    assert not rows["waste"]["questions"] and not rows["waste"]["lifecycle"]["verify"]
    assert not rows["communications"]["lifecycle"]["configure"]
    assert "1 unassigned" in rows["rooms"]["status"]
    if "music" in expected_questions:
        assert any("providers" in q for q in rows["music"]["questions"])
        assert initial["choices"] == {}  # No Spotify or service is presumed.
    request = body(initial)
    request["members"] = {
        p["id"]: {"kind": "adult" if p["audience"] == "adult" else "child", "rooms": ["room1"], "devices": [], "presence": [], "access": "later"}
        for p in house["people"]
    }
    for key in expected_questions:
        request["choices"][key] = choice(
            sources=[s["id"] for s in rows[key]["sources"]],
            answers={"providers": ["spotify" if name in ("complex_family", "apartment") else "local"]} if key == "music" else {},
        )
    if name == "enthusiast":
        request["choices"]["communications"]["answers"] = {"service": ["existing"], "uses": ["internal"]}
    saved = r.save(store, saved_house, request, inv, states)
    assert r.load(HouseholdStore(str(tmp_path)), saved_house) == saved
    assert store.load() == saved_house  # Plans do not create HA users/devices/screens.
    later = r.report(saved_house, saved, inv, states, music)
    assert next(row for row in later["rows"] if row["id"] == "household")["status"] == "Context recorded"
    assert all(not row.get("lifecycle", {}).get("verify") for row in later["rows"])
    if "music" in saved["choices"]:
        assert "unverified" in next(row for row in later["rows"] if row["id"] == "music")["status"]
    if "communications" in saved["choices"]:
        assert saved["choices"]["communications"]["permissions"] == {}
        assert "incomplete" in next(row for row in later["rows"] if row["id"] == "communications")["status"]
        deferred = body(saved)
        deferred["choices"]["communications"]["intent"] = "later"
        saved = r.save(store, saved_house, deferred, inv, states)
        comms = next(row for row in r.report(saved_house, saved, inv, states, music)["rows"] if row["id"] == "communications")
        assert comms["status"] == "Not now · deferred" and not comms["questions"]
    policy = r.policy_for(saved, saved_house, inv, states)
    for screen in house["surfaces"]:
        dashboard = generate(saved_house, screen, classify(inv, states, {}), inv["areas"], policy=policy)
        assert "calendar.example" not in str(dashboard["config"]) and "Bins" not in str(dashboard["config"])
        admitted = {item["entity_id"] for item in dashboard["admitted"]}
        assert all(card.get("entity") in admitted for card in cards(dashboard["config"]) if card.get("entity"))
        assert all(item.get("evidence", {}).get("entity_id") == item["entity_id"] for item in dashboard["admitted"] if not item["id"].startswith("alert:"))
    request = body(saved)
    request["devices"]["device-unassigned"] = "ignored"
    saved = r.save(store, saved_house, request, inv, states)
    assert not r.report(saved_house, saved, inv, states, music)["unassigned"]


class CalendarCore:
    def __init__(self, events):
        self.events, self.calls = events, []

    async def rest_get(self, path):
        self.calls.append(path)
        return self.events


async def test_bins_require_real_event_explicit_display_and_repeat_safe_proof(tmp_path):
    house, inv, states, _ = scenario("complex_family")
    inv["unattached_entities"][-1]["name"] = "Example Bins"
    store = HouseholdStore(str(tmp_path))
    house = store.save(house)
    value = r.empty(house["epoch"])
    value["choices"]["waste"] = choice(sources=["calendar.example"])
    value = r.save(store, house, body(value), inv, states)
    assert not r.policy_for(value, house, inv, states).get("waste")
    for events in (
        [],
        [{"summary": "Example collection", "start": {"date": "not-a-date"}}],
        [{"summary": "Example collection", "start": {"date": "2000-01-01"}}],
        [{"summary": "Example birthday", "start": {"date": (datetime.now(UTC) + timedelta(days=1)).date().isoformat()}}],
    ):
        with pytest.raises(ValueError, match="upcoming"):
            await r.verify(CalendarCore(events), value, "waste", inv, states)
    event = {"summary": "Example recycling collection", "start": {"date": (datetime.now(UTC) + timedelta(days=1)).date().isoformat()}}
    core = CalendarCore([event])
    verified = await r.verify(core, value, "waste", inv, states)
    store.write(store.readiness_path, verified)
    assert "summary" not in store.readiness_path.read_text() and "recycling collection" not in store.readiness_path.read_text()
    policy = r.policy_for(verified, house, inv, states)
    assert policy["waste"] == ["calendar.example"]
    for screen in house["surfaces"]:
        config = generate(house, screen, classify(inv, states, {}), inv["areas"], policy=policy)["config"]
        assert ("calendar.example" in str(config)) == (screen["id"] == "phone")
    repeated = r.save(store, house, body(verified), inv, states)
    assert repeated == verified
    inv["unattached_entities"][-1]["registry_id"] = "replacement-registry"
    assert not r.policy_for(verified, house, inv, states).get("waste")


def test_presence_requires_membership_and_per_display_choice(tmp_path):
    house, inv, states, _ = scenario("minimal")
    entity = {"entity_id": "person.example", "registry_id": "example-person", "name": "Adult 1", "observed": True, "state": "home", "area_id": None}
    inv["unattached_entities"].append(entity)
    states.append({"entity_id": entity["entity_id"], "state": "home", "attributes": {}})
    value = r.empty(0)
    value["choices"]["presence"] = choice(sources=[entity["entity_id"]])
    assert not r.policy_for(value, house, inv, states)["presence"]
    value["members"]["adult1"] = {"kind": "adult", "rooms": [], "devices": [], "presence": [entity["entity_id"]], "access": "no"}
    policy = r.policy_for(value, house, inv, states)
    assert "person.example" in str(generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"], policy=policy)["config"])
    house["people"] = []
    assert not r.policy_for(value, house, inv, states)["presence"]
    assert len([v for v in generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"])["config"]["views"] if not v.get("subview")]) == 1


def test_explicit_child_call_plan_never_inherits_adult_destinations(tmp_path):
    house, inv, states, _ = scenario("complex_family")
    store = HouseholdStore(str(tmp_path))
    value = r.empty(0)
    value["choices"]["communications"] = choice(permissions={"adult1": ["adult2"]})
    saved = r.save(store, house, body(value), inv, states)
    assert all(child["id"] not in saved["choices"]["communications"]["permissions"] for child in house["people"] if child["audience"] != "adult")
    broken = body(saved)
    broken["choices"]["communications"]["answers"]["password"] = ["example-invalid-secret"]
    with pytest.raises(ValueError, match="credentials"):
        r.save(store, house, broken, inv, states)


async def test_readiness_api_is_private_guarded_persistent_and_reset_invalidates_it(make_env):
    env = await make_env("ready")
    app = create_app(env.settings, env.session)
    client = TestClient(TestServer(app))
    await client.start_server()
    headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
    try:
        assert (await client.get("/api/readiness")).status == 403
        initial = await (await client.get("/api/readiness", headers=headers)).json()
        request = body(initial["state"])
        request["choices"]["communications"] = choice(intent="later", screens=[])
        response = await client.post("/api/readiness/save", json=request, headers=headers)
        assert response.status == 200
        saved = await response.json()
        assert app[K_STATE].household.load()["configured"]
        assert (await client.post("/api/readiness/save", json=request, headers=headers)).status == 409
        again = await (await client.get("/api/readiness", headers=headers)).json()
        assert again["state"] == saved["state"]
        assert "SIP" not in str(next(row for row in again["rows"] if row["id"] == "communications")["questions"])
        store = app[K_STATE].household
        store.reset(store.load()["revision"])
        reset = await (await client.get("/api/readiness", headers=headers)).json()
        assert reset["state"]["choices"] == {} and reset["state"]["epoch"] == 1
        assert store.read(store.reset_path, {})["readiness"] == saved["state"]
    finally:
        await client.close()


@pytest.mark.parametrize("profile", ["phone", "tablet", "specialist", "kitchen", "entry", "bedside", "wall"])
def test_every_fresh_profile_omits_bins_calendars_and_unlinked_presence(profile):
    house, inv, states, _ = scenario("complex_family")
    screen = {**house["surfaces"][0], "profile": profile}
    inv["unattached_entities"][-1]["name"] = "Example Bins"
    config = generate(house, screen, classify(inv, states, {}), inv["areas"])["config"]
    assert "calendar.example" not in str(config) and "Bins" not in str(config)


async def test_unsupported_verification_cannot_mark_music_or_calling_complete():
    house, inv, states, _ = scenario("complex_family")
    value = r.empty(0)
    value["choices"]["music"] = choice(sources=["media_player.example"], answers={"providers": ["spotify"]})
    with pytest.raises(ValueError, match="not supported"):
        await r.verify(CalendarCore([]), value, "music", inv, states)
    assert value["verified"] == {}
    value["choices"]["communications"] = choice()
    with pytest.raises(ValueError):
        await r.verify(CalendarCore([]), value, "communications", inv, states)
    assert not next(row for row in r.report(house, value, inv, states, {"state": "ready"})["rows"] if row["id"] == "music")["lifecycle"]["configure"]


def test_ignore_and_capability_opt_out_hide_controls_but_preserve_safety():
    house, inv, states, _ = scenario("minimal")
    alarm = {
        "entity_id": "alarm_control_panel.example",
        "name": "Example alarm",
        "state": "triggered",
        "observed": True,
        "device_id": "device-unassigned",
        "area_id": None,
    }
    inv["devices"][0]["entities"] = [alarm]
    states.append({"entity_id": alarm["entity_id"], "state": "triggered", "attributes": {}})
    value = r.empty(0)
    value["devices"]["device-unassigned"] = "ignored"
    value["choices"]["lighting"] = choice(intent="not_wanted")
    result = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"], policy=r.policy_for(value, house, inv, states))
    assert "light.example" not in str(result["config"])
    assert any(item["id"] == "alert:alarm_control_panel.example" for item in result["admitted"])


def test_child_context_caps_existing_adult_audience_without_rewriting_settings():
    house, inv, states, _ = scenario("minimal")
    house["surfaces"][0].update(person_id="adult1", audience="adult")
    source = {"entity_id": "lock.example", "name": "Example lock", "state": "locked", "observed": True, "area_id": "room1"}
    inv["unattached_entities"].append(source)
    states.append({"entity_id": source["entity_id"], "state": "locked", "attributes": {}})
    value = r.empty(0)
    value["members"]["adult1"] = {"kind": "child", "rooms": [], "devices": [], "presence": [], "access": "no"}
    original = copy.deepcopy(house)
    config = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"], policy=r.policy_for(value, house, inv, states))["config"]
    assert "lock.example" not in str(config) and house == original


@pytest.mark.parametrize("music_state", ["unavailable", "stopped", "ready"])
def test_music_questions_require_evidence_and_preserve_health(music_state):
    house, inv, states, _ = scenario("minimal")
    value = r.empty(0)
    music = {"state": music_state}
    row = next(row for row in r.report(house, value, inv, states, music)["rows"] if row["id"] == "music")
    assert bool(row["questions"]) == (music_state != "unavailable")
    assert not row["lifecycle"]["verify"]
    value["choices"]["music"] = choice()
    row = next(row for row in r.report(house, value, inv, states, music)["rows"] if row["id"] == "music")
    assert {"unavailable": "unavailable", "stopped": "stopped", "ready": "unverified"}[music_state] in row["status"]


@pytest.mark.parametrize("domain,state", [("light", "off"), ("alarm_control_panel", "triggered")])
def test_demo_entities_never_supply_household_content(domain, state):
    house, inv, states, _ = scenario("minimal")
    inv["unattached_entities"][0]["platform"] = "demo"
    inv["unattached_entities"][0].update(entity_id=domain + ".example", state=state)
    states[0].update(entity_id=domain + ".example", state=state)
    assert not any(r.discover(inv, states).values())
    config = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"])["config"]
    assert domain + ".example" not in str(config)


@pytest.mark.parametrize("field", ["revision", "epoch"])
def test_readiness_rejects_boolean_metadata(field, tmp_path):
    house, inv, states, _ = scenario("minimal")
    request = body(r.empty(0))
    request[field] = False
    with pytest.raises(ValueError, match="Refresh"):
        r.save(HouseholdStore(str(tmp_path)), house, request, inv, states)
