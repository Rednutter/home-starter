"""AirTouch focused routes. Household selection is presentation, never authentication."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import context
from .surfaces import admitted, preferences


def capability_bindings(policy, surface, owner):
    """Read-only adapter boundary. No settings, identities or providers are created here.

    Commissioners can attach a revisioned owned HA projection after their working
    checks. Readiness intent/screen opt-outs still win. No producer is implied by
    an entity name, discovered integration or a selected person tab.
    """
    result = {}
    scope = "person:" + owner if owner else "house"
    for feature, choice_key in (("listening", "music"), ("call", "communications"), ("camera", "cameras")):
        choice = policy.get("features", {}).get(choice_key, {})
        value = policy.get("panel_bindings", {}).get(scope, {}).get(feature)
        if choice.get("intent") != "wanted" or surface["id"] not in choice.get("screens", []):
            continue
        if not isinstance(value, dict) or value.get("status") != "ready" or value.get("person_id") != owner:
            continue
        if not isinstance(value.get("revision"), str) or not re.fullmatch(r"sensor\.[a-z0-9_]+", str(value.get("entity_id", ""))):
            continue
        result[feature] = {k: value[k] for k in ("entity_id", "revision")}
        # Actual integrations declare actions/arguments. The UI never guesses SIP
        # commands, camera/lock associations or listener-resume service arguments.
        actions = value.get("actions", {})
        domains = {"listening": {"music_assistant", "media_player"}, "call": {"voip", "sip", "asterisk"}, "camera": {"camera", "voip", "sip", "cover", "lock"}}
        result[feature]["actions"] = {
            name: spec
            for name, spec in (actions.items() if isinstance(actions, dict) else [])
            if isinstance(spec, dict)
            and spec.get("domain") in domains[feature]
            and isinstance(spec.get("service"), str)
            and re.fullmatch(r"[a-z0-9_]+", spec["service"])
            and set(spec) <= {"domain", "service", "data", "value_parameter", "destination_parameter"}
            and isinstance(spec.get("data", {}), dict)
            and not any(any(word in str(k).lower() for word in ("token", "password", "secret", "authorization")) for k in spec.get("data", {}))
        }
        if feature == "camera":
            result[feature]["cameras"] = [c for c in value.get("cameras", []) if isinstance(c, dict) and c.get("entity_id") in choice.get("sources", [])]
            result[feature]["entry"] = value.get("entry", [])
    return result


def person_sources(house, surface, person, items, policy):
    """Intersect screen choices, audience and explicit member rooms/devices."""
    member = policy.get("members", {}).get(person["id"], {})
    rooms = list(dict.fromkeys(member.get("rooms", []) + [s["area_id"] for s in house["surfaces"] if s["person_id"] == person["id"] and s["area_id"]]))
    devices = set(member.get("devices", []))
    adult = person["audience"] == "adult" and member.get("kind") != "child"
    personal = {**surface, "person_id": person["id"], "audience": "adult" if adult else "everyone"}
    pref = preferences(house, personal)
    selected = []
    for item in items:
        own = item["area_id"] in rooms or item.get("evidence", {}).get("device_id") in devices
        if not adult and not (own or item["scope"] == "whole_house" or item["level"] == 0):
            continue
        # An explicitly assigned room/device may be away from this wall panel.
        location = item["area_id"] if own else surface["area_id"]
        if admitted(item, {**personal, "area_id": location}, house, pref):
            selected.append(item)
    return selected, rooms, adult


def control(item):
    # Runtime values come from hass.states. Do not persist arbitrary provider
    # attributes (including expiring picture tokens) in dashboard configuration.
    return {k: item.get(k) for k in ("entity_id", "name", "domain", "device_class", "area_id", "interaction")}


def apply_pages(generated, house, items, areas, policy):
    from .panel import climate_panel

    static = Path(__file__).parent / "static"
    config = generated["config"]
    base = "/" + generated["url_path"]
    views = {v["path"]: v for v in config["views"]}
    overview = views["home"]["cards"][0]
    common = {k: overview["variables"]["panel"][k] for k in ("base", "people", "weather", "kiosk_user_name")}
    common["music_backend"] = policy.get("music_backend")
    common["surface_id"] = generated["surface"]["id"]
    common["epoch"] = house["epoch"]
    common["scopes"] = {}
    common["alerts"] = [control(i) for i in generated["admitted"] if i["level"] == 0]
    shell = (static / "panel-shell.js").read_text(encoding="utf-8")
    body = (static / "panel-music.js").read_text(encoding="utf-8") + "\n" + (static / "panel-pages.js").read_text(encoding="utf-8")
    css = overview["extra_styles"].replace(".hs-panel {", ".hs-panel, #card {", 1) + "\n" + (static / "panel-pages.css").read_text(encoding="utf-8")
    config.setdefault("button_card_templates", {})["home_starter_page"] = {
        "show_icon": False,
        "show_name": False,
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "update_timer": "2s",
        "variables": {"common": common},
        "styles": {
            "card": [{"padding": "18px 22px 16px"}, {"border": "0"}, {"border-radius": "0"}, {"box-shadow": "none"}],
            "grid": [
                {"grid-template-areas": '"header" "body" "footer"'},
                {"grid-template-columns": "minmax(0,1fr)"},
                {"grid-template-rows": "auto minmax(0,1fr) auto"},
                {"gap": "14px"},
            ],
            "custom_fields": {key: [{"min-width": "0"}, {"white-space": "normal"}, {"text-align": "left"}] for key in ("header", "body", "footer")},
        },
        "custom_fields": {
            "header": "[[[\n" + shell + "\nreturn header();\n]]]",
            "body": "[[[\n" + shell + "\n" + body + "\n]]]",
            "footer": "[[[\n" + shell + "\nreturn footer();\n]]]",
        },
        "extra_styles": css,
    }
    config.get("button_card_templates", {}).pop("home_starter_details", None)
    routes = {}

    def route(kind, path, title, owner, selected, back="home", room=None, default_rooms=()):
        selected_controls = [control(i) for i in selected if i["level"] != 0 and i["domain"] not in ("calendar", "weather", "person", "device_tracker")]
        players = [i for i in selected_controls if i["domain"] == "media_player"]
        default = next(
            (p["entity_id"] for area in default_rooms for p in players if p["area_id"] == area), players[0]["entity_id"] if players and not owner else None
        )
        key = "person:" + owner if owner else "house"
        scope = common["scopes"].setdefault(
            key,
            {
                "controls": selected_controls,
                "players": players,
                "default_destination": default,
                "listener": {"id": owner, "scope": "person" if owner else "house"},
                "rooms": [],
                "bindings": capability_bindings(policy, generated["surface"], owner),
            },
        )
        focus = {
            "kind": kind,
            "path": path,
            "title": title,
            "back": base + "/" + back,
            "owner": owner,
            "scope_key": key,
            "context_entity": context.entity_id(generated["surface"]["id"], owner),
            "bins": owner is None and generated["surface"]["id"] in policy.get("bin_context_screens", []),
            "room": room,
            "control_ids": [i["entity_id"] for i in selected_controls] if room or path.endswith("climate") else None,
        }
        # Availability is sourced from Home Starter; unsupported adapters have no actions.
        focus["availability"] = {k: "ready" if k in scope["bindings"] else "setup" for k in ("call", "camera", "listening")}
        root = {"type": "custom:button-card", "template": "home_starter_page", "variables": {"focus": focus}}
        routes[path] = {"type": "panel", "title": title, "path": path, "subview": True, "back_path": focus["back"], "cards": [root]}
        return focus

    def family(owner, name, selected, own_rooms=(), adult=False):
        parent = "person-" + owner.encode().hex() if owner else "home"
        prefix = parent + "-" if owner else ""
        for kind, suffix, title in [
            ("today", "today", "Today"),
            ("media", "music", "Media"),
            ("call", "call", "Call"),
            ("camera", "cameras", "Cameras / Door"),
            ("rooms", "rooms", "Home / Rooms"),
            ("context", "context", "Around the house"),
        ]:
            route(kind, prefix + suffix, name + "’s " + title if owner else title, owner, selected, parent, default_rooms=own_rooms)
        room_list = []
        for area in areas:
            controls = [i for i in selected if i["area_id"] == area["area_id"] and i["level"] != 0]
            if (not controls and owner and area["area_id"] not in own_rooms) or "room:" + area["area_id"] in preferences(
                house, {**generated["surface"], "person_id": owner}
            )["hide"]:
                continue
            path = prefix + "room-" + hashlib.sha256(area["area_id"].encode()).hexdigest()[:10]
            route("room", path, area["name"], owner, controls, prefix + "rooms", area["area_id"], own_rooms)
            room_list.append({"id": area["area_id"], "name": area["name"], "path": base + "/" + path, "control_ids": [i["entity_id"] for i in controls]})
        common["scopes"]["person:" + owner if owner else "house"]["rooms"] = room_list
        if owner:
            focus = route("person", parent, name, owner, selected, default_rooms=own_rooms)
            focus.update(default_rooms=list(own_rooms), adult=adult)
            focus["destinations"] = {k: base + "/" + prefix + v for k, v in [("today", "today"), ("media", "music"), ("call", "call"), ("rooms", "rooms")]}
            # Supervisory shortcuts reveal only each child's own already-scoped page.
            focus["supervision"] = (
                [
                    {"name": p["name"], "path": base + "/person-" + p["id"].encode().hex()}
                    for p in house["people"]
                    if policy.get("members", {}).get(p["id"], {}).get("kind") == "child"
                ]
                if adult
                else []
            )

    family(None, "House", generated["admitted"])
    for person in house["people"]:
        selected, own_rooms, adult = person_sources(house, generated["surface"], person, items, policy)
        family(person["id"], person["name"], selected, own_rooms, adult)
    for kind in ("ambient", "dark"):
        route(kind, kind, kind.title(), None, [], "home")
    routes["dark"]["cards"][0]["styles"] = {"card": [{"--hs-canvas": "#000000"}]}
    # Keep existing secondary routes reachable, but replace generic pages with focused controls.
    for path, view in views.items():
        if path in routes or path in {"home", "ambient", "dark"}:
            continue
        if path == "climate":
            route("climate", path, "Climate", None, generated["admitted"])
            source = {**view, "sections": view.get("sections", [])}
            climate_css = (static / "panel-climate.css").read_text(encoding="utf-8")
            climate_css = climate_css.replace("calc(100dvh - 56px)", "var(--hs-content-height, 480px)")
            climate_panel(source, climate_css, generated["admitted"])
            routes[path]["cards"][0]["custom_fields"] = {"body": {"card": source["cards"][0], "do_not_eval": True}}
        elif path == "settings":
            route("settings", path, "Display settings", None, [])
        else:
            owner = next((p["id"] for p in house["people"] if path.startswith("person-" + p["id"].encode().hex() + "-")), None)
            selected = (
                person_sources(house, generated["surface"], next(p for p in house["people"] if p["id"] == owner), items, policy)[0]
                if owner
                else generated["admitted"]
            )
            if path.endswith("climate"):
                selected = [i for i in selected if i["domain"] == "climate"]
            route(
                "room" if path.endswith("climate") else "context", path, view["title"], owner, selected, "person-" + owner.encode().hex() if owner else "home"
            )
    # button-card recursively evaluates object variables. A JSON string starts
    # with `{`, so even a label containing a complete [[[ template stays data.
    config["button_card_templates"]["home_starter_page"]["variables"] = {"common_json": json.dumps(common)}
    for view in routes.values():
        root = view["cards"][0]
        root["variables"] = {"focus_json": json.dumps(root["variables"]["focus"])}
    config["views"] = [views["home"], *routes.values()]
    generated["focused_pages"] = True
    generated["context_people"] = [p["id"] for p in house["people"]]
    generated["warnings"].append(
        "Focused Today context is an expiring HA projection. Selected household/personal briefing text may enter HA recorder history; "
        "person tabs do not authenticate anyone."
    )
    if common["kiosk_user_name"]:
        viewer = "!user_is_admin && user_name === " + json.dumps(common["kiosk_user_name"])
        paths = [base, base + "/home"] + [base + "/" + p for p in routes]
        config["kiosk_mode"]["hide_header"] = "[[[ " + viewer + " && " + json.dumps(paths) + ".includes(panel_url) ]]]"
        config["kiosk_mode"]["hide_sidebar"] = "[[[ " + viewer + " && " + json.dumps(paths) + ".includes(panel_url) ]]]"
    return generated
