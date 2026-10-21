"""The reference wall is passive and keeps source selection/ownership boundaries."""

import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from homestarter.surfaces import generate
from test_surfaces import household, inventory


def test_local_wallpaper_library_has_complete_periods_and_recorded_provenance():
    static = Path(__file__).parents[1] / "home_starter/server/homestarter/static"
    manifest = json.loads((static / "wallpapers.json").read_text(encoding="utf-8"))
    assert manifest["generator"] == "OpenAI built-in image_gen"
    assert manifest["not_live_household_data"] is True
    assert Counter(row["period"] for row in manifest["images"]) == dict.fromkeys(("morning", "day", "afternoon", "evening", "night"), 4)
    assert len({row["id"] for row in manifest["images"]}) == 20
    for row in manifest["images"]:
        assert row["prompt"] and row["easter_egg"]
        assert row["file"] == row["id"] + ".webp"
        payload = (static / "wallpapers" / row["file"]).read_bytes()
        assert payload[:4] == b"RIFF" and payload[8:12] == b"WEBP"
        assert sha256(payload).hexdigest() == row["sha256"]


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
    catalogue = json.loads(root["variables"]["wall_json"])["wallpapers"]
    assert len(catalogue) == 20
    assert root["extra_styles"].count("data:image/webp;base64,") == 26
    assert "const wallWallpaper=" in root["custom_fields"]["wall"]
    assert len(json.dumps(generated["config"]).encode()) < 4 * 1024 * 1024
    assert "call-service" not in str(root) and '"action": "navigate"' not in str(root)


def test_extra_decorations_have_recorded_generated_provenance_and_packaged_hashes():
    static = Path(__file__).parents[1] / "home_starter/server/homestarter/static"
    manifest = json.loads((static / "decorations.json").read_text())
    assert manifest["not_live_household_data"] is True
    assert manifest["generator"] == "OpenAI built-in image_gen"
    assert sum(row.get("count", 1) for row in manifest["images"]) == 42
    for row in manifest["images"]:
        assert sha256((static / row["file"]).read_bytes()).hexdigest() == row["sha256"]
