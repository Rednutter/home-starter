"""Conservative household semantics and native Sections dashboard assembly."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .core import CoreClient, CoreError
from .household import PROFILES
from .readiness import allowed

# The catalogue is a capability contract, not a promise to invent absent sources.
CATALOGUE = {
    "room_summary": ("vertical-stack", "ready"),
    "quick_action": ("tile", "ready"),
    "alert": ("tile", "ready"),
    "climate_control": ("thermostat", "ready"),
    "climate_summary": ("tile", "ready"),
    "light_control": ("tile", "ready"),
    "media_now_playing": ("media-control", "ready"),
    "media_favourites": (None, "source_required"),
    "calendar_agenda": ("calendar", "ready"),
    "clock_weather": ("clock", "ready"),
    "weather_summary": ("weather-forecast", "ready"),
    "access": ("tile", "ready"),
    "camera": ("picture-entity", "source_required"),
    "doorbell_event": ("tile", "ready"),
    "appliance_status": ("tile", "ready"),
    "activity_today": ("markdown", "ready"),
    "presence": ("tile", "ready"),
    "status_chip": ("tile", "ready"),
    "timer": ("tile", "ready"),
    "household_notice": ("markdown", "ready"),
    "security_summary": ("tile", "ready"),
    "action_group": ("grid", "ready"),
    "bedside_clock": ("clock", "ready"),
    "calling_contact": (None, "source_required"),
    "room_detail": ("sections", "ready"),
}
PROFILE_FUNCTIONS = {
    "phone": {"lighting", "climate", "media", "access", "security", "information", "safety", "appliance"},
    "tablet": {"lighting", "climate", "media", "access", "security", "information", "safety", "appliance"},
    "specialist": {"climate", "lighting", "access", "safety", "security", "media", "information", "appliance"},
    "kitchen": {"lighting", "climate", "media", "information", "safety", "appliance"},
    "entry": {"access", "security", "information", "safety"},
    "bedside": {"lighting", "climate", "media", "information", "safety"},
    "wall": {"information", "media", "access", "security", "safety", "appliance", "climate", "lighting"},
}


def fingerprint(config: Any) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def suitable(item: dict, profile: str) -> bool:
    if profile == "wall" and item["interaction"] == "control":
        return False
    return item["function"] in PROFILE_FUNCTIONS[profile] or (
        item["level"] == 2 and item["interaction"] in ("control", "both") and item["scope"] == "whole_house"
    )


def classify(inventory: dict, states: list[dict], overrides: dict) -> list[dict]:
    live = {s["entity_id"]: s for s in states}
    devices = {d["id"]: d for d in inventory["devices"]}
    entities = [e for d in inventory["devices"] for e in d["entities"]] + inventory["unattached_entities"]
    result = []
    for e in entities:
        entity_id = e["entity_id"]
        domain = entity_id.split(".", 1)[0]
        state = live.get(entity_id, {})
        attrs = state.get("attributes") or {}
        dc = attrs.get("device_class")
        category = e.get("entity_category")
        override = overrides.get(entity_id, {})
        area = e.get("area_id") or devices.get(e.get("device_id"), {}).get("area_id")
        function, level, interaction, visibility, audience, component = "maintenance", 5, "status", "drill_down", "admin", "status_chip"
        reason = "No clear household role; kept in administration."
        if domain in ("light", "climate", "media_player", "cover", "lock", "alarm_control_panel", "vacuum", "fan"):
            function, component = {
                "light": ("lighting", "light_control"),
                "climate": ("climate", "climate_control"),
                "media_player": ("media", "media_now_playing"),
                "cover": ("access", "access"),
                "lock": ("access", "access"),
                "alarm_control_panel": ("security", "security_summary"),
                "vacuum": ("appliance", "appliance_status"),
                "fan": ("climate", "quick_action"),
            }[domain]
            level, interaction, visibility, audience = 2, "both", "always", "adult" if domain in ("cover", "lock", "alarm_control_panel") else "everyone"
            reason = "Home Assistant exposes a native household control."
        elif domain in ("weather", "calendar", "person", "timer"):
            function, level, visibility, audience = "information", 3, "always", "everyone"
            component = {"weather": "weather_summary", "calendar": "calendar_agenda", "person": "presence", "timer": "timer"}[domain]
            interaction = "both" if domain == "timer" else "status"
            reason = "Home Assistant exposes household context."
        elif domain == "sensor" and dc in ("temperature", "humidity"):
            function, level, visibility, audience = "climate", 3, "always", "everyone"
            reason = "A room measurement identified by Home Assistant."
        elif domain == "binary_sensor" and dc in ("smoke", "carbon_monoxide", "gas", "moisture", "safety"):
            function, level, visibility, audience, component = "safety", 0, "when_abnormal", "everyone", "alert"
            reason = "A safety signal identified by Home Assistant."
        elif domain == "binary_sensor" and dc in ("door", "window", "garage_door", "opening", "lock"):
            function, level, visibility, audience, component = "access", 1, "when_active", "everyone", "alert"
            reason = "An opening signal identified by Home Assistant."
        elif domain == "event" and dc == "doorbell":
            function, level, visibility, audience, component = "safety", 0, "when_active", "everyone", "doorbell_event"
            reason = "A doorbell event identified by Home Assistant; shown for two minutes."
        elif domain in ("scene", "script", "input_boolean", "switch") and override.get("include") is True:
            function, level, interaction, visibility, audience, component = "information", 2, "control", "always", "adult", "quick_action"
            reason = "Included explicitly by the household administrator."
        if domain == "cover" and dc == "damper" and e.get("platform") == "airtouch5":
            function, component, audience = "climate", "climate_summary", "everyone"
            reason = "AirTouch exposes a zone damper; show position without overriding automatic temperature control."
        # Diagnostics never become household controls through a pin or name match.
        if dc in ("battery", "signal_strength") or category in ("diagnostic", "config") or e.get("platform") == "demo":
            function, level, interaction, visibility, audience, component = "maintenance", 5, "status", "drill_down", "admin", "status_chip"
            reason = "Home Assistant marks this as maintenance, configuration or a demo source."
        usable = (
            e.get("observed")
            and not e.get("disabled_by")
            and not e.get("hidden_by")
            and e.get("platform") != "demo"
            and e.get("state") not in (None, "unavailable")
            and (domain == "scene" or e.get("state") != "unknown")
        )
        item = {
            "id": entity_id,
            "entity_id": entity_id,
            "name": override.get("name", e["name"]),
            "area_id": area,
            "function": function,
            "scope": override.get("scope", "whole_house" if domain in ("weather", "calendar", "person", "scene", "script") and not area else "local"),
            "interaction": interaction,
            "importance": "safety" if level == 0 else "technical" if level == 5 else "important" if level == 1 else "routine",
            "frequency": "frequent" if level == 2 else "occasional",
            "visibility": visibility,
            "audience": "everyone" if level == 0 else "admin" if level == 5 else override.get("audience", audience),
            "level": level,
            "component": component,
            "state": e.get("state"),
            "domain": domain,
            "device_class": dc,
            "platform": e.get("platform"),
            "attributes": {
                k: attrs[k]
                for k in (
                    "supported_features",
                    "hvac_modes",
                    "fan_modes",
                    "preset_modes",
                    "temperature",
                    "current_temperature",
                    "min_temp",
                    "max_temp",
                    "target_temp_step",
                    "current_position",
                )
                if k in attrs
            },
            "available": bool(usable),
            "usable": bool(usable) and (level == 0 or override.get("include") is not False),
            "reason": reason,
            "evidence": {
                "entity_id": entity_id,
                "registry_id": e.get("registry_id"),
                "device_id": e.get("device_id"),
                "platform": e.get("platform"),
                "basis": reason,
            },
        }
        item["surfaces"] = [profile for profile in PROFILES if suitable(item, profile)]
        result.append(item)
    return result


def preferences(house: dict, surface: dict) -> dict:
    physical = house["preferences"].get("surface:" + surface["id"], {})
    personal = house["preferences"].get(surface["person_id"], {})
    return {k: list(dict.fromkeys(personal.get(k, []) + physical.get(k, []))) for k in ("pin", "hide", "order")}


def admitted(item: dict, surface: dict, house: dict, pref: dict) -> bool:
    person = next((p for p in house["people"] if p["id"] == surface["person_id"]), None)
    audience = "adult" if surface["audience"] == "adult" and (not person or person["audience"] == "adult") else "everyone"
    if not item["usable"] or item["level"] > 4 or item["audience"] == "admin":
        return False
    if item["audience"] == "adult" and audience != "adult":
        return False
    if not suitable(item, surface["profile"]):
        return False
    if item["level"] != 0 and item["id"] in pref["hide"]:
        return False
    if surface["profile"] in ("specialist", "kitchen", "bedside") and item["scope"] == "local" and item["level"] != 0:
        if surface["profile"] == "specialist" and item.get("platform") == "airtouch5" and item["function"] == "climate":
            return True
        # Unknown location is not evidence that a control is near this fixed screen.
        if not item["area_id"] or surface["area_id"] != item["area_id"]:
            return False
    return True


def disabled_actions(card: dict) -> dict:
    return {**card, "tap_action": {"action": "none"}, "hold_action": {"action": "none"}, "double_tap_action": {"action": "none"}}


def card_for(item: dict, surface: dict, variant: str = "normal") -> dict:
    entity, name, domain = item["entity_id"], item["name"], item["domain"]
    wall = surface["profile"] == "wall"
    # Wall information is deliberately not interactive; native media/thermostat widgets have controls.
    if wall or domain == "calendar" and surface["profile"] in ("phone", "bedside"):
        # Markdown templates update from HA states without clickable controls.
        safe_name = json.dumps(name, ensure_ascii=False)
        if domain == "calendar":
            content = "**{{ " + safe_name + " }}**\n\n{{ state_attr('" + entity + "', 'message') or 'No upcoming event reported' }}"
            content += (
                "{% if state_attr('"
                + entity
                + "', 'start_time') %}\n\n{{ as_timestamp(state_attr('"
                + entity
                + "', 'start_time')) | timestamp_custom('%a %d %b · %H:%M') }}{% endif %}"
            )
        elif domain == "weather":
            content = (
                "**{{ "
                + safe_name
                + " }}**: {{ states('"
                + entity
                + "') }} · {{ state_attr('"
                + entity
                + "', 'temperature') }}{{ state_attr('"
                + entity
                + "', 'temperature_unit') or '' }}"
            )
        elif domain == "climate":
            content = "**{{ " + safe_name + " }}**: {{ states('" + entity + "') }}"
            for attribute, label in (("current_temperature", "Now"), ("temperature", "Target")):
                content += "{% if state_attr('" + entity + "', '" + attribute + "') is not none %} · " + label
                content += " {{ state_attr('" + entity + "', '" + attribute + "') }}{% endif %}"
        elif domain == "media_player":
            content = "{{ " + safe_name + " }}: {{ state_attr('" + entity + "', 'media_title') or states('" + entity + "') }}"
        else:
            content = "{{ " + safe_name + " }}: {{ states('" + entity + "') }}{{ state_attr('" + entity + "', 'unit_of_measurement') or '' }}"
        return {"type": "markdown", "content": content}
    if domain == "weather":
        return {"type": "weather-forecast", "entity": entity, "name": name, "show_forecast": False, "tap_action": {"action": "more-info"}}
    if domain == "calendar":
        return {"type": "calendar", "entities": [entity], "initial_view": "listWeek", "title": name}
    if domain == "climate":
        attrs = item.get("attributes", {})
        supported = attrs.get("supported_features", 0)
        supported = supported if type(supported) is int else 0
        features = []
        if supported & 3:
            features.append({"type": "target-temperature"})
        if variant != "compact" and attrs.get("hvac_modes"):
            features.append({"type": "climate-hvac-modes", "hvac_modes": attrs["hvac_modes"]})
        if variant != "compact" and supported & 8 and attrs.get("fan_modes"):
            features.append({"type": "climate-fan-modes", "style": "dropdown", "fan_modes": attrs["fan_modes"]})
        card = {"type": "thermostat" if variant == "large" and supported & 3 else "tile", "entity": entity, "name": name}
        if card["type"] == "thermostat":
            features = [f for f in features if f["type"] != "target-temperature"]
        if features:
            card["features"] = features
        if card["type"] == "tile":
            card.update(
                tap_action={"action": "more-info"}, state_content=["state"] + [a for a in ("current_temperature", "temperature") if attrs.get(a) is not None]
            )
        return card
    if domain == "cover" and item.get("device_class") == "damper":
        return {
            "type": "tile",
            "entity": entity,
            "name": name,
            "state_content": ["state", "current_position"],
            "tap_action": {"action": "none"},
            "icon_tap_action": {"action": "none"},
        }
    if domain == "media_player":
        return {"type": "media-control", "entity": entity, "name": name}
    card = {"type": "tile", "entity": entity, "name": name, "tap_action": {"action": "more-info"}, "icon_tap_action": {"action": "more-info"}}
    if surface["profile"] in ("phone", "bedside"):
        card["grid_options"] = {"columns": 12, "rows": 1}
    if item["interaction"] in ("control", "both") and domain in ("light", "fan", "switch", "input_boolean"):
        card["icon_tap_action"] = {"action": "toggle"}
    elif domain in ("scene", "script"):
        card["tap_action"] = {
            "action": "perform-action",
            "perform_action": domain + ".turn_on",
            "target": {"entity_id": entity},
            "confirmation": {"text": "Run " + name + "?"},
        }
    # Access/security always open native detail; never one-tap unlock/open/disarm.
    return card


def exception_card(item: dict, surface: dict) -> dict | None:
    domain, dc = item["domain"], item["device_class"]
    conditions = []
    if domain == "binary_sensor":
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "on"}]
    elif domain in ("light", "fan"):
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "on"}]
    elif domain == "cover" and dc in ("garage", "gate", "door"):
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": ["open", "opening"]}]
    elif domain == "lock":
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "unlocked"}]
    elif domain == "alarm_control_panel":
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "triggered"}]
    elif domain == "media_player":
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "playing"}]
    elif domain == "climate":
        # HVAC mode 'heat' does not mean equipment is currently heating.
        entity = item["entity_id"]
        name = json.dumps(item["name"], ensure_ascii=False)
        return {
            "type": "conditional",
            "conditions": [
                {"condition": "template", "value_template": "{{ state_attr('" + entity + "', 'hvac_action') in ['heating','cooling','drying','fan'] }}"}
            ],
            "card": {"type": "markdown", "content": "{{ " + name + " }} is running"},
        }
    elif domain == "event" and dc == "doorbell":
        conditions = [
            {"condition": "template", "value_template": "{{ 0 <= as_timestamp(now()) - as_timestamp(states('" + item["entity_id"] + "'), 0) < 120 }}"}
        ]
    elif domain == "vacuum":
        conditions = [{"condition": "state", "entity": item["entity_id"], "state": "error"}]
    if not conditions:
        return None
    card = card_for(item, surface, "compact")
    if item["level"] == 0:
        card = {"type": "markdown", "content": "**{{ " + json.dumps(item["name"], ensure_ascii=False) + " }}**: {{ states('" + item["entity_id"] + "') }}"}
    return {"type": "conditional", "conditions": conditions, "card": card}


def section(title: str, cards: list[dict]) -> dict:
    result = {"type": "grid", "cards": [{"type": "heading", "heading": title}] + cards}
    if cards and all(c["type"] == "conditional" for c in cards):
        result["visibility"] = [{"condition": "or", "conditions": [{"condition": "and", "conditions": c["conditions"]} for c in cards]}]
    return result


def room_summary(area: dict, items: list[dict], target: str) -> dict:
    """Summarize admitted items only; hidden or adult-only controls do not leak via an Area card."""
    lights = [i["entity_id"] for i in items if i["domain"] == "light"]
    temperatures = [i["entity_id"] for i in items if i["domain"] == "sensor" and i["device_class"] == "temperature"]
    media = [i["entity_id"] for i in items if i["domain"] == "media_player"]
    lines = []
    if temperatures:
        entity = temperatures[0]
        lines.append("{{ states('" + entity + "') }}{{ state_attr('" + entity + "', 'unit_of_measurement') or '' }}")
    if lights:
        lines.append("{% set n = expand(" + json.dumps(lights) + ") | selectattr('state', 'eq', 'on') | list | count %}{% if n %}{{ n }} lights on{% endif %}")
    for entity in media:
        lines.append("{% if is_state('" + entity + "', 'playing') %}{{ state_attr('" + entity + "', 'friendly_name') }} playing{% endif %}")
    return {
        "type": "vertical-stack",
        "cards": [
            {
                "type": "button",
                "name": area["name"],
                "icon": "mdi:home-outline",
                "tap_action": {"action": "navigate", "navigation_path": target},
                "hold_action": {"action": "none"},
            },
            {"type": "markdown", "content": "\n\n".join(lines) or "Room controls"},
        ],
        "grid_options": {"columns": 6, "rows": "auto"},
    }


def generate(house: dict, surface: dict, items: list[dict], areas: list[dict], activity: list[dict] | None = None, policy: dict | None = None) -> dict:
    if policy and policy.get("members"):
        house = copy.deepcopy(house)
        for person in house["people"]:
            if policy["members"].get(person["id"], {}).get("kind") == "child":
                person["audience"] = "everyone"
    source_areas = {i["id"]: i["area_id"] for i in items}
    activity = activity or []
    activity_decision = (policy or {}).get("features", {}).get("appliances")
    if activity_decision:
        activity = [
            a
            for a in activity
            if activity_decision["intent"] == "wanted" and surface["id"] in activity_decision["screens"] and a.get("source") in activity_decision["sources"]
        ]
    if surface["profile"] in ("specialist", "kitchen", "bedside"):
        activity = [a for a in activity if surface["area_id"] and source_areas.get(a.get("source")) == surface["area_id"]]
    all_items = items
    # Discovery is not consent to expose calendars or identities on every screen.
    items = [i for i in items if allowed(i, surface, house, policy)]
    items = [
        {**item, "reason": item["reason"] + " Selected for this display in Home Readiness; source/member checks passed."}
        if item["domain"] in ("calendar", "person", "device_tracker")
        else item
        for item in items
    ]
    pref = preferences(house, surface)
    eligible = [i for i in items if admitted(i, surface, house, pref)]
    # Alarm interruption is informational for everyone; its control remains adult-only.
    for item in all_items:
        if item["domain"] == "alarm_control_panel" and item.get("available", item["usable"]):
            alert = {
                **item,
                "id": "alert:" + item["id"],
                "level": 0,
                "audience": "everyone",
                "interaction": "status",
                "name": "Security alarm",
                "visibility": "when_abnormal",
                "component": "alert",
                "function": "safety",
                "surfaces": list(PROFILES),
                "reason": "An informational security interruption, shown only while triggered.",
                "usable": True,
            }
            if admitted(alert, surface, house, pref):
                eligible.append(alert)
    rank = {item: pos for pos, item in enumerate(pref["order"])}
    eligible.sort(key=lambda i: (i["level"], i["id"] not in pref["pin"], rank.get(i["id"], 9999), i["name"].casefold(), i["id"]))
    profile = surface["profile"]
    if profile in ("phone", "tablet", "specialist"):
        return touch_dashboard(house, surface, items, eligible, areas, activity or [])
    path = "home-starter-" + surface["id"].replace("_", "-")
    base = "/" + path
    sections, details, other_access = [], [], []
    if profile in ("wall", "kitchen", "bedside"):
        sections.append(section("Today", [{"type": "clock", "clock_size": "large"}]))
    alerts = [exception_card(i, surface) for i in eligible if i["level"] == 0 or i["domain"] == "alarm_control_panel"]
    if any(alerts):
        sections.append(section("Needs attention", [c for c in alerts if c]))
    active = [exception_card(i, surface) for i in eligible if i["level"] != 0 and i["domain"] != "alarm_control_panel"]
    climate = [i for i in eligible if i["function"] == "climate" and i["level"] == 2]
    if profile == "specialist":
        sections.append(
            section(
                "Air conditioning",
                [card_for(i, surface, "large") for i in climate]
                or [{"type": "markdown", "content": "No available air conditioning in this room. Choose its room in Home Starter."}],
            )
        )
    if profile not in ("wall",):
        quick = [i for i in eligible if i["level"] == 2 and (i["id"] in pref["pin"] or i["scope"] == "whole_house")]
        unplaced = [i for i in eligible if i["level"] in (2, 4) and not i["area_id"] and i not in quick]
        if unplaced:
            # Still reachable deliberately, without flooding the main screen.
            other_access = [
                {
                    "type": "button",
                    "name": "Other controls",
                    "icon": "mdi:dots-horizontal",
                    "tap_action": {"action": "navigate", "navigation_path": base + "/other-controls"},
                    "hold_action": {"action": "none"},
                }
            ]
            details.append(
                {
                    "type": "sections",
                    "title": "Other controls",
                    "path": "other-controls",
                    "subview": True,
                    "sections": [section("Other controls", [card_for(i, surface) for i in unplaced])],
                }
            )
        quick = [i for i in quick if not (profile == "specialist" and i in climate)]
        if quick:
            sections.append(section("Quick actions", [card_for(i, surface) for i in quick]))
        room_cards = []
        for area in areas:
            area_items = [i for i in eligible if i["area_id"] == area["area_id"]]
            if not area_items or "room:" + area["area_id"] in pref["hide"]:
                continue
            room_path = "room-" + hashlib.sha256(area["area_id"].encode()).hexdigest()[:10]
            room_cards.append((area["area_id"], room_summary(area, area_items, base + "/" + room_path)))
            detail_cards = [card_for(i, surface) for i in area_items if i["level"] != 0]
            details.append({"type": "sections", "title": area["name"], "path": room_path, "subview": True, "sections": [section(area["name"], detail_cards)]})
        area_rank = {r: n for n, r in enumerate(pref["order"])}
        room_cards.sort(key=lambda c: ("room:" + c[0] not in pref["pin"], area_rank.get("room:" + c[0], 9999)))
        if room_cards:
            sections.append(section("Rooms", [c[1] for c in room_cards]))
    if any(active):
        sections.append(section("Happening now", [c for c in active if c]))
    context = [i for i in eligible if i["level"] == 3 and (profile not in ("specialist", "bedside") or i["domain"] in ("weather", "timer"))]
    if context:
        sections.append(section("What's next" if profile == "wall" else "Household", [card_for(i, surface) for i in context]))
    if activity:
        cards = [
            card_for({"entity_id": a["entity_id"], "name": a["name"] + " cycles today", "domain": "sensor", "interaction": "status"}, surface) for a in activity
        ]
        sections.append(section("Activity today", cards))
    if other_access:
        sections.append(section("More controls", other_access))
    if not sections:
        sections.append(
            section("Home", [{"type": "markdown", "content": "No available household controls yet. Review rooms and household names in Home Starter."}])
        )
    home = {"type": "sections", "title": "Home", "path": "home", "max_columns": 1 if profile in ("phone", "bedside", "specialist") else 3, "sections": sections}
    views = [home]
    if profile == "tablet":
        for title, function in (("Climate", "climate"), ("Media", "media"), ("Security", "access"), ("Household", "information")):
            group = [
                i
                for i in eligible
                if i["level"] > 0 and i["visibility"] == "always" and (i["function"] == function or title == "Security" and i["function"] == "security")
            ]
            if group:
                views.append(
                    {
                        "type": "sections",
                        "title": title,
                        "path": title.lower(),
                        "sections": [section(title, [card_for(i, surface) for i in group if i["visibility"] == "always"])],
                    }
                )
    views += details
    config = {"title": surface["name"], "views": views}
    return {
        "surface": surface,
        "url_path": path,
        "config": config,
        "fingerprint": fingerprint(config),
        "admitted": eligible,
        "catalogue": [{"id": k, "native": v[0], "status": v[1], "variants": ["compact", "normal", "large"]} for k, v in CATALOGUE.items()],
        "warnings": [
            "Names and audience choices arrange screens; they do not change Home Assistant account permissions.",
            "Activity today is a snapshot. Regenerate to refresh it; live appliance state still updates in Home Assistant.",
            "Calling, event takeover and music favourites need a supported source and are not installed by this version.",
        ],
    }


def navigation(name: str, target: str, icon: str = "mdi:arrow-expand") -> dict:
    return {"type": "button", "name": name, "icon": icon, "tap_action": {"action": "navigate", "navigation_path": target}, "hold_action": {"action": "none"}}


def touch_dashboard(house: dict, surface: dict, items: list[dict], eligible: list[dict], areas: list[dict], activity: list[dict]) -> dict:
    """Native people + House shell. All expansion paths stay inside the owned dashboard."""
    path = "home-starter-" + surface["id"].replace("_", "-")
    base = "/" + path
    views, details = [], []
    columns = 1 if surface["profile"] in ("phone", "specialist") else 3

    def view(title, view_path, sections, parent=None):
        result = {"type": "sections", "title": title, "path": view_path, "max_columns": columns, "sections": sections}
        if parent:
            result.update(subview=True, back_path=base + "/" + parent)
        return result

    def page(title, page_path, selected, person_surface):
        pref = preferences(house, person_surface)
        rank = {key: n for n, key in enumerate(pref["order"])}
        selected = sorted(selected, key=lambda i: (i["level"], i["id"] not in pref["pin"], rank.get(i["id"], 9999), i["name"].casefold(), i["id"]))
        alerts = [c for i in selected if i["level"] == 0 if (c := exception_card(i, person_surface))]
        sections = [section("Needs attention", alerts)] if alerts else []

        def expand(label, suffix, cards, icon="mdi:arrow-expand"):
            target = suffix if page_path == "home" else page_path + "-" + suffix
            details.append(view(label, target, ([section("Needs attention", alerts)] if alerts else []) + [section(label, cards)], page_path))
            return navigation(label, base + "/" + target, icon)

        climate = [i for i in selected if i["function"] == "climate" and i["level"] == 2]
        if climate:
            # Main units advertise fan modes; this orders the glance without guessing identities.
            main = next((i for i in climate if i.get("attributes", {}).get("fan_modes")), climate[0])
            controls = [card_for(main, person_surface, "large")] + [card_for(i, person_surface) for i in climate if i is not main]
            glance = card_for(main, person_surface, "large" if surface["profile"] == "specialist" else "compact")
            if glance["type"] == "tile":
                glance["tap_action"] = {"action": "navigate", "navigation_path": base + "/" + ("climate" if page_path == "home" else page_path + "-climate")}
            sections.append(
                section(
                    "Air conditioning" if surface["profile"] == "specialist" else "Climate", [glance, expand("Climate", "climate", controls, "mdi:thermostat")]
                )
            )
        active = [
            c
            for i in selected
            if i["level"] != 0 and i["domain"] not in ("climate", "media_player", "alarm_control_panel")
            if (c := exception_card(i, person_surface))
        ]
        if active:
            sections.append(section("Happening now", active))
        calendars = [i for i in selected if i["domain"] == "calendar"]
        if calendars:
            # Consume HA calendars; never fetch or aggregate external ICS feeds.
            summary = card_for(calendars[0], {**person_surface, "profile": "phone"})
            sections.append(
                section("Today", [summary, expand("Today", "today", [card_for(i, {**person_surface, "profile": "tablet"}) for i in calendars], "mdi:calendar")])
            )
        quick = [i for i in selected if i["level"] == 2 and i not in climate and (i["id"] in pref["pin"] or i["scope"] == "whole_house")]
        if quick:
            sections.append(section("Quick actions", [card_for(i, person_surface) for i in quick]))
        room_cards = []
        for area in areas:
            area_items = [i for i in selected if i["area_id"] == area["area_id"] and i["level"] != 0]
            if not area_items or "room:" + area["area_id"] in pref["hide"]:
                continue
            room_path = "room-" + hashlib.sha256(area["area_id"].encode()).hexdigest()[:10]
            if page_path != "home":
                room_path = page_path + "-" + room_path
            room_cards.append((area["area_id"], room_summary(area, area_items, base + "/" + room_path)))
            details.append(
                view(
                    area["name"],
                    room_path,
                    ([section("Needs attention", alerts)] if alerts else []) + [section(area["name"], [card_for(i, person_surface) for i in area_items])],
                    page_path,
                )
            )
        room_cards.sort(key=lambda c: ("room:" + c[0] not in pref["pin"], rank.get("room:" + c[0], 9999)))
        unplaced = [i for i in selected if i["level"] == 2 and not i["area_id"] and i not in climate and i not in quick]
        home_cards = [c[1] for c in room_cards]
        if unplaced:
            sections.append(section("More controls", [expand("Other controls", "other-controls", [card_for(i, person_surface) for i in unplaced])]))
        if home_cards:
            sections.append(section("Home / Rooms", [expand("Home / Rooms", "rooms", home_cards, "mdi:home-outline")]))
        media = [i for i in selected if i["domain"] == "media_player"]
        if media:
            glance = {
                "type": "tile",
                "entity": media[0]["entity_id"],
                "name": media[0]["name"],
                "tap_action": {"action": "navigate", "navigation_path": base + "/" + ("music" if page_path == "home" else page_path + "-music")},
            }
            supported = media[0].get("attributes", {}).get("supported_features", 0)
            if type(supported) is int and supported & 513 == 513:
                glance["features"] = [{"type": "media-player-playback"}]
            sections.append(section("Music", [glance, expand("Music", "music", [card_for(i, person_surface) for i in media], "mdi:music")]))
        context = [i for i in selected if i["level"] == 3 and i["domain"] != "calendar"]
        if context:
            sections.append(section("Around the house", [expand("Around the house", "context", [card_for(i, person_surface) for i in context])]))
        if activity:
            sections.append(
                section(
                    "Activity today",
                    [
                        card_for(
                            {"entity_id": a["entity_id"], "name": a["name"] + " cycles today", "domain": "sensor", "interaction": "status"}, person_surface
                        )
                        for a in activity
                    ],
                )
            )
        if not sections:
            sections.append(section(title, [{"type": "markdown", "content": "No available household sources yet."}]))
        if page_path == "home":
            sections.append(
                section("Display", [navigation("Ambient", base + "/ambient", "mdi:weather-night"), navigation("Dark", base + "/dark", "mdi:monitor-off")])
            )
        return view(title, page_path, sections)

    views.append(page("House", "home", eligible, surface))
    # Saved list order is intentional and stable; names are display text, IDs form routes.
    for person in house["people"]:
        personal = {**surface, "person_id": person["id"]}
        personal_pref = preferences(house, personal)
        own_rooms = {s["area_id"] for s in house["surfaces"] if s["person_id"] == person["id"] and s["area_id"]}
        selected = [
            i
            for i in items
            if admitted(i, surface, house, preferences(house, {**surface, "person_id": None}))
            and admitted(i, personal, house, personal_pref)
            and (person["audience"] == "adult" or i["level"] == 0 or i["scope"] == "whole_house" or i["area_id"] in own_rooms)
        ]
        selected += [i for i in eligible if i["id"].startswith("alert:")]
        # Hex has no hyphens: a valid ID like alex-climate cannot collide with
        # Alex's contextual -climate route. Encoding is reversible and collision-free.
        views.append(page(person["name"], "person-" + person["id"].encode().hex(), selected, personal))
    # Lifecycle is per browser navigation, never a household-global helper.
    alerts = [c for i in eligible if i["level"] == 0 if (c := exception_card(i, surface))]
    quiet = {**surface, "profile": "wall"}
    glance = [card_for(i, quiet) for i in eligible if i["domain"] in ("climate", "calendar")]
    playing = [c for i in eligible if i["domain"] == "media_player" if (c := exception_card(i, quiet))]
    ambient = ([section("Needs attention", alerts)] if alerts else []) + [
        section("Today", [{"type": "clock", "clock_size": "large"}] + glance + playing),
        section("Display", [navigation("Active", base + "/home", "mdi:home"), navigation("Dark", base + "/dark", "mdi:monitor-off")]),
    ]
    dark = ([section("Needs attention", alerts)] if alerts else []) + [section("", [navigation("Wake", base + "/home", "mdi:gesture-tap")])]
    dark_view = view("Dark", "dark", dark, "home")
    dark_view["background"] = {"color": "#000000"}
    config = {"title": surface["name"], "views": views + details + [view("Ambient", "ambient", ambient, "home"), dark_view]}
    return {
        "surface": surface,
        "url_path": path,
        "config": config,
        "fingerprint": fingerprint(config),
        "admitted": eligible,
        "catalogue": [{"id": k, "native": v[0], "status": v[1], "variants": ["compact", "normal", "large"]} for k, v in CATALOGUE.items()],
        "warnings": [
            "People tabs arrange content, not Home Assistant permissions. Shared screen audience caps every page.",
            "Ambient and Dark are manual native views. Dark keeps a Wake target, HA chrome and safety alerts; it does not turn off the panel.",
            "Automatic inactivity, brightness, full black and physical wake/sleep require verified device management, "
            "such as Fully Kiosk with Remote Administration and its HA integration.",
            "AirTouch damper positions are informational; automatic zone temperature control remains authoritative.",
        ],
    }


async def publish(core: CoreClient, generated: dict, expected: str | None, records: dict) -> dict:
    """Only own tracked dashboards. Never overwrite unknown or externally edited content."""
    path = generated["url_path"]
    async with core.websocket() as ws:
        dashboards = await ws.command("lovelace/dashboards/list")
        existing = next((d for d in dashboards if d.get("url_path") == path), None)
        if existing:
            if path not in records:
                raise ValueError("This screen address already belongs to another dashboard.")
            current = await ws.command("lovelace/config", url_path=path, force=True)
            if fingerprint(current) != expected or expected != records[path].get("fingerprint"):
                raise ValueError("This dashboard changed in Home Assistant. Preserve those edits; create a new screen instead.")
            if fingerprint(current) == generated["fingerprint"]:
                return {"url_path": path, "fingerprint": expected, "verified": True}
        elif expected is not None:
            raise ValueError("The published dashboard is missing. Refresh before publishing.")
        else:
            await ws.command(
                "lovelace/dashboards/create", url_path=path, title=generated["surface"]["name"], require_admin=False, show_in_sidebar=True, icon="mdi:home"
            )
        await ws.command("lovelace/config/save", url_path=path, config=generated["config"])
        readback = await ws.command("lovelace/config", url_path=path, force=True)
        if readback != generated["config"]:
            raise CoreError("api", "Dashboard save could not be verified. Inspect it in Home Assistant before retrying.")
    return {"url_path": path, "fingerprint": fingerprint(readback), "verified": True}
