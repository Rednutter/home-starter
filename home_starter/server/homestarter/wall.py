"""Passive family morning display using the approved panoramic visual reference."""

import base64
import json
from functools import lru_cache
from pathlib import Path

from .context import entity_id


@lru_cache(maxsize=1)
def wallpapers():
    """Embed reviewed decorative assets locally; never fetch a remote feed."""
    static = Path(__file__).parent / "static"
    manifest = static / "wallpapers.json"
    if not manifest.exists():
        return [], ""
    images, styles = [], []
    for row in json.loads(manifest.read_text(encoding="utf-8"))["images"]:
        image = base64.b64encode((static / "wallpapers" / row["file"]).read_bytes()).decode()
        images.append({"id": row["id"], "period": row["period"]})
        styles.append(f"--wallpaper-{row['id']}:url(data:image/webp;base64,{image});")
    return images, "".join(styles)


def apply(generated, house, policy):
    from .surfaces import fingerprint

    static = Path(__file__).parent / "static"
    source = (static / "wall-wallpaper.js").read_text(encoding="utf-8") + "\n" + (static / "wall-content.js").read_text(encoding="utf-8")
    css = (static / "wall-layout.css").read_text(encoding="utf-8")
    backdrop = static / "wall-morning.jpg"
    image = "url(data:image/jpeg;base64," + base64.b64encode(backdrop.read_bytes()).decode() + ")" if backdrop.exists() else "none"
    catalogue, wallpaper_styles = wallpapers()
    items = generated["admitted"]
    climate = [i for i in items if i["domain"] == "climate"]
    main = next((i for i in climate if i.get("attributes", {}).get("fan_modes")), next(iter(climate), None))
    metadata = {
        "title": generated["surface"]["name"],
        "surface_id": generated["surface"]["id"],
        "epoch": house["epoch"],
        "context": entity_id(generated["surface"]["id"]),
        "weather": next((i["entity_id"] for i in items if i["domain"] == "weather"), None),
        "people": {i["attributes"]["id"]: i["entity_id"] for i in items if i["domain"] == "person" and i.get("attributes", {}).get("id")},
        "climate": main["entity_id"] if main else None,
        "lights": [i["entity_id"] for i in items if i["domain"] == "light"],
        "security": [i["entity_id"] for i in items if i["domain"] == "alarm_control_panel" and not i["id"].startswith("alert:")],
        "alerts": [{"entity": i["entity_id"], "name": i["name"], "alarm": i["domain"] == "alarm_control_panel"} for i in items if i["level"] == 0],
        "endpoint": policy.get("wall_endpoint"),
        "wallpapers": catalogue,
    }
    root = {
        "type": "custom:button-card",
        "show_icon": False,
        "show_name": False,
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "double_tap_action": {"action": "none"},
        "update_timer": "5s",
        "variables": {"wall_json": json.dumps(metadata)},
        "styles": {
            "card": [{"padding": "0"}, {"border": "0"}, {"border-radius": "0"}, {"box-shadow": "none"}, {"background": "#0b1013"}],
            "grid": [{"display": "block"}],
            "custom_fields": {"wall": [{"white-space": "normal"}, {"text-align": "left"}]},
        },
        "custom_fields": {"wall": "[[[\n" + source + "\n]]]"},
        "extra_styles": ":host { --wall-landscape: " + image + "; " + wallpaper_styles + " }\n" + css,
    }
    generated["config"]["views"] = [{"type": "panel", "title": "Home", "path": "home", "background": "#0b1013", "cards": [root]}]
    generated["wall_briefing"] = True
    generated["fingerprint"] = fingerprint(generated["config"])
    return generated
