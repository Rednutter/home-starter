"""Reference-led specialist shell using mature button-card and native HA controls."""

import base64
import json
from pathlib import Path
from urllib.parse import urlsplit


def resource_ready(resources, component="button-card"):
    """Only recognize an installed same-origin module, never fetch third-party JS."""
    for row in resources if isinstance(resources, list) else []:
        parts = urlsplit(row.get("url", ""))
        if (
            row.get("type") == "module"
            and not parts.scheme
            and not parts.netloc
            and parts.path in {f"/hacsfiles/{component}/{component}.js", f"/local/{component}.js"}
        ):
            return True
    return False


def apply(generated, house, climate, policy):
    """Keep all control subviews; replace only specialist household overview pages."""
    from .surfaces import card_for, fingerprint, section

    static = Path(__file__).parent / "static"
    content = (static / "panel-content.js").read_text(encoding="utf-8")
    css = (static / "panel-layout.css").read_text(encoding="utf-8")
    backdrop = static / "panel-room.jpg"
    image = "url(data:image/jpeg;base64," + base64.b64encode(backdrop.read_bytes()).decode() + ")" if backdrop.exists() else "none"
    css = ":host { --hs-backdrop: " + image + "; }\n" + css
    config = generated["config"]
    base = "/" + generated["url_path"]
    kiosk_name = policy.get("kiosk_user_name") if generated["surface"].get("kiosk") else None
    if generated["surface"].get("kiosk") and not kiosk_name:
        raise ValueError("Review this panel's dedicated display account before enabling kiosk presentation.")
    if kiosk_name:
        viewer = "!user_is_admin && user_name === " + json.dumps(kiosk_name)
        config["kiosk_mode"] = {
            "hide_sidebar": "[[[ " + viewer + " && panel_url !== " + json.dumps(base + "/settings") + " ]]]",
            "hide_header": "[[[ " + viewer + " && " + json.dumps([base, base + "/home"]) + ".includes(panel_url) ]]]",
        }
    people = [{"name": "House", "path": base + "/home", "icon": "mdi:home-outline"}] + [
        {"name": p["name"], "path": base + "/person-" + p["id"].encode().hex(), "icon": "mdi:account-circle-outline"} for p in house["people"]
    ]
    for view in config["views"]:
        if view.get("subview") or view["path"] in {"ambient", "dark"}:
            continue
        path = view["path"]
        prefix = "" if path == "home" else path + "-"
        targets = {
            name: base + "/" + prefix + name
            for name in ("climate", "today", "rooms", "music", "context")
            if any(v["path"] == prefix + name for v in config["views"])
        }
        main = next((i for i in climate if i.get("attributes", {}).get("fan_modes")), next(iter(climate), None))
        # A known offline AirTouch remains inspectable; it never fabricates temperature.
        if main and "climate" not in targets:
            target = prefix + "climate"
            config["views"].append(
                {
                    "type": "sections",
                    "title": "Climate",
                    "path": target,
                    "subview": True,
                    "back_path": base + "/" + path,
                    "max_columns": 2,
                    "sections": [section("Climate", [card_for(i, generated["surface"], "large") for i in climate])],
                }
            )
            targets["climate"] = base + "/" + target
        admitted = generated["admitted"] if path == "home" else []
        # Personal pages retain their existing admission boundary and controls.
        if path != "home":
            view.update(subview=True, back_path=base + "/home")
            continue
        root = {
            "type": "custom:button-card",
            "show_icon": False,
            "show_name": False,
            "tap_action": {"action": "none"},
            "hold_action": {"action": "none"},
            "update_timer": "30s",
            "variables": {
                "panel": {
                    "base": base,
                    "kiosk_user_name": kiosk_name,
                    "title": generated["surface"]["name"],
                    "path": base + "/" + path,
                    "people": people,
                    "targets": targets,
                    "climate": main["entity_id"] if main else None,
                    "zones": [i["entity_id"] for i in climate if i is not main],
                    "weather": next((i["entity_id"] for i in admitted if i["domain"] == "weather"), None),
                    "calendars": [i["entity_id"] for i in admitted if i["domain"] == "calendar"],
                    "media": [i["entity_id"] for i in admitted if i["domain"] == "media_player"],
                    "lights": [i["entity_id"] for i in admitted if i["domain"] == "light"],
                    "alerts": [i["entity_id"] for i in admitted if i["level"] == 0],
                    "bins": generated["surface"]["id"] in policy.get("bin_context_screens", []),
                }
            },
            "styles": {
                "card": [
                    {"padding": "0"},
                    {"border": "0"},
                    {"border-radius": "0"},
                    {"box-shadow": "none"},
                    {"background": "transparent"},
                ],
                "grid": [{"display": "block"}],
                "custom_fields": {"panel": [{"white-space": "normal"}, {"text-align": "left"}]},
            },
            "custom_fields": {"panel": "[[[\n" + content + "\n]]]"},
            "extra_styles": css,
        }
        view.clear()
        view.update(type="panel", title="House", path=path, cards=[root])
    if kiosk_name:
        config["views"].append(
            {
                "type": "sections",
                "title": "Settings",
                "path": "settings",
                "subview": True,
                "back_path": base + "/home",
                "max_columns": 1,
                "sections": [
                    section(
                        "Display settings",
                        [
                            {
                                "type": "button",
                                "name": "Profile and app settings",
                                "icon": "mdi:account-cog-outline",
                                "tap_action": {"action": "navigate", "navigation_path": "/profile"},
                            },
                            {
                                "type": "button",
                                "name": "Panel mode",
                                "icon": "mdi:fullscreen",
                                "tap_action": {"action": "navigate", "navigation_path": base + "/home"},
                            },
                        ],
                    )
                ],
            }
        )
    generated["fingerprint"] = fingerprint(config)
    generated["warnings"].append(
        "Landscape panel requires the installed HACS button-card module. Climate controls remain native HA subviews; uncommissioned services are labelled."
    )
    return generated
