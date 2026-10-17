"""The reference wall is passive and keeps source selection/ownership boundaries."""

import json

from homestarter.surfaces import generate
from test_surfaces import household, inventory


def test_reference_wall_uses_bounded_single_panel_and_no_operating_actions():
    house = household()
    house["surfaces"][0]["profile"] = "wall"
    inv, states = inventory()
    from homestarter.surfaces import classify

    generated = generate(house, house["surfaces"][0], classify(inv, states, {}), inv["areas"], policy={"landscape_panel": True})
    assert generated["wall_briefing"]
    assert len(generated["config"]["views"]) == 1
    view = generated["config"]["views"][0]
    assert view["type"] == "panel"
    root = view["cards"][0]
    assert root["tap_action"] == root["hold_action"] == root["double_tap_action"] == {"action": "none"}
    assert "data:image/jpeg;base64" in root["extra_styles"]
    assert len(json.dumps(generated["config"]).encode()) < 4 * 1024 * 1024
    assert "call-service" not in str(root) and '"action": "navigate"' not in str(root)
