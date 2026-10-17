"""Household decisions and bounded verification. Never store credentials or event contents."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

from . import context
from .household import HouseholdStore

CAPABILITIES = {
    "music": ("Music", {"media_player"}, "#music"),
    "communications": ("Communications", set(), "/config/integrations"),
    "calendars": ("Calendars", {"calendar"}, "/calendar"),
    "waste": ("Waste collection", {"calendar"}, "/calendar"),
    "climate": ("Climate", {"climate"}, "#house-climate"),
    "cameras": ("Cameras and doorbells", {"camera", "event"}, "/config/integrations"),
    "presence": ("Presence", {"person", "device_tracker"}, "/config/person"),
    "voice": ("Voice", {"assist_satellite"}, "/config/voice-assistants"),
    "appliances": ("Appliances", {"vacuum"}, "#household-activities"),
    "lighting": ("Lighting and power", {"light"}, "#your-home"),
}
ANSWERS = {
    "music": {
        "providers": {"spotify", "apple_music", "local", "radio", "podcasts", "other"},
        "accounts": {"shared", "individual", "mixed"},
        "groups": {"none", "configure_in_ma"},
    },
    "communications": {"service": {"existing", "new", "none"}, "uses": {"internal", "external", "door_gate"}},
    "voice": {"plan": {"keep", "remove", "replace"}, "controls": {"lights", "climate", "media", "other"}},
    "presence": {"purpose": {"display_only", "lighting", "climate", "security"}},
}
SINGLE_ANSWERS = {"accounts", "groups", "service", "plan"}
SIP = {"asterisk", "asterisk_mbox", "voip", "sip", "linphone"}
WASTE = {"waste_collection_schedule", "waste_collection", "recollect"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def empty(epoch):
    return {"version": 2, "epoch": epoch, "revision": 0, "choices": {}, "members": {}, "devices": {}, "verified": {}, "context": context.empty()}


def load(store: HouseholdStore, house: dict) -> dict:
    value = store.read(store.readiness_path, None)
    if value is None:
        return empty(house["epoch"])
    if isinstance(value, dict) and type(value.get("version")) is int and value["version"] == 1:
        if set(value) != set(empty(0)) - {"context"}:
            raise ValueError("Unsupported Home Readiness state. Existing data is preserved.")
        value = {**value, "version": 2, "context": context.empty()}
    if (
        not isinstance(value, dict)
        or set(value) != set(empty(0))
        or type(value.get("version")) is not int
        or value["version"] != 2
        or type(value.get("epoch")) is not int
        or type(value.get("revision")) is not int
    ):
        raise ValueError("Unsupported Home Readiness state. Existing data is preserved.")
    if value["epoch"] != house["epoch"]:
        return empty(house["epoch"])
    if any(not isinstance(value[k], dict) for k in ("choices", "members", "devices", "verified")):
        raise ValueError("Invalid Home Readiness state.")
    context.validate(value["context"])
    return value


def entities(inventory):
    return [e for d in inventory["devices"] for e in d["entities"]] + inventory["unattached_entities"]


def discover(inventory, states, activities=()):
    live = {s["entity_id"]: s for s in states}
    result = {key: [] for key in CAPABILITIES}
    for entity in entities(inventory):
        if (
            entity.get("disabled_by")
            or entity.get("hidden_by")
            or entity.get("entity_category") in ("diagnostic", "config")
            or entity.get("platform") == "demo"
        ):
            continue
        identifier = entity["entity_id"]
        domain = identifier.split(".")[0]
        attrs = live.get(identifier, {}).get("attributes") or {}
        candidate = {
            "id": identifier,
            "name": entity["name"],
            "available": entity.get("observed") is True and entity.get("state") not in (None, "unknown", "unavailable"),
        }
        for key, (_, domains, _) in CAPABILITIES.items():
            if domain in domains and key != "waste" and (domain != "event" or attrs.get("device_class") == "doorbell"):
                result[key].append(candidate)
        # A label is only a suggestion, never admission or a verified schedule.
        if domain == "calendar":
            result["waste"].append(
                {
                    **candidate,
                    "likely": entity.get("platform") in WASTE or any(w in entity["name"].casefold() for w in ("waste", "recycling", "bin ", "bins", "rubbish")),
                }
            )
        if identifier in {a["entity_id"] for a in activities} and domain != "vacuum":
            result["appliances"].append(candidate)
    return result


def selection_signature(choice, inventory):
    wanted = set(choice.get("sources", []))
    sources = [{k: e.get(k) for k in ("entity_id", "registry_id", "device_id", "platform")} for e in entities(inventory) if e["entity_id"] in wanted]
    devices = [
        {"id": d["id"], "connection": d.get("connection_fingerprint")} for d in inventory["devices"] if any(e["entity_id"] in wanted for e in d["entities"])
    ]
    return digest([choice, sorted(sources, key=lambda e: e["entity_id"]), sorted(devices, key=lambda d: d["id"])])


def proof_valid(value, key, inventory, now=None):
    choice = value["choices"].get(key, {})
    proof = value["verified"].get(key, {})
    now = now or datetime.now(UTC)
    try:
        checked = datetime.fromisoformat(proof["at"])
        return timedelta(0) <= now - checked <= timedelta(days=1) and proof["signature"] == selection_signature(choice, inventory)
    except (KeyError, ValueError, TypeError):
        return False


def save(store, house, body, inventory, states, *, persist=True):
    current = load(store, house)
    if not inventory["complete"]:
        raise ValueError("Inventory is incomplete. Saved decisions are preserved.")
    if (
        set(body) != {"revision", "epoch", "choices", "members", "devices"}
        or type(body["revision"]) is not int
        or type(body["epoch"]) is not int
        or body["revision"] != current["revision"]
        or body["epoch"] != house["epoch"]
    ):
        raise ValueError("Readiness changed. Refresh before saving.")
    choices, members, devices = body["choices"], body["members"], body["devices"]
    if not all(isinstance(v, dict) for v in (choices, members, devices)) or not set(choices) <= CAPABILITIES.keys():
        raise ValueError("Unsupported readiness fields. Credentials belong in the connected service.")
    candidates = discover(inventory, states, house["activities"])
    screen_ids = {s["id"] for s in house["surfaces"]}
    people = {p["id"] for p in house["people"]}

    def subset(values, allowed):
        return isinstance(values, list) and all(isinstance(v, str) for v in values) and len(set(values)) == len(values) and set(values) <= allowed

    for key, choice in choices.items():
        if not isinstance(choice, dict) or set(choice) != {"intent", "sources", "screens", "answers", "permissions"}:
            raise ValueError("Unsupported capability choice.")
        if (
            choice["intent"] not in ("wanted", "not_wanted", "later")
            or not subset(choice["sources"], {s["id"] for s in candidates[key]} | set(current["choices"].get(key, {}).get("sources", [])))
            or not subset(choice["screens"], screen_ids | set(current["choices"].get(key, {}).get("screens", [])))
        ):
            raise ValueError("Choose existing sources and displays.")
        if key == "waste" and len(choice["sources"]) > 1:
            raise ValueError("Choose one collection source.")
        answers = choice["answers"]
        if not isinstance(answers, dict) or not set(answers) <= ANSWERS.get(key, {}).keys():
            raise ValueError("Unsupported interview answer. Do not enter credentials here.")
        if any(not subset(vals, ANSWERS[key][question]) for question, vals in answers.items()):
            raise ValueError("Choose a supported answer.")
        if any(len(vals) > 1 for question, vals in answers.items() if question in SINGLE_ANSWERS):
            raise ValueError("Choose one answer for this question.")
        permissions = choice["permissions"]
        if not isinstance(permissions, dict) or (permissions and key != "communications") or not set(permissions) <= people:
            raise ValueError("Call permissions must belong to saved household members.")
        if any(not subset(targets, people - {person}) for person, targets in permissions.items()):
            raise ValueError("Choose explicit internal call destinations per person.")
    all_entities = {e["entity_id"] for e in entities(inventory)}
    areas = {a["area_id"] for a in inventory["areas"]}
    device_ids = {d["id"] for d in inventory["devices"]}
    if (
        not set(members) <= people
        or not set(devices) <= device_ids | current["devices"].keys()
        or any(v not in ("ignored", "hidden") for v in devices.values())
    ):
        raise ValueError("Choose existing people or explicitly ignore/hide an existing device.")
    for member in members.values():
        if not isinstance(member, dict) or set(member) != {"kind", "rooms", "devices", "presence", "access"}:
            raise ValueError("Unsupported household context.")
        if member["kind"] not in ("adult", "child") or member["access"] not in ("yes", "no", "later"):
            raise ValueError("Review adult/child membership and HA access separately.")
        if (
            not subset(member["rooms"], areas)
            or not subset(member["devices"], device_ids)
            or not subset(member["presence"], {s["id"] for s in candidates["presence"]} & all_entities)
        ):
            raise ValueError("Choose existing rooms, devices and presence sources.")
    value = {**current, "choices": copy.deepcopy(choices), "members": copy.deepcopy(members), "devices": copy.deepcopy(devices)}
    if value != current:
        value["revision"] += 1
        if persist:
            store.write(store.readiness_path, value)
    return value


async def verify(core, value, key, inventory, states):
    choice = value["choices"].get(key, {})
    if not inventory["complete"] or choice.get("intent") != "wanted" or not choice.get("sources"):
        raise ValueError("Save a wanted capability and real source before verification.")
    candidates = {s["id"]: s for s in discover(inventory, states)[key]}
    if any(not candidates.get(source, {}).get("available") for source in choice["sources"]):
        raise ValueError("A selected source is missing or unavailable.")
    now = datetime.now(UTC)
    if key in ("calendars", "waste"):
        until = now + timedelta(days=90 if key == "waste" else 30)
        query = urlencode({"start": now.isoformat(), "end": until.isoformat()})
        events = []
        for source in choice["sources"]:
            received = await core.rest_get("/calendars/" + source + "?" + query)
            if not isinstance(received, list):
                raise ValueError("A selected calendar did not return a supported event list.")
            events.extend(received)

        def credible(event):
            if not isinstance(event, dict) or not isinstance(event.get("summary"), str) or not isinstance(event.get("start"), dict):
                return False
            start = event["start"]
            try:
                if start.get("dateTime"):
                    when = datetime.fromisoformat(start["dateTime"])
                    upcoming = when.tzinfo is not None and now <= when.astimezone(UTC) <= until
                else:
                    upcoming = now.date() <= date.fromisoformat(start["date"]) <= until.date()
            except (ValueError, KeyError, TypeError):
                return False
            return upcoming and bool(event["summary"].strip()) and (key != "waste" or collection_event(event, choice["sources"][0], inventory))

        # Calendar names and stale attributes are not a successful event read.
        if not isinstance(events, list) or not any(credible(event) for event in events):
            raise ValueError(
                "No verifiable upcoming collection event was returned."
                if key == "waste"
                else "No dated upcoming event was returned. Connect or repair the source, then verify again."
            )
        kind = "upcoming_collection" if key == "waste" else "upcoming_event"
    elif key == "cameras":
        cameras = [s for s in choice["sources"] if s.startswith("camera.")]
        if not cameras:
            raise ValueError("Select a native camera before checking a picture.")
        for camera in cameras:
            await core.check_camera(camera)
        kind = "native_snapshot"
    else:
        raise ValueError(
            "Automatic end-to-end verification is not supported here. Complete the secure service setup and test there; readiness remains incomplete."
        )
    value = copy.deepcopy(value)
    value["verified"][key] = {"at": now.isoformat(), "signature": selection_signature(choice, inventory), "kind": kind}
    value["revision"] += 1
    return value


def collection_event(event, source, inventory):
    collection = bool(re.search(r"\b(?:collection|waste|bins?|recycling|recycle|rubbish|garbage)\b", str(event.get("summary", "")), re.IGNORECASE))
    known_service = any(e["entity_id"] == source and e.get("platform") in WASTE for e in entities(inventory))
    return collection or known_service


def allowed(item, surface, house, policy):
    if policy and item.get("evidence", {}).get("device_id") in policy.get("excluded_devices", []) and item["level"] != 0:
        return False
    if item["domain"] not in ("calendar", "person", "device_tracker"):
        feature = {"media": "music", "climate": "climate", "appliance": "appliances", "lighting": "lighting"}.get(item["function"])
        decision = (policy or {}).get("features", {}).get(feature)
        if decision and item["level"] != 0:
            return decision["intent"] == "wanted" and surface["id"] in decision["screens"] and item["id"] in decision["sources"]
        return True
    if not policy:
        return False
    if item["domain"] == "calendar":
        if "calendar_access" in policy:
            from .calendar_access import permitted

            if not permitted(policy["calendar_access"], item["id"], person=surface.get("person_id"), mappings=policy.get("calendar_mappings", [])):
                return False
        return any(item["id"] in policy.get(key, []) and surface["id"] in policy.get(key + "_screens", []) for key in ("calendars", "waste"))
    return item["id"] in policy.get("presence", []) and surface["id"] in policy.get("presence_screens", [])


def policy_for(value, house, inventory, states, store=None):
    candidates = discover(inventory, states, house["activities"])
    result = {"excluded_devices": list(value["devices"]), "features": value["choices"], "members": value["members"]}
    for key in ("calendars", "waste", "presence", "cameras"):
        choice = value["choices"].get(key, {})
        if choice.get("intent") != "wanted":
            continue
        available = {s["id"] for s in candidates[key] if s["available"]}
        if key == "presence":
            linked = {s for person, member in value["members"].items() if person in {p["id"] for p in house["people"]} for s in member["presence"]}
            available &= linked
        elif not proof_valid(value, key, inventory):
            continue
        result[key] = [s for s in choice["sources"] if s in available]
        result[key + "_screens"] = choice["screens"]
    if store is not None:
        from . import calendar_access, household_services

        result["calendar_access"] = calendar_access.load(store, house)["calendars"]
        result["calendar_mappings"] = household_services.load(store, house)["calendars"]
    return result


def report(house, value, inventory, states, music):
    found = discover(inventory, states, house["activities"])
    integrations = {i["domain"] for i in inventory.get("integrations", [])}
    rows = []
    people = {p["id"] for p in house["people"]}
    unresolved = [d for d in inventory["devices"] if not d.get("area_id") and d["id"] not in value["devices"]]
    unreachable = [d for d in inventory["devices"] if d.get("unavailable_count", 0) or d.get("status") in ("offline", "unavailable")]
    members_complete = bool(people) and people <= value["members"].keys()
    rows += [
        {
            "id": "household",
            "title": "Household",
            "status": "Context recorded" if members_complete else "Membership/context incomplete",
            "route": "#household-people",
            "questions": ["Who lives here? Confirm adults/children, rooms, personal devices and who needs HA access."],
            "sources": [],
        },
        {
            "id": "rooms",
            "title": "Rooms",
            "status": f"{len(unresolved)} unassigned devices · {len(unreachable)} with unavailable sources",
            "route": "#your-home",
            "questions": ["Assign a room in Your home, or explicitly hide/ignore each unresolved device."],
            "sources": [],
        },
        {
            "id": "displays",
            "title": "Displays",
            "status": f"{len(house['surfaces'])} configured · roles selected in Screens",
            "route": "#surfaces",
            "questions": ["Choose shared/personal, room and interactive/display-only role for each screen."],
            "sources": [],
        },
    ]
    for key, (title, _, route) in CAPABILITIES.items():
        choice = value["choices"].get(key, {})
        detected = (
            bool(found[key])
            or key == "communications"
            and bool(integrations & SIP)
            or key == "music"
            and music.get("state")
            in {"ready", "stopped", "starting", "running_unverified", "needs_onboarding", "needs_integration", "integration_starting", "installing"}
            or key == "voice"
            and bool(integrations & {"google_assistant", "alexa"})
            or key == "appliances"
            and bool(house["activities"])
        )
        likely = any(s.get("likely") for s in found["waste"]) or bool(integrations & WASTE)
        ask = detected if key != "waste" else likely
        intent = choice.get("intent")
        questions = []
        if key in CAPABILITIES:
            questions = [f"Do you want {title.lower()} here? Choose sources and relevant displays."]
            if key == "music":
                questions += [
                    "Which providers: Spotify, local music, radio, podcasts or other?",
                    "Shared or individual accounts? Choose room speakers/groups; configure providers in Music Assistant and test playback there.",
                ]
            elif key == "communications":
                questions += [
                    "Existing SIP/VoIP service or a new one? Internal, external and door/gate calling are separate choices.",
                    "Configure server/account/authentication securely in the service. Confirm registration, extensions and an internal test call there.",
                    "Choose call destinations separately for every adult and child. Nothing is inherited or enabled here.",
                ]
            elif key == "calendars":
                questions += ["Which consolidated calendar? Verify a real upcoming event before showing it on chosen displays."]
            elif key == "waste":
                questions += ["Select the calendar you confirm contains collection dates; verify its next event. No schedule is invented."]
            elif key == "climate":
                questions += ["Review controller/connection drift. Test an advertised control in HA and restore it; discovery alone does not verify control."]
            elif key == "cameras":
                questions += [
                    "Check live view, events, recordings, doorbell press and intercom separately in HA. A camera entity does not prove these capabilities."
                ]
            elif key == "voice":
                questions += [
                    "Keep, remove or replace assistants? Select rooms and allowed controls in Voice assistants. Test there before calling it working."
                ]
            elif key == "presence":
                questions += [
                    "Link HA presence sources to actual household members. Is this display-only or intended for another purpose? No automation is created."
                ]
            elif key == "appliances":
                questions += ["Choose a documented completion transition and relevant room. Ran today is observed activity, not a chore assertion."]
            elif key == "lighting":
                questions += ["Review room assignment, powered-off/unreachable devices and test actual control in HA."]
        guide = questions
        if not ((ask and intent is None) or intent == "wanted"):
            questions = []
        status = "Not configured" if not detected else "Discovered · decision needed"
        if key == "music" and music.get("state") == "unavailable":
            status = "Music Assistant check unavailable"
        if intent == "not_wanted":
            status = "Not wanted"
        elif intent == "later":
            status = "Not now · deferred"
        elif intent == "wanted":
            chosen = set(choice["sources"])
            healthy = bool(chosen) and chosen <= {s["id"] for s in found[key] if s["available"]}
            status = "Source missing or unavailable" if not healthy else "Setup/test incomplete"
            if key == "communications":
                status = "Service, registration and call test incomplete"
            if key == "music":
                if music.get("state") in ("stopped", "unavailable"):
                    status = "Music Assistant stopped" if music["state"] == "stopped" else "Music Assistant check unavailable"
                else:
                    status = "Provider choice/setup unverified" if not choice["answers"].get("providers") else "Provider/playback unverified"
                if music.get("runtime", {}).get("proof"):
                    status = "Verified chosen provider and speaker · other paths untested"
            if key in ("calendars", "waste") and healthy and proof_valid(value, key, inventory):
                status = "Verified upcoming event" if choice["screens"] else "Verified source · choose displays"
            if key == "cameras" and healthy and proof_valid(value, key, inventory):
                status = "Native picture checked · events, recordings and intercom untested"
            if key == "presence":
                status = "Member links/intent incomplete" if not members_complete or not choice["sources"] else "Linked sources · no automation configured"
        rows.append(
            {
                "id": key,
                "title": title,
                "status": status,
                "route": route,
                "questions": questions,
                "guide": guide,
                "sources": found[key]
                + [
                    {"id": source, "name": "Missing saved source", "available": False}
                    for source in choice.get("sources", [])
                    if source not in {s["id"] for s in found[key]}
                ],
                "detected": bool(detected),
                "lifecycle": {
                    "discover": bool(detected),
                    "ask": intent is not None,
                    "source_selection": bool(choice.get("sources")),
                    "configure": key in ("calendars", "waste", "cameras") and bool(choice.get("screens")) and proof_valid(value, key, inventory),
                    "verify": proof_valid(value, key, inventory)
                    if key in ("calendars", "waste", "cameras")
                    else key == "music" and bool(music.get("runtime", {}).get("proof")),
                    "monitor": inventory["complete"],
                },
            }
        )
    return {
        "state": value,
        "rows": rows,
        "inventory_complete": inventory["complete"],
        "unassigned": [{"id": d["id"], "name": d["name"]} for d in unresolved],
        "room_devices": [{"id": d["id"], "name": d["name"]} for d in inventory["devices"] if not d.get("area_id")],
        "areas": inventory["areas"],
        "devices": [{"id": d["id"], "name": d["name"]} for d in inventory["devices"]],
        "people": house["people"],
        "screens": house["surfaces"],
        "answer_options": {k: {q: sorted(v) for q, v in qs.items()} for k, qs in ANSWERS.items()},
    }
