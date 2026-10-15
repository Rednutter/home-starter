"""Fictional household configuration; actual rendering is checked on disposable HA."""

import copy
import json

import pytest
from homestarter.household import empty_household
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
            assert view in panel["config"]["views"]
    card = panel["config"]["views"][0]["cards"][0]
    assert card["variables"]["panel"]["climate"] == "climate.example"
    assert "call_service" not in json.dumps(card) and "fetch(" not in json.dumps(card)


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
