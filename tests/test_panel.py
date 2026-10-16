"""Fictional household configuration; actual rendering is checked on disposable HA."""

import copy
import json

import pytest
from homestarter.household import empty_household, validate_household
from homestarter.panel import resource_ready
from homestarter.surfaces import classify, generate, publish


def fixture(state="cool", disabled=None, hidden=None):
    house = empty_household()
    house["people"] = [{"id": "example", "name": "Example person", "audience": "adult"}]
    surface = {"id": "example_panel", "name": "Example panel", "profile": "specialist", "area_id": "kitchen", "person_id": None, "audience": "everyone"}
    house["surfaces"] = [surface]
    entities = [
        {
            "entity_id": "climate.example",
            "name": "Example climate",
            "platform": "airtouch5",
            "observed": True,
            "state": state,
            "disabled_by": disabled,
            "hidden_by": hidden,
            "area_id": "kitchen",
        }
    ]
    inv = {"devices": [], "unattached_entities": entities}
    states = [
        {
            "entity_id": "climate.example",
            "state": state,
            "attributes": {
                "temperature": 22,
                "current_temperature": 21.5,
                "hvac_modes": ["off", "cool", "heat"],
                "fan_modes": ["auto", "high"],
                "supported_features": 393,
            },
        }
    ]
    return house, surface, classify(inv, states, {}), [{"area_id": "kitchen", "name": "Example kitchen"}]


@pytest.mark.parametrize(
    "url,expected",
    [
        ("/hacsfiles/button-card/button-card.js?hacstag=7", True),
        ("/local/button-card.js?v=7", True),
        ("https://example.com/button-card.js", False),
        ("//example.com/local/button-card.js", False),
        ("/local/other.js", False),
    ],
)
def test_only_installed_same_origin_module_is_detected(url, expected):
    assert resource_ready([{"type": "module", "url": url}]) is expected
    assert not resource_ready([{"type": "css", "url": url}])


def test_native_fallback_and_controls_are_preserved_without_household_mutation():
    house, surface, items, areas = fixture()
    before = copy.deepcopy(house)
    native = generate(house, surface, items, areas)
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    assert house == before and native["config"]["views"][0]["type"] == "sections"
    assert panel["config"]["views"][0]["type"] == "panel"
    for view in native["config"]["views"]:
        if view.get("subview"):
            themed = next(v for v in panel["config"]["views"] if v["path"] == view["path"])
            if view["path"] == "climate":
                assert themed["subview"] and themed["back_path"] == view["back_path"]
                controls = [c for s in view["sections"] for c in s["cards"] if c["type"] != "heading"]
                assert themed["cards"][0]["custom_fields"]["system"]["card"] == controls[0]
                assert "#09131b" in themed["cards"][0]["extra_styles"]
            else:
                assert view == themed
    card = panel["config"]["views"][0]["cards"][0]
    assert card["variables"]["panel"]["climate"] == "climate.example"
    assert "call_service" not in json.dumps(card) and "fetch(" not in json.dumps(card)


def test_climate_layout_preserves_native_zone_and_readonly_damper_cards():
    from homestarter.panel import climate_panel

    system = {"type": "thermostat", "entity": "climate.example", "features": [{"type": "climate-hvac-modes"}]}
    zone = {"type": "tile", "entity": "climate.room", "name": "Actual room", "features": [{"type": "target-temperature"}]}
    damper = {"type": "tile", "entity": "cover.room", "tap_action": {"action": "none"}, "icon_tap_action": {"action": "none"}}
    notice = {
        "type": "conditional",
        "conditions": [{"condition": "state", "entity": "binary_sensor.example", "state": "on"}],
        "card": {"type": "tile", "entity": "binary_sensor.example"},
    }
    view = {"path": "climate", "subview": True, "back_path": "/example/home", "sections": [{"cards": [{"type": "heading"}, notice, system, zone, damper]}]}
    climate_panel(view, "fixture CSS")
    fields = view["cards"][0]["custom_fields"]
    assert fields["system"]["card"] == system
    assert fields["rooms"]["card"]["custom_fields"]["control0"]["card"] == zone
    assert fields["airflow"]["card"]["custom_fields"]["control0"]["card"] == damper
    assert fields["notices"]["card"]["cards"] == [notice]
    assert {"display": "block"} in view["cards"][0]["styles"]["card"]
    assert view["subview"] and view["back_path"] == "/example/home"
    assert "sections" not in view


@pytest.mark.parametrize("ambiguous", [False, True])
def test_room_airflow_uses_unique_device_evidence_not_names_or_entity_suffixes(ambiguous):
    from homestarter.panel import climate_panel

    system = {"type": "thermostat", "entity": "climate.system"}
    zone = {
        "type": "tile",
        "entity": "climate.old_name",
        "name": "Different room name",
        "features": [{"type": "target-temperature"}, {"type": "climate-hvac-modes", "hvac_modes": ["off", "fan_only"]}],
    }
    damper = {"type": "tile", "entity": "cover.another_name", "tap_action": {"action": "none"}}
    items = [
        {"entity_id": zone["entity"], "platform": "airtouch5", "evidence": {"device_id": "fixture_zone"}},
        {"entity_id": damper["entity"], "device_class": "damper", "evidence": {"device_id": "fixture_zone"}},
    ]
    cards = [system, zone, damper]
    if ambiguous:
        other = {**zone, "entity": "climate.other"}
        cards.append(other)
        items.append({**items[0], "entity_id": other["entity"]})
    before = copy.deepcopy(cards)
    view = {"path": "climate", "sections": [{"cards": cards}]}
    climate_panel(view, "fixture CSS", items)
    fields = view["cards"][0]["custom_fields"]
    room = fields["rooms"]["card"]["custom_fields"]["control0"]["card"]
    assert cards == before
    if ambiguous:
        assert room == zone and "airflow" in fields
    else:
        assert "airflow" not in fields
        assert room["variables"] == {"zone": zone["entity"], "damper": damper["entity"]}
        controls = room["custom_fields"]["controls"]["card"]
        assert controls["entity"] == zone["entity"] and controls["name"] == ""
        assert controls["features"][1] == zone["features"][0]
        assert controls["features"][0]["hvac_modes"] == ["off", "fan_only"]
        assert controls["features"][0]["style"] == "icons"
        assert "perform_action" not in json.dumps(room)


def test_room_names_are_escaped_and_airflow_cannot_override_the_damper():
    from homestarter.panel import room_panel

    room = room_panel({"type": "tile", "entity": "climate.fixture", "name": "<img src=x>"}, {"entity": "cover.fixture"})
    assert room["name"] == "&lt;img src=x&gt;"
    assert room["triggers_update"] == ["climate.fixture", "cover.fixture"]
    assert "current_position" in room["custom_fields"]["airflow"]
    assert "% open" in room["custom_fields"]["airflow"]
    assert "set_cover_position" not in json.dumps(room)
    assert "Number.isFinite" in room["custom_fields"]["current"]


@pytest.mark.parametrize("state", ["unavailable", "unknown"])
def test_offline_known_climate_retains_native_controls_and_reports_missing_temperature(state):
    house, surface, items, areas = fixture(state)
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    root = panel["config"]["views"][0]["cards"][0]
    assert root["variables"]["panel"]["climate"] == "climate.example"
    assert any(v["path"] == "climate" for v in panel["config"]["views"])
    assert "Connection unavailable" in root["custom_fields"]["panel"]


@pytest.mark.parametrize("disabled,hidden", [("user", None), (None, "user")])
def test_offline_shell_never_readmits_disabled_or_hidden_climate(disabled, hidden):
    house, surface, items, areas = fixture("unavailable", disabled, hidden)
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    assert panel["config"]["views"][0]["cards"][0]["variables"]["panel"]["climate"] is None


def test_hidden_preferences_and_unselected_bin_context_stay_excluded():
    house, surface, items, areas = fixture()
    house["preferences"]["surface:example_panel"] = {"hide": ["climate.example"], "pin": [], "order": []}
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    cfg = panel["config"]["views"][0]["cards"][0]["variables"]["panel"]
    assert cfg["climate"] is None and cfg["bins"] is False


async def test_publication_stops_if_frontend_dependency_is_removed():
    class MissingResource:
        def websocket(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def command(self, command):
            assert command == "lovelace/resources/list"
            return []

    house, surface, items, areas = fixture()
    generated = generate(house, surface, items, areas, policy={"landscape_panel": True})
    with pytest.raises(ValueError, match="no longer registered"):
        await publish(MissingResource(), generated, None, {})


def test_kiosk_is_explicit_and_preserves_legacy_state_and_native_back_paths():
    house, surface, items, areas = fixture()
    before = copy.deepcopy(house)
    assert validate_household(house) == before and "kiosk" not in surface
    surface["kiosk"] = True
    assert validate_household(house)["surfaces"][0]["kiosk"] is True
    with pytest.raises(ValueError, match="dedicated"):
        generate(house, surface, items, areas, policy={"landscape_panel": True})
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True, "kiosk_user_name": "Fixture panel"})
    assert "!user_is_admin" in panel["config"]["kiosk_mode"]["hide_header"]
    assert "panel_url" in panel["config"]["kiosk_mode"]["hide_header"]
    assert "/settings" in panel["config"]["kiosk_mode"]["hide_sidebar"]
    settings = next(v for v in panel["config"]["views"] if v["path"] == "settings")
    assert settings["subview"] and settings["back_path"].endswith("/home")
    assert settings["sections"][0]["cards"][1]["tap_action"]["action"] == "navigate"
    assert panel["config"]["views"][1]["subview"]
    assert all(v.get("back_path") for v in panel["config"]["views"] if v.get("subview"))
    surface["kiosk"] = "yes"
    with pytest.raises(ValueError, match="Kiosk"):
        validate_household(house)


async def test_removed_kiosk_dependency_stops_before_dashboard_writes():
    class NoKiosk:
        def websocket(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def command(self, command):
            assert command == "lovelace/resources/list"
            return [{"url": "/local/button-card.js", "type": "module"}]

    house, surface, items, areas = fixture()
    surface["kiosk"] = True
    generated = generate(house, surface, items, areas, policy={"landscape_panel": True, "kiosk_user_name": "Fixture display"})
    with pytest.raises(ValueError, match="Kiosk Mode"):
        await publish(NoKiosk(), generated, None, {})


async def test_kiosk_preview_requires_installed_modules_and_suitable_unique_bound_account(make_env, monkeypatch):
    from aiohttp.test_utils import TestClient, TestServer
    from homestarter.household import HouseholdStore
    from homestarter.server import create_app
    from homestarter.surfaces import fingerprint

    env = await make_env("ready")
    store = HouseholdStore(env.settings.data_dir)
    house, surface, _, _ = fixture()
    surface["kiosk"] = True
    current = store.load()
    house.update(revision=current["revision"], epoch=current["epoch"])
    house = store.save(house)
    user = {
        "id": "fixture_display",
        "name": "Example panel",
        "username": "example_panel",
        "is_owner": False,
        "is_active": True,
        "local_only": True,
        "system_generated": False,
        "group_ids": ["system-users"],
        "credentials": [{"type": "homeassistant"}],
    }
    env.mock.users.append(user)
    modules = ["button-card", "kiosk-mode"]
    original = env.mock._fake_ws_result

    def result(message):
        if message["type"] == "lovelace/resources/list":
            return [{"type": "module", "url": f"/local/{module}.js"} for module in modules]
        return original(message)

    monkeypatch.setattr(env.mock, "_fake_ws_result", result)
    path = "home-starter-example-panel"
    config = {"views": [{"title": "Existing", "path": "home", "cards": []}]}
    env.mock.dashboards.append({"url_path": path})
    env.mock.dashboard_configs[path] = config
    store.write(store.publication_path, {path: {"fingerprint": fingerprint(config)}})
    before_house, before_publication = store.path.read_bytes(), store.publication_path.read_bytes()
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        route = "/api/surfaces/example_panel/preview"
        assert (await client.get(route, headers=headers)).status == 409
        identity = await (await client.get("/api/screens/identity", headers=headers)).json()
        response = await client.post(
            "/api/screens/identity",
            headers=headers,
            json={
                "revision": identity["revision"],
                "epoch": identity["epoch"],
                "surface": surface["id"],
                "action": "select",
                "confirm": True,
                "user_id": user["id"],
                "permission": "control",
            },
        )
        assert response.status == 200
        response = await client.get(route, headers=headers)
        assert response.status == 200, await response.text()
        preview = await response.json()
        assert user["name"] in preview["config"]["kiosk_mode"]["hide_header"]
        env.mock.users.append({**user, "id": "fixture_duplicate"})
        assert (await client.get(route, headers=headers)).status == 409
        env.mock.users.pop()
        user["group_ids"] = ["system-admin"]
        assert (await client.get(route, headers=headers)).status == 409
        user["group_ids"] = ["system-users"]
        modules.remove("kiosk-mode")
        assert (await client.get(route, headers=headers)).status == 409
    assert store.path.read_bytes() == before_house
    assert store.publication_path.read_bytes() == before_publication
    assert env.mock.dashboard_configs[path] == config
