"""Synthetic preview configuration only. No credentials, publishing or household data."""

import copy
import json

import pytest
from homestarter.panel_preview import prepare, verify
from homestarter.surfaces import generate
from test_panel import fixture, nested


def example():
    house, surface, items, areas = fixture()
    return generate(house, surface, items, areas, policy={"landscape_panel": True, "music_backend": "fixture_addon"})


def test_preview_is_separate_and_keeps_scope_state_and_source_unchanged():
    generated = example()
    source = copy.deepcopy(generated["config"])
    prepared = prepare(source, generated["url_path"])
    verify(prepared, source, generated["url_path"])
    assert source == generated["config"]
    assert prepared["show_in_sidebar"] is False
    assert prepared["url_path"] != generated["url_path"]
    assert [v["path"] for v in prepared["config"]["views"]] == [v["path"] for v in source["views"]]
    assert "kiosk_mode" not in prepared["config"]
    original = json.loads(source["button_card_templates"]["home_starter_page"]["variables"]["common_json"])
    common = json.loads(prepared["config"]["button_card_templates"]["home_starter_page"]["variables"]["common_json"])
    assert common["surface_id"] == original["surface_id"]
    expected_scopes = json.loads(json.dumps(original["scopes"]).replace("/" + generated["url_path"] + "/", "/home-starter-airtouch-preview/"))
    assert common["scopes"] == expected_scopes
    assert common["epoch"] == original["epoch"]
    assert common["base"] == "/home-starter-airtouch-preview"
    assert prepared["review"]["native_replacements"] > 0
    assert prepared["review"]["wrapped_templates"] > 0
    for node in nested(prepared["config"]):
        if node.get("type"):
            assert node["type"] in {"panel", "custom:button-card"}
        for key, action in node.items():
            if key.endswith("_action"):
                assert action["action"] in {"none", "navigate"}
                if action["action"] == "navigate":
                    assert action["navigation_path"] in prepared["review"]["routes"]
        assert "features" not in node and "camera_image" not in node


def test_preview_rejects_same_address_invalid_routes_and_stale_or_changed_payload():
    generated = example()
    source, path = generated["config"], generated["url_path"]
    with pytest.raises(ValueError):
        prepare(source, path, preview_path=path)
    prepared = prepare(source, path)
    prepared["config"]["title"] = "Changed"
    with pytest.raises(ValueError):
        verify(prepared, source, path)
    changed = copy.deepcopy(source)
    changed["views"][0]["path"] = "../other"
    with pytest.raises(ValueError):
        prepare(changed, path)
    changed = copy.deepcopy(source)
    changed["views"][0]["type"] = "sections"
    with pytest.raises(ValueError):
        prepare(changed, path)


def test_native_camera_and_service_actions_are_replaced_without_resource_urls():
    generated = example()
    source = generated["config"]
    source["views"][0]["cards"].append({"type": "picture-entity", "entity": "camera.fixture", "camera_image": "camera.fixture"})
    root = source["views"][0]["cards"][0]
    root["hold_action"] = {"action": "call-service", "service": "climate.turn_off"}
    root["styles"]["card"].append({"background-image": "url(/api/camera_proxy/camera.fixture)"})
    prepared = prepare(source, generated["url_path"])
    card = prepared["config"]["views"][0]["cards"][0]
    assert card["hold_action"] == {"action": "none"}
    assert card["styles"]["card"][-1]["background-image"] == "none"
    assert prepared["config"]["views"][0]["cards"][-1]["type"] == "custom:button-card"
