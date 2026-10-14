"""Shared native shell contracts, including deliberately incomplete HA sources."""

import copy

import pytest
from homestarter.surfaces import admitted, card_for, classify, generate, preferences
from test_surfaces import household, inventory, items


def cards(value):
    if isinstance(value, dict):
        if "type" in value:
            yield value
        for child in value.values():
            yield from cards(child)
    elif isinstance(value, list):
        for child in value:
            yield from cards(child)


def generated(house, policy=None):
    return generate(house, house["surfaces"][0], items(house), inventory()[0]["areas"], policy=policy)["config"]


@pytest.mark.parametrize("count", [0, 1, 5, 12, 50])
@pytest.mark.parametrize("profile", ["phone", "tablet", "specialist"])
def test_people_navigation_is_unbounded_stable_and_rooms_are_contextual(count, profile):
    house = household(profile)
    house["people"] = [{"id": f"p{n}", "name": f"Person {count - n}", "audience": "adult"} for n in range(count)]
    house["surfaces"][0]["person_id"] = None
    original = copy.deepcopy(house)
    config = generated(house)
    main = [v for v in config["views"] if not v.get("subview")]
    assert [v["title"] for v in main] == ["House"] + [p["name"] for p in house["people"]]
    assert main[0]["path"] == "home"
    assert all(v["path"].startswith("person-") for v in main[1:])
    assert config == generated(house) and house == original
    paths = {v["path"] for v in config["views"]}
    assert len(paths) == len(config["views"])
    assert all(v.get("subview") for v in config["views"] if "room" in v["path"])
    for card in cards(config):
        if card.get("tap_action", {}).get("action") == "navigate":
            assert card["tap_action"]["navigation_path"].rsplit("/", 1)[1] in paths


@pytest.mark.parametrize("profile,columns,climate_type", [("phone", 1, "tile"), ("tablet", 3, "tile"), ("specialist", 1, "thermostat")])
def test_shared_components_with_profile_emphasis(profile, columns, climate_type):
    config = generated(household(profile))
    home = config["views"][0]
    assert home["max_columns"] == columns
    climate = next(c for c in cards(home) if c.get("entity") == "climate.kitchen")
    assert climate["type"] == climate_type
    detail = next(v for v in config["views"] if v["path"] == "climate")
    assert detail["subview"] and detail["back_path"].endswith("/home")
    assert any(c.get("entity") == "climate.kitchen" for c in cards(detail))


def test_absent_features_do_not_generate_placeholder_blocks():
    house = household()
    config = generate(house, house["surfaces"][0], [], [])["config"]
    assert not any(v["title"] in ("Climate", "Today", "Music", "Call", "Door / Cameras") for v in config["views"])
    assert "No available household sources yet" in str(config)
    assert "custom:" not in str(config)


def test_valid_person_ids_cannot_collide_with_contextual_routes():
    house = household("tablet")
    house["people"] += [
        {"id": "alex-" + suffix, "name": suffix, "audience": "adult"}
        for suffix in ("climate", "rooms", "today", "music", "context", "other-controls", "room-0f03ed373b")
    ]
    config = generated(house)
    paths = [v["path"] for v in config["views"]]
    assert len(paths) == len(set(paths))
    assert len([v for v in config["views"] if not v.get("subview")]) == 9


@pytest.mark.parametrize(
    "features,modes,fans,expected",
    [
        (0, [], [], []),
        (0, ["off", "fan_only"], ["high"], ["climate-hvac-modes"]),
        (1, [], [], ["target-temperature"]),
        (2, ["off", "heat_cool"], [], ["target-temperature", "climate-hvac-modes"]),
        (9, ["off", "cool"], ["auto", "diffuse"], ["target-temperature", "climate-hvac-modes", "climate-fan-modes"]),
        (8, [], [], []),
    ],
)
def test_climate_features_are_gated_by_actual_capabilities(features, modes, fans, expected):
    item = next(i for i in items() if i["domain"] == "climate")
    item["attributes"] = {"supported_features": features, "hvac_modes": modes, "fan_modes": fans}
    card = card_for(item, household()["surfaces"][0])
    assert [f["type"] for f in card.get("features", [])] == expected
    assert card["entity"] == item["entity_id"]
    assert "perform-action" not in str(card)
    if "climate-hvac-modes" in expected:
        assert next(f for f in card["features"] if f["type"] == "climate-hvac-modes")["hvac_modes"] == modes


def test_airtouch_all_zones_admitted_by_registry_platform_dampers_are_information_only():
    inv, states = inventory()
    for n in range(9):
        for domain in ("climate", "cover"):
            entity = f"{domain}.arbitrary_{n}"
            inv["unattached_entities"].append(
                {"entity_id": entity, "name": "Unrelated label", "state": "off", "observed": True, "platform": "airtouch5", "area_id": f"elsewhere{n}"}
            )
            states.append(
                {
                    "entity_id": entity,
                    "attributes": {"device_class": "damper"} if domain == "cover" else {"hvac_modes": ["off", "fan_only"], "supported_features": 401},
                }
            )
    house = household("specialist")
    classified = classify(inv, states, {})
    config = generate(house, house["surfaces"][0], classified, inv["areas"])["config"]
    detail = next(v for v in config["views"] if v["path"] == "climate")
    for n in range(9):
        assert f"climate.arbitrary_{n}" in str(detail) and f"cover.arbitrary_{n}" in str(detail)
    damper = next(c for c in cards(detail) if c.get("entity") == "cover.arbitrary_0")
    assert damper["state_content"] == ["state", "current_position"]
    assert damper["tap_action"] == {"action": "none"} and "features" not in damper
    unrelated = next(i for i in classified if i["id"] == "climate.arbitrary_0")
    unrelated["platform"] = "other"
    assert not admitted(unrelated, house["surfaces"][0], house, preferences(house, house["surfaces"][0]))


def test_expanded_climate_puts_system_before_alphabetically_earlier_zones():
    house = household("tablet")
    classified = items(house)
    main = next(i for i in classified if i["domain"] == "climate")
    main["name"] = "Whole system"
    main["attributes"].update(fan_modes=["auto"], supported_features=9)
    zone = {
        **main,
        "id": "climate.zone",
        "entity_id": "climate.zone",
        "name": "A zone",
        "attributes": {"supported_features": 1, "hvac_modes": ["off", "fan_only"]},
    }
    config = generate(house, house["surfaces"][0], [zone] + classified, inventory()[0]["areas"])["config"]
    detail = next(v for v in config["views"] if v["path"] == "climate")
    controls = [c for c in cards(detail) if c.get("entity", "").startswith("climate.")]
    assert [c["entity"] for c in controls] == [main["entity_id"], zone["entity_id"]]


def test_person_pages_never_elevate_physical_audience_and_children_favour_configured_room():
    house = household("tablet")
    house["surfaces"][0].update(person_id=None, audience="adult")
    house["people"] += [{"id": "child", "name": "Child", "audience": "everyone"}]
    house["surfaces"].append({**house["surfaces"][0], "id": "child-phone", "person_id": "child", "area_id": "bedroom"})
    config = generated(house)
    child_path = next(v["path"] for v in config["views"] if v["title"] == "Child" and not v.get("subview"))
    child_views = [v for v in config["views"] if v["path"].startswith(child_path)]
    assert "light.bedroom" in str(child_views) and "light.kitchen" not in str(child_views)
    assert "lock.front" not in str(child_views)
    house["surfaces"][0]["audience"] = "everyone"
    assert "lock.front" not in str(generated(house))


def test_person_hide_order_and_safety_hold_across_context_and_lifecycle_views():
    house = household("tablet")
    house["preferences"]["alex"] = {"pin": ["light.bedroom"], "hide": ["light.kitchen", "binary_sensor.leak"], "order": ["room:bedroom", "room:kitchen"]}
    config = generated(house)
    assert "light.kitchen" not in str(config)
    for v in config["views"]:
        assert "binary_sensor.leak" in str(v)
    ambient = next(v for v in config["views"] if v["path"] == "ambient")
    dark = next(v for v in config["views"] if v["path"] == "dark")
    assert dark["background"]["color"] == "#000000"
    assert "Wake" in str(dark) and "/home" in str(dark)
    assert "thermostat" not in str(ambient) and "media-control" not in str(ambient)
    assert not any(c.get("entity", "").startswith("light.") for c in cards(ambient))
    assert all(c.get("icon_tap_action", {}).get("action") != "toggle" for c in cards(dark))


def test_calendar_uses_admitted_ha_sources_and_no_external_aggregation():
    house = household("tablet")
    assert "calendar.family" not in str(generated(house))
    policy = {"calendars": ["calendar.family"], "calendars_screens": ["phone"]}
    config = generated(house, policy)
    today = next(v for v in config["views"] if v["path"] == "today")
    assert any(c.get("entities") == ["calendar.family"] for c in cards(today))
    assert "https://" not in str(config)
    house["preferences"]["alex"] = {"pin": [], "hide": ["calendar.family"], "order": []}
    assert "calendar.family" not in str(generated(house, policy))


def test_unplaced_opening_exceptions_remain_prominent_and_hide_is_respected():
    inv, states = inventory()
    inv["unattached_entities"].append({"entity_id": "binary_sensor.front_door", "name": "Front door", "state": "on", "observed": True})
    states.append({"entity_id": "binary_sensor.front_door", "state": "on", "attributes": {"device_class": "door"}})
    house = household("tablet")
    config = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"])["config"]
    for page in [v for v in config["views"] if not v.get("subview")]:
        active = next(s for s in page["sections"] if s["cards"][0]["heading"] == "Happening now")
        assert any(c.get("conditions") == [{"condition": "state", "entity": "binary_sensor.front_door", "state": "on"}] for c in cards(active))
    house["preferences"]["alex"] = {"pin": [], "hide": ["binary_sensor.front_door"], "order": []}
    hidden = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"])["config"]
    assert "binary_sensor.front_door" not in str(hidden)
