"""Reference-led specialist shell using mature button-card and native HA controls."""

import base64
import json
from html import escape
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


def room_panel(zone, damper):
    """Keep native temperature/mode features; group the same-device airflow."""
    controls = {**zone, "name": "", "hide_state": True, "features_position": "inline"}
    controls["features"] = sorted(
        [{**feature, **({"style": "icons"} if feature["type"] == "climate-hvac-modes" else {})} for feature in zone.get("features", [])],
        key=lambda feature: feature["type"] != "climate-hvac-modes",
    )
    # Two enclosing button-cards (page and room grid) each consume one bracket pair.
    current = (
        "const s=hass.states[variables.zone]; const t=s?.attributes.current_temperature; "
        "const reading=s && !['unknown','unavailable'].includes(s.state) && typeof t==='number' && Number.isFinite(t) "
        "? `<span class='hs-room-now' aria-label='Room temperature ${t} degrees'>"
        "<ha-icon icon='mdi:thermometer' aria-hidden='true'></ha-icon>${t}°</span>` : '';"
        "return `<div class='hs-room-heading'><span class='hs-room-name'>${variables.label}</span>${reading}</div>`;"
    )
    airflow = (
        "const s=hass.states[variables.damper]; const p=s?.attributes.current_position; "
        "const valid=s && !['unknown','unavailable'].includes(s.state) && typeof p==='number' && Number.isFinite(p) && p>=0 && p<=100; "
        "return `<div class='hs-room-airflow' role='img' aria-label='Damper ${valid?p+\"% open\":\"unavailable\"}'>"
        "<ha-icon icon='mdi:valve' title='Damper opening' aria-hidden='true'></ha-icon><span class='hs-airflow-track' aria-hidden='true'>"
        "<span style='width:${valid?p:0}%'></span></span><strong>${valid?p+'%':'—'}</strong></div>`;"
    )
    return {
        "type": "custom:button-card",
        "entity": zone["entity"],
        "name": escape(zone.get("name", zone["entity"])),
        "show_icon": False,
        "show_name": False,
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "variables": {"zone": zone["entity"], "damper": damper["entity"], "label": escape(zone.get("name", zone["entity"])).replace("[", "&#91;")},
        "triggers_update": [zone["entity"], damper["entity"]],
        "styles": {
            "card": [
                {"padding": "12px"},
                {"height": "100%"},
                {"border": "0"},
                {"box-shadow": "none"},
                {"background": "linear-gradient(105deg,rgba(22,24,26,.96),rgba(22,24,26,.72)),var(--hs-backdrop)"},
                {"background-size": "cover"},
                {"background-position": "center"},
                {"--ha-font-size-m": "22px"},
                {"--feature-height": "48px"},
                {"--state-climate-fan-only-color": "#3b8cbb"},
                {"--ha-card-background": "transparent"},
                {"--ha-card-border-width": "0"},
            ],
            "grid": [
                {"grid-template-areas": '"current controls" "airflow airflow"'},
                {"grid-template-columns": "minmax(0,.35fr) minmax(0,.65fr)"},
                {"gap": "8px"},
            ],
            "name": [
                {"justify-self": "start"},
                {"text-align": "left"},
                {"white-space": "normal"},
                {"font-size": "20px"},
                {"line-height": "1.25"},
                {"font-weight": "600"},
            ],
            "custom_fields": {
                "current": [{"min-width": "0"}, {"white-space": "normal"}, {"text-align": "left"}],
                "controls": [{"width": "100%"}, {"min-width": "0"}],
                "airflow": [{"width": "100%"}],
            },
        },
        "custom_fields": {"current": "[[[[[ " + current + " ]]]]]", "controls": {"card": controls}, "airflow": "[[[[[ " + airflow + " ]]]]]"},
        "extra_styles": (
            ":host{height:100%;display:block}"
            ".hs-room-heading{display:flex;flex-direction:column;gap:10px;text-align:left;font-family:Roboto,Arial,sans-serif}"
            ".hs-room-name{font-size:20px;font-weight:600;line-height:1.25;overflow-wrap:normal}"
            ".hs-room-now{display:flex;align-items:center;gap:4px;font-size:24px;font-variant-numeric:tabular-nums}"
            ".hs-room-now ha-icon{--mdc-icon-size:16px;width:16px;height:16px;flex:0 0 16px;color:#cad3db}"
            ".hs-room-airflow{display:flex;align-items:center;gap:10px;color:#cad3db;font:14px Roboto,Arial,sans-serif;text-align:left}"
            ".hs-room-airflow ha-icon{--mdc-icon-size:18px;width:18px;height:18px;flex:0 0 18px}"
            ".hs-room-airflow strong{font-weight:500;min-width:40px;text-align:right}"
            ".hs-airflow-track{flex:1;height:4px;background:#2b4353;border-radius:2px;overflow:hidden}"
            ".hs-airflow-track>span{display:block;height:100%;background:#79bedf}#card.disabled{pointer-events:auto;cursor:default}"
        ),
    }


def climate_panel(view, css, items=()):
    """Theme the existing native controls without changing their actions or IDs."""
    cards = [card for group in view.get("sections", []) for card in group.get("cards", []) if card.get("type") != "heading"]
    if not cards:
        return
    system = next((card for card in cards if card.get("type") == "thermostat"), cards[0])
    rooms = [card for card in cards if card is not system and card.get("entity", "").startswith("climate.")]
    notices = [card for card in cards if card.get("type") == "conditional"]
    airflow = [card for card in cards if card is not system and card not in rooms and card not in notices]
    sources = {item["entity_id"]: item for item in items}
    paired_rooms = []
    for zone in rooms:
        source = sources.get(zone["entity"], {})
        device = source.get("evidence", {}).get("device_id")
        candidates = [
            card
            for card in airflow
            if (item := sources.get(card.get("entity"), {})).get("device_class") == "damper" and device and item.get("evidence", {}).get("device_id") == device
        ]
        siblings = [card for card in rooms if device and sources.get(card["entity"], {}).get("evidence", {}).get("device_id") == device]
        if source.get("platform") == "airtouch5" and len(candidates) == 1 and len(siblings) == 1:
            paired_rooms.append(room_panel(zone, candidates[0]))
            airflow.remove(candidates[0])
        else:
            paired_rooms.append(zone)
    rooms = paired_rooms

    def group(children, columns=2):
        names = [f"control{i}" for i in range(len(children))]
        rows = [names[i : i + columns] for i in range(0, len(names), columns)]
        areas = " ".join('"' + " ".join(row + ["."] * (columns - len(row))) + '"' for row in rows) or "none"
        return {
            "type": "custom:button-card",
            "show_icon": False,
            "show_name": False,
            "tap_action": {"action": "none"},
            "hold_action": {"action": "none"},
            "styles": {
                "card": [{"padding": "0"}, {"background": "none"}, {"border": "0"}, {"box-shadow": "none"}, {"height": "100%"}],
                "grid": [{"grid-template-areas": areas}, {"grid-template-columns": f"repeat({columns},minmax(0,1fr))"}, {"gap": "12px"}, {"height": "100%"}],
                "custom_fields": {
                    name: [
                        {"min-width": "0"},
                        {"width": "100%"},
                        {"text-align": "left"},
                        {"border": "1px solid #52606b"},
                        {"border-radius": "20px"},
                        {"overflow": "hidden"},
                        {"align-self": "stretch"},
                    ]
                    for name in names
                },
            },
            "custom_fields": {f"control{i}": {"card": card} for i, card in enumerate(children)},
            "extra_styles": ":host{height:100%;display:block}@media (max-width:720px) { #container { "
            "grid-template-columns: minmax(0,1fr) !important; grid-template-areas: "
            + (" ".join('"' + name + '"' for name in names) or "none")
            + " !important; } }",
        }

    fields = {"system": {"card": system}}
    if notices:
        fields["notices"] = {"card": {"type": "vertical-stack", "cards": notices}}
    if rooms:
        fields["rooms"] = {"card": group(rooms)}
    if airflow:
        fields["airflow"] = {"card": group(airflow, 3)}
    root = group([])
    root["styles"]["card"] = [
        {"display": "block"},
        {"padding": "22px"},
        {"background": "#0b1013"},
        {"border": "0"},
        {"border-radius": "0"},
        {"box-shadow": "none"},
    ]
    root["styles"]["grid"] = [
        {
            "grid-template-areas": ('"notices notices" ' if notices else "")
            + ('"system rooms" ' if rooms else '"system system" ')
            + ('"airflow airflow"' if airflow else "")
        },
        {"grid-template-columns": "minmax(0, .75fr) minmax(0, 1.25fr)"},
        {"grid-template-rows": ("auto " if notices else "") + "minmax(min-content,1fr)" + (" auto" if airflow else "")},
        {"height": "auto"},
        {"gap": "20px"},
        {"align-items": "start"},
        {"align-content": "stretch"},
    ]
    root["styles"]["custom_fields"] = {key: [{"min-width": "0"}, {"width": "100%"}, {"align-self": "stretch"}] for key in fields}
    root["custom_fields"] = fields
    root["extra_styles"] = css.replace(
        '"system" "rooms" "airflow"', " ".join('"' + key + '"' for key in ["notices", "system", "rooms", "airflow"] if key in fields)
    )
    view.pop("sections", None)
    view.pop("max_columns", None)
    view.update(type="panel", cards=[root])


def detail_panel(view, css, template=None):
    """Lay out admitted native sections in the specialist world's responsive shell."""

    def title_text(value, level=2):
        # button-card evaluates templates and renders names as HTML. A quoted,
        # escaped constant keeps household names as display text.
        title = f'<h{level} style="margin:0;font:inherit">' + escape(value or "") + f"</h{level}>"
        return "[[[ return " + json.dumps(title) + "; ]]]"

    def compact_navigation(card):
        if card.get("type") == "button" and card.get("tap_action", {}).get("action") == "navigate":
            return {**card, "icon_height": card.get("icon_height", "40px")}
        if card.get("type") in {"vertical-stack", "horizontal-stack", "grid"}:
            return {**card, "cards": [compact_navigation(child) for child in card.get("cards", [])]}
        if card.get("type") == "conditional":
            return {**card, "card": compact_navigation(card["card"])}
        return card

    def layout(cards, title=None):
        fields = {
            f"control{i}": {
                "card": compact_navigation(card),
                "do_not_eval": True,
            }
            for i, card in enumerate(cards)
        }
        return {
            "type": "custom:button-card",
            "show_icon": False,
            "show_name": bool(title),
            "name": title_text(title),
            "tap_action": {"action": "none"},
            "hold_action": {"action": "none"},
            "styles": {
                "card": [{"padding": "0"}, {"background": "transparent"}, {"border": "0"}, {"box-shadow": "none"}],
                "grid": [
                    {"grid-template-areas": "none"},
                    {"grid-template-columns": "repeat(auto-fit,minmax(min(100%,280px),1fr))"},
                    {"gap": "14px"},
                    {"align-items": "start"},
                ],
                "name": [
                    {"grid-area": "auto"},
                    {"grid-column": "1 / -1"},
                    {"text-align": "left"},
                    {"justify-self": "stretch"},
                    {"white-space": "normal"},
                    {"font-size": "22px"},
                    {"font-weight": "600"},
                ],
                "custom_fields": {
                    key: [
                        {"grid-area": "auto"},
                        {"min-width": "0"},
                        {"text-align": "left"},
                        {"white-space": "normal"},
                        {"--ha-card-border-radius": "20px"},
                        {"--ha-card-border-width": "1px"},
                    ]
                    + ([{"--primary-color": "#103e59"}] if fields[key]["card"].get("type") == "media-control" else [])
                    for key in fields
                },
            },
            "custom_fields": fields,
            # button-card assigns named inline areas after custom field styles.
            "extra_styles": "#card.disabled{pointer-events:auto;cursor:default}#container>[id^=control]{grid-area:auto!important}",
        }

    groups = []
    for section in view.get("sections", []):
        cards = section.get("cards", [])
        title = next((card.get("heading") for card in cards if card.get("type") == "heading"), None)
        controls = [card for card in cards if card.get("type") != "heading"]
        if not controls:
            continue
        group = layout(controls, title if title != view["title"] else None)
        if section.get("visibility"):
            group = {"type": "conditional", "conditions": section["visibility"], "card": group}
        groups.append(group)
    root = layout([])
    root.update(
        show_name=True,
        name=title_text(view["title"], 1),
        custom_fields={"content": {"card": {"type": "vertical-stack", "cards": groups}, "do_not_eval": True}},
        extra_styles=css,
    )
    root["styles"]["card"] = [
        {"display": "block"},
        {"padding": "24px"},
        {"background": "#0b1013"},
        {"border": "0"},
        {"border-radius": "0"},
        {"box-shadow": "none"},
    ]
    root["styles"]["grid"] = [{"grid-template-areas": '"n" "content"'}, {"grid-template-columns": "minmax(0,1fr)"}, {"gap": "24px"}, {"align-content": "start"}]
    root["styles"]["name"] = [
        {"grid-area": "n"},
        {"text-align": "left"},
        {"justify-self": "stretch"},
        {"white-space": "normal"},
        {"font-size": "26px"},
        {"font-weight": "600"},
    ]
    root["styles"]["custom_fields"] = {"content": [{"min-width": "0"}, {"text-align": "left"}, {"white-space": "normal"}]}
    if template:
        root["template"] = template
        root.pop("extra_styles")
    view.pop("sections", None)
    view.pop("max_columns", None)
    view.update(type="panel", cards=[root])


def apply(generated, house, climate, policy, *, items=(), areas=()):
    """Reference shell and themed native climate controls for specialist panels."""
    from .surfaces import card_for, fingerprint, navigation, section

    static = Path(__file__).parent / "static"
    content = (static / "panel-content.js").read_text(encoding="utf-8")
    css = (static / "panel-layout.css").read_text(encoding="utf-8")
    backdrop = static / "panel-room.jpg"
    image = "url(data:image/jpeg;base64," + base64.b64encode(backdrop.read_bytes()).decode() + ")" if backdrop.exists() else "none"
    css = ":host { --hs-backdrop: " + image + "; }\n" + css
    # Decorative feature art is embedded only in the overview, never per person.
    art = []
    for kind in ("today", "call", "cameras", "media"):
        asset = static / f"panel-{kind}.jpg"
        value = "url(data:image/jpeg;base64," + base64.b64encode(asset.read_bytes()).decode() + ")" if asset.exists() else "none"
        art.append(f"--hs-{kind}-art: {value};")
    css = ":host { " + " ".join(art) + " }\n" + css
    config = generated["config"]
    base = "/" + generated["url_path"]
    # Every overview destination remains useful even before sources are selected.
    empty_pages = {
        "today": ("Today", "No verified commitments to show. Choose and verify a household calendar in Home Starter."),
        "rooms": ("Home / Rooms", "No room controls selected. Review room assignments and this screen's sources in Home Starter."),
        "music": ("Music", "No speaker selected. Choose a room speaker in Home Starter to show its native playback controls."),
        "context": ("Around the house", "No household information selected. Review this screen's sources in Home Starter."),
        "call": ("Call", "Calling is not commissioned. Complete calling setup and a working call check before using this panel to call."),
        "cameras": ("Cameras", "No camera selected. Camera selection and a working picture check are still needed. No camera feeds are shown."),
    }
    for path, (title, message) in empty_pages.items():
        if not any(v["path"] == path for v in config["views"]):
            config["views"].append(
                {
                    "type": "sections",
                    "title": title,
                    "path": path,
                    "subview": True,
                    "back_path": base + "/home",
                    "sections": [section(title, [{"type": "markdown", "content": message}])],
                }
            )
    rooms = next(v for v in config["views"] if v["path"] == "rooms")
    more = [("Around the house", "context", "mdi:information-outline"), ("Other controls", "other-controls", "mdi:tune")]
    rooms["sections"].append(
        section("", [navigation(title, base + "/" + path, icon) for title, path, icon in more if any(v["path"] == path for v in config["views"])])
    )
    if generated["surface"]["id"] in policy.get("bin_context_screens", []):
        from .waste import card

        bins = card()
        today = next(v for v in config["views"] if v["path"] == "today")
        today["sections"].insert(0, {**section("Bins", [bins]), "visibility": bins["conditions"]})
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
            for name in ("climate", "today", "rooms", "music", "context", "call", "cameras")
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
    from .panel_pages import apply_pages

    apply_pages(generated, house, items, areas, policy)
    generated["fingerprint"] = fingerprint(config)
    generated["warnings"].append(
        "Landscape panel requires the installed HACS button-card module. Climate controls remain native HA subviews; uncommissioned services are labelled."
    )
    return generated
