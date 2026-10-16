"""Fictional household configuration; actual rendering is checked on disposable HA."""

import copy
import json

import pytest
from homestarter.household import empty_household, validate_household
from homestarter.panel import resource_ready
from homestarter.surfaces import classify, generate, publish


def nested(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested(child)


def detail_card(original):
    if original.get("type") == "button" and original.get("tap_action", {}).get("action") == "navigate":
        return {**original, "icon_height": original.get("icon_height", "40px")}
    if original.get("type") in {"vertical-stack", "horizontal-stack", "grid"}:
        return {**original, "cards": [detail_card(child) for child in original.get("cards", [])]}
    if original.get("type") == "conditional":
        return {**original, "card": detail_card(original["card"])}
    return original


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


def focus_data(panel, view):
    root = json.loads(view["cards"][0]["variables"]["focus_json"])
    scope = json.loads(panel["config"]["button_card_templates"]["home_starter_page"]["variables"]["common_json"])["scopes"][root["scope_key"]]
    result = {**scope, **root}
    result["controls"] = [c for c in scope["controls"] if root.get("control_ids") is None or c["entity_id"] in root["control_ids"]]
    return result


def test_native_fallback_and_controls_are_preserved_without_household_mutation():
    house, surface, items, areas = fixture()
    before = copy.deepcopy(house)
    native = generate(house, surface, items, areas)
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    assert house == before and native["config"]["views"][0]["type"] == "sections"
    assert panel["config"]["views"][0]["type"] == "panel"
    views = {v["path"]: v for v in panel["config"]["views"]}
    for view in native["config"]["views"]:
        if view["path"] in {"ambient", "dark"}:
            assert json.loads(views[view["path"]]["cards"][0]["variables"]["focus_json"])["kind"] == view["path"]
        elif view.get("subview"):
            focused = views[view["path"]]
            assert focused["subview"] and focused["back_path"]
            assert focused["cards"][0]["template"] == "home_starter_page"
            if view["path"] == "climate":
                original = [c for section in view["sections"] for c in section["cards"] if c["type"] != "heading"]
                nested_climate = focused["cards"][0]["custom_fields"]["body"]
                assert nested_climate["do_not_eval"] is True
                assert nested_climate["card"]["custom_fields"]["system"]["card"] == original[0]
                assert "#0b1013" in nested_climate["card"]["extra_styles"]


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


def test_all_overview_destinations_exist_without_sources_and_people_keep_their_boundary():
    house, surface, items, areas = fixture()
    native = generate(house, surface, items, areas)
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    views = {view["path"]: view for view in panel["config"]["views"]}
    targets = views["home"]["cards"][0]["variables"]["panel"]["targets"]
    assert {"today", "rooms", "music", "context", "call", "cameras"} <= targets.keys()
    for target in targets.values():
        assert target.rsplit("/", 1)[1] in views
    assert json.loads(views["rooms"]["cards"][0]["variables"]["focus_json"])["kind"] == "rooms"
    assert focus_data(panel, views["music"])["players"] == []
    assert not any(card.get("entity", "").startswith(("camera.", "media_player.")) for card in nested(panel["config"]))
    for view in native["config"]["views"]:
        if not view["path"].startswith("person-"):
            continue
        themed = views[view["path"]]
        assert themed["subview"]
        expected_back = view.get("back_path", "/" + panel["url_path"] + "/home")
        if "-room-" in view["path"]:
            expected_back += "-rooms"
        assert themed["back_path"] == expected_back
        focus = focus_data(panel, themed)
        assert {c["entity_id"] for c in focus["controls"]} <= {i["entity_id"] for i in panel["admitted"]}
        assert focus["owner"] == house["people"][0]["id"]


def test_details_preserve_selected_bin_expiry_and_section_visibility():
    from homestarter.panel import detail_panel
    from homestarter.waste import card

    bins = card()
    view = {"title": "Today", "path": "today", "sections": [{"visibility": bins["conditions"], "cards": [bins]}]}
    detail_panel(view, "fixture CSS")
    assert bins in list(nested(view))
    assert any(c.get("type") == "conditional" and c.get("conditions") == bins["conditions"] for c in nested(view))
    house, surface, items, areas = fixture()
    for selected in (False, True):
        panel = generate(house, surface, items, areas, policy={"landscape_panel": True, "bin_context_screens": [surface["id"]] if selected else []})
        today = next(v for v in panel["config"]["views"] if v["path"] == "today")
        assert json.loads(today["cards"][0]["variables"]["focus_json"])["bins"] is selected


def test_populated_details_use_focused_media_context_and_feature_controls():
    house, surface, items, areas = fixture()
    states = [
        {"entity_id": "calendar.example", "state": "off", "attributes": {}},
        {"entity_id": "media_player.example", "state": "playing", "attributes": {"supported_features": 16437}},
        {"entity_id": "light.example", "state": "on", "attributes": {"supported_features": 1}},
    ]
    sources = [{**state, "name": state["entity_id"], "observed": True, "area_id": "kitchen"} for state in states]
    items += classify({"devices": [], "unattached_entities": sources}, states, {})
    policy = {"calendars": ["calendar.example"], "calendars_screens": [surface["id"]], "landscape_panel": True}
    panel = generate(house, surface, items, areas, policy=policy)
    views = {v["path"]: v for v in panel["config"]["views"]}
    assert not any(c.get("type") in {"calendar", "media-control", "entities"} for c in nested(panel["config"]))
    media = focus_data(panel, views["music"])
    assert media["listener"] == {"id": None, "scope": "house"}
    assert [p["entity_id"] for p in media["players"]] == ["media_player.example"]
    assert json.loads(views["today"]["cards"][0]["variables"]["focus_json"])["context_entity"].startswith("sensor.home_starter_context_")
    rooms = focus_data(panel, views["rooms"])["rooms"]
    assert len(rooms) == 1
    room = views[rooms[0]["path"].rsplit("/", 1)[1]]
    assert room["back_path"].endswith("/rooms")
    assert "light.example" in {i["entity_id"] for i in focus_data(panel, room)["controls"]}


def test_detail_titles_and_native_config_cannot_become_button_card_code_or_html():
    from html import escape

    from homestarter.panel import detail_panel

    title = '<img src=x onerror="alert(1)"> [[[ return "example"; ]]]'
    native = {"type": "tile", "entity": "light.example", "name": title}
    view = {"title": title, "sections": [{"cards": [native]}]}
    detail_panel(view, "fixture CSS")
    root = view["cards"][0]
    # Only our generated return expression is evaluated. Household text is a
    # JSON string, then rendered with HTML metacharacters escaped.
    assert root["name"] == "[[[ return " + json.dumps('<h1 style="margin:0;font:inherit">' + escape(title) + "</h1>") + "; ]]]"
    assert root["custom_fields"]["content"]["do_not_eval"] is True
    for card in nested(root):
        if card.get("card") == native:
            assert card["do_not_eval"] is True
    assert native in list(nested(root))


def test_shared_detail_backdrop_stays_below_ha_websocket_message_limit():
    house, surface, items, areas = fixture()
    house["people"] = [{"id": f"person{index}", "name": f"Example person {index}", "audience": "adult"} for index in range(8)]
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    config = panel["config"]
    payload = json.dumps(config).encode()
    assert len(payload) < 4 * 1024 * 1024
    # Five images in the approved overview and five once in the shared focused template.
    assert payload.count(b"data:image/jpeg;base64,") == 10
    template = config["button_card_templates"]["home_starter_page"]
    assert "pointer-events: auto" in template["extra_styles"]
    for view in config["views"]:
        if view["path"] in {"home", "ambient", "dark", "climate"}:
            continue
        assert view["cards"][0]["template"] == "home_starter_page"
        assert "extra_styles" not in view["cards"][0]


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
        assert room["variables"]["zone"] == zone["entity"]
        assert room["variables"]["damper"] == damper["entity"]
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
    assert json.loads(settings["cards"][0]["variables"]["focus_json"])["kind"] == "settings"
    assert "/profile" in panel["config"]["button_card_templates"]["home_starter_page"]["custom_fields"]["body"]
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


def test_every_person_has_first_class_focused_routes_and_separate_listener_scope():
    house, surface, items, areas = fixture()
    house["people"] += [{"id": "child", "name": "Example child", "audience": "everyone"}]
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    views = {v["path"]: v for v in panel["config"]["views"]}
    for person in house["people"]:
        prefix = "person-" + person["id"].encode().hex()
        root = json.loads(views[prefix]["cards"][0]["variables"]["focus_json"])
        assert root["kind"] == "person" and root["owner"] == person["id"]
        for suffix in ("today", "music", "call", "cameras", "rooms"):
            child = views[prefix + "-" + suffix]
            assert child["title"].startswith(person["name"] + "’s ")
            assert child["cards"][0]["template"] == "home_starter_page"
            assert child["back_path"].endswith("/" + prefix)
            assert json.loads(child["cards"][0]["variables"]["focus_json"])["owner"] == person["id"]
        media = focus_data(panel, views[prefix + "-music"])
        assert media["listener"] == {"id": person["id"], "scope": "person"}
        assert media["context_entity"] != json.loads(views["today"]["cards"][0]["variables"]["focus_json"])["context_entity"]


def test_child_default_destination_is_not_a_hard_restriction_and_admission_still_wins():
    from homestarter.panel_pages import person_sources

    house, surface, items, areas = fixture()
    child = {"id": "child", "name": "Example child", "audience": "everyone"}
    house["people"].append(child)
    states = [{"entity_id": "media_player." + room, "state": "idle", "attributes": {}} for room in ("bedroom", "other", "private")]
    sources = [{**s, "name": s["entity_id"], "area_id": s["entity_id"].split(".")[1], "device_id": s["entity_id"], "observed": True} for s in states]
    items += classify({"devices": [], "unattached_entities": sources}, states, {})
    areas += [{"area_id": room, "name": "Example " + room} for room in ("bedroom", "other", "private")]
    policy = {"landscape_panel": True, "members": {"child": {"kind": "child", "rooms": ["bedroom"], "devices": ["media_player.other"]}}}
    selected, rooms, adult = person_sources(house, surface, child, items, policy)
    assert {i["entity_id"] for i in selected if i["domain"] == "media_player"} == {"media_player.bedroom", "media_player.other"}
    assert rooms == ["bedroom"] and not adult
    panel = generate(house, surface, items, areas, policy=policy)
    views = {v["path"]: v for v in panel["config"]["views"]}
    media = focus_data(panel, views["person-" + child["id"].encode().hex() + "-music"])
    assert media["default_destination"] == "media_player.bedroom"
    assert len(media["players"]) == 2
    house["preferences"]["child"] = {"hide": ["media_player.other"], "pin": [], "order": []}
    assert "media_player.other" not in {i["id"] for i in person_sources(house, surface, child, items, policy)[0]}


def test_adapter_readiness_opt_out_and_person_binding_cannot_be_bypassed():
    from homestarter.panel_pages import capability_bindings

    _, surface, _, _ = fixture()
    policy = {
        "features": {"music": {"intent": "wanted", "screens": [surface["id"]]}},
        "panel_bindings": {
            "person:example": {
                "listening": {"status": "ready", "person_id": "example", "revision": "fixture", "entity_id": "sensor.example_listening", "actions": {}}
            }
        },
    }
    assert "listening" in capability_bindings(policy, surface, "example")
    assert not capability_bindings(policy, surface, None)
    assert not capability_bindings(policy, surface, "other")
    policy["features"]["music"]["intent"] = "not_wanted"
    assert not capability_bindings(policy, surface, "example")


def test_focused_shell_reuses_the_approved_overview_css_without_restyling_house():
    from pathlib import Path

    house, surface, items, areas = fixture()
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    home = panel["config"]["views"][0]["cards"][0]
    shell = panel["config"]["button_card_templates"]["home_starter_page"]
    expected = Path("home_starter/server/homestarter/static/panel-layout.css").read_text(encoding="utf-8")
    assert home["extra_styles"].endswith(expected)
    assert expected.replace(".hs-panel {", ".hs-panel, #card {", 1) in shell["extra_styles"]
    assert json.loads(shell["variables"]["common_json"])["people"] == home["variables"]["panel"]["people"]
    assert "#0b1013" in shell["extra_styles"] and "#41484e" in shell["extra_styles"]


def test_focused_payload_is_inert_to_recursive_button_card_template_evaluation():
    house, surface, items, areas = fixture()
    label = '[[[ throw new Error("must stay a label"); ]]]'
    house["people"][0]["name"] = label
    items[0]["name"] = label
    panel = generate(house, surface, items, areas, policy={"landscape_panel": True})
    variables = panel["config"]["button_card_templates"]["home_starter_page"]["variables"]
    # The renderer receives one JSON string, never recursively evaluated objects.
    assert set(variables) == {"common_json"} and variables["common_json"].startswith("{")
    assert json.loads(variables["common_json"])["people"][1]["name"] == label
    for view in panel["config"]["views"][1:]:
        payload = view["cards"][0]["variables"]["focus_json"]
        assert isinstance(payload, str) and payload.startswith("{")
