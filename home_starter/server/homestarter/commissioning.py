"""Persistent commissioning draft and reviewed execution; no implicit HA writes."""

from __future__ import annotations

import copy
import secrets
from datetime import UTC, datetime, timedelta

from . import calendar_access
from . import readiness as r
from .core import CoreError
from .household import validate_household
from .surfaces import classify, generate, publish

PHASES = {
    "not_started",
    "preparing",
    "scanned",
    "household_defined",
    "capabilities_selected",
    "configuration_incomplete",
    "reviewed",
    "executing",
    "verification_incomplete",
    "commissioned",
}
KEYS = set(r.CAPABILITIES) | {"displays"}


def load(store):
    house = store.load()
    value = store.read(store.commissioning_path, None)
    if value is None:
        return {
            "version": 1,
            "epoch": house["epoch"],
            "revision": 0,
            "phase": "not_started",
            "active": not house["configured"],
            "legacy": house["configured"],
            "draft": {
                "house": house,
                "readiness": r.load(store, house),
                "selected": [key for key, choice in r.load(store, house)["choices"].items() if choice["intent"] == "wanted"],
                "publish_ids": [],
                "install_music": False,
            },
            "scan": None,
            "review": None,
            "results": {},
        }
    if (
        not isinstance(value, dict)
        or type(value.get("version")) is not int
        or value["version"] != 1
        or value.get("phase") not in PHASES
        or type(value.get("revision")) is not int
        or type(value.get("epoch")) is not int
        or type(value.get("active")) is not bool
        or not isinstance(value.get("draft"), dict)
        or not isinstance(value.get("results"), dict)
        or value["epoch"] != house["epoch"]
    ):
        raise ValueError("Commissioning data could not be read. Existing setup is preserved.")
    return value


def write(store, value):
    value["revision"] += 1
    store.write(store.commissioning_path, value)
    return value


def precondition(value, body):
    if type(body.get("revision")) is not int or type(body.get("epoch")) is not int or any(body[k] != value[k] for k in ("revision", "epoch")):
        raise ValueError("Setup changed elsewhere. Reload the saved draft before continuing.")


def gate(store):
    value = load(store)
    if value["active"] and value["phase"] != "commissioned":
        raise ValueError("Review your commissioning plan and use Set up my home before applying changes.")


def begin(store, value):
    if value["phase"] in ("executing", "verification_incomplete", "commissioned"):
        raise ValueError("Continue the saved execution or use maintenance to add capabilities.")
    if not value["active"]:
        house = store.load()
        rd = r.load(store, house)
        value["draft"] = {
            "house": house,
            "readiness": rd,
            "selected": [key for key, choice in rd["choices"].items() if choice["intent"] == "wanted"],
            "publish_ids": [],
            "install_music": False,
        }
    value.update(active=True, phase="preparing", review=None)
    return write(store, value)


def summary(inventory, states):
    candidates = r.discover(inventory, states)
    entities = [e for e in r.entities(inventory) if e.get("platform") != "demo" and not e.get("disabled_by") and not e.get("hidden_by")]
    return {
        "lights and switches": sum(e["entity_id"].split(".")[0] in ("light", "switch") for e in entities),
        "audio and media sources": len(candidates["music"]),
        "climate sources and zones": len(candidates["climate"]),
        "cameras and doorbell sources": len(candidates["cameras"]),
        "rooms": len(inventory["areas"]),
        "calendars": len(candidates["calendars"]),
        "devices without rooms": sum(not d.get("area_id") for d in inventory["devices"]),
        "devices needing attention": sum(d.get("status") != "fine" for d in inventory["devices"]),
    }


def validate_draft(store, value, draft, inventory, states):
    if not isinstance(draft, dict) or set(draft) != {"house", "readiness", "selected", "publish_ids", "install_music"}:
        raise ValueError("Unsupported commissioning draft. Credentials belong in the service.")
    house = validate_household(draft["house"])
    current = store.load()
    if any(house[k] != current[k] for k in ("revision", "epoch", "configured", "preferences", "overrides", "activities")):
        raise ValueError("Existing settings changed. Reload before reviewing; saved configuration is preserved.")
    if not house["people"]:
        raise ValueError("Add at least one household member before creating personal views.")
    rd = draft["readiness"]
    if not isinstance(rd, dict) or not {p["id"] for p in house["people"]} <= rd.get("members", {}).keys():
        raise ValueError("Confirm adult/child membership and household context for each person.")
    r.save(store, house, {k: rd[k] for k in ("revision", "epoch", "choices", "members", "devices")}, inventory, states, persist=False)
    for key, allowed in (("selected", KEYS), ("publish_ids", {s["id"] for s in house["surfaces"]})):
        values = draft[key]
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values) or len(set(values)) != len(values) or not set(values) <= allowed:
            raise ValueError("Choose existing capabilities and screens.")
    if type(draft["install_music"]) is not bool or draft["install_music"] and "music" not in draft["selected"]:
        raise ValueError("Select Music before requesting its installer.")
    if draft["publish_ids"] and "displays" not in draft["selected"]:
        raise ValueError("Select household displays before requesting publication.")
    for key in r.CAPABILITIES:
        wanted = rd["choices"].get(key, {}).get("intent") == "wanted"
        if wanted != (key in draft["selected"]):
            raise ValueError("Capability selections changed. Review their configuration before continuing.")
    return copy.deepcopy(draft)


def save_draft(store, value, draft, step, inventory, states):
    if value["phase"] in ("not_started", "preparing", "executing", "verification_incomplete", "commissioned") or value["scan"] is None:
        raise ValueError("Scan the prepared house before defining and reviewing setup.")
    phases = {"household": "household_defined", "choose": "capabilities_selected", "configure": "configuration_incomplete"}
    if step not in phases:
        raise ValueError("Choose a supported setup step.")
    draft = validate_draft(store, value, draft, inventory, states)
    value.update(draft=draft, phase=phases[step], review=None)
    return write(store, value)


async def make_review(store, value, core, inventory, states, music):
    if value["phase"] not in ("capabilities_selected", "configuration_incomplete", "reviewed"):
        raise ValueError("Define the household and choose capabilities before review.")
    draft = validate_draft(store, value, value["draft"], inventory, states)
    rd = copy.deepcopy(draft["readiness"])
    checks = {}
    for key in ("calendars", "waste"):
        if key not in draft["selected"]:
            continue
        try:
            rd = await r.verify(core, rd, key, inventory, states)
            checks[key] = {"status": "verified", "detail": "Real upcoming event retrieved (read only)."}
        except (ValueError, CoreError):
            rd["verified"].pop(key, None)
            checks[key] = {"status": "incomplete", "detail": "Choose/connect a source with a real upcoming event, then retry."}
    records = store.read(store.publication_path, {})
    generated = [
        {
            "generated": generate(
                draft["house"],
                screen,
                classify(inventory, states, draft["house"]["overrides"]),
                inventory["areas"],
                policy=r.policy_for(rd, draft["house"], inventory, states, store),
            ),
            "expected": records.get("home-starter-" + screen["id"].replace("_", "-"), {}).get("fingerprint"),
        }
        for screen in draft["house"]["surfaces"]
        if screen["id"] in draft["publish_ids"]
    ]
    automatic = ["Save household membership, screen roles and selected capability decisions locally."]
    automatic += ["Publish reviewed screen: " + item["generated"]["surface"]["name"] for item in generated]
    if draft["install_music"]:
        automatic.append("Run the Music Assistant installer; retain an existing installation and its configuration.")
    manual = [
        r.CAPABILITIES[key][0] + ": finish secure service setup and verify operation there."
        for key in draft["selected"]
        if key not in ("calendars", "waste", "presence", "displays")
    ]
    value.update(
        phase="reviewed",
        review={
            "token": secrets.token_hex(16),
            "at": datetime.now(UTC).isoformat(),
            "draft_hash": r.digest(draft),
            "house_revision": store.load()["revision"],
            "readiness_revision": r.load(store, store.load())["revision"],
            "calendar_revision": calendar_access.load(store, store.load())["revision"],
            "source_signature": source_signature(inventory, states),
            "checks": checks,
            "proofs": rd["verified"],
            "screens": generated,
            "automatic": automatic,
            "sign_in": ["Music providers and calling accounts: sign in only in their own service; no credentials are collected here."]
            if {"music", "communications"} & set(draft["selected"])
            else [],
            "manual": manual,
            "music_state": music.get("state", "unavailable"),
        },
    )
    return write(store, value)


def source_signature(inventory, states):
    # Live values fluctuate; bind the review to identities, connection metadata,
    # availability and advertised control capabilities, not temperatures or events.
    found = r.discover(inventory, states)
    return r.digest(
        [
            [
                {k: e.get(k) for k in ("entity_id", "registry_id", "device_id", "platform", "area_id", "disabled_by", "hidden_by")}
                for e in r.entities(inventory)
            ],
            [{k: d.get(k) for k in ("id", "area_id", "connection_fingerprint")} for d in inventory["devices"]],
            found,
            [
                {"id": s["entity_id"], "attrs": {k: (s.get("attributes") or {}).get(k) for k in ("supported_features", "hvac_modes", "device_class")}}
                for s in states
            ],
        ]
    )


def check_go(store, value, token, inventory, states):
    review = value.get("review")
    if value["phase"] != "reviewed" or not isinstance(review, dict) or token != review["token"]:
        raise ValueError("Review the current plan before Set up my home.")
    if not inventory["complete"] or source_signature(inventory, states) != review["source_signature"]:
        raise ValueError("Discovery changed or is incomplete. Scan and review the plan again.")
    if datetime.now(UTC) - datetime.fromisoformat(review["at"]) > timedelta(minutes=10):
        raise ValueError("This review expired. Review the current plan again.")
    house = store.load()
    if (
        review["draft_hash"] != r.digest(value["draft"])
        or house["revision"] != review["house_revision"]
        or r.load(store, house)["revision"] != review["readiness_revision"]
        or calendar_access.load(store, house)["revision"] != review.get("calendar_revision", 0)
    ):
        raise ValueError("Saved settings changed. Review again before applying changes.")


async def execute(store, value, core, setup, user, music_runtime=None):
    """Journal each independent result; retries never replay successful writes."""
    results = value["results"]

    def record(key, status, detail, **extra):
        results[key] = {"status": status, "detail": detail, **extra}
        write(store, value)

    try:
        if results.get("household", {}).get("status") != "verified":
            intended = value["draft"]["house"]
            current = store.load()
            requested = value["draft"]["readiness"]
            rd = r.load(store, current)
            if any(rd[k] != requested[k] for k in ("choices", "members", "devices")):
                rd = r.save(
                    store,
                    intended,
                    {k: requested[k] for k in ("revision", "epoch", "choices", "members", "devices")},
                    await _inventory(core),
                    await core.states(),
                    persist=False,
                )
            # Resume a completed local save after interruption; never overwrite a
            # household that differs from this reviewed intent.
            if any(current[k] != intended[k] for k in intended if k not in ("revision", "configured")):
                house = store.save(intended)
            elif current["configured"]:
                house = current
            else:
                house = store.save(intended)
            rd["verified"] = copy.deepcopy(value["review"]["proofs"])
            store.write(store.readiness_path, rd)
            record("household", "verified", "Household and decisions saved.")
        for key in value["draft"]["selected"]:
            if key == "displays" or results.get(key, {}).get("status") in ("verified", "skipped"):
                continue
            if key in ("calendars", "waste"):
                try:
                    house = store.load()
                    rd = await r.verify(core, r.load(store, house), key, await _inventory(core), await core.states())
                    store.write(store.readiness_path, rd)
                    record(key, "verified", "Real upcoming event retrieved.")
                except (ValueError, CoreError):
                    rd = r.load(store, store.load())
                    rd["verified"].pop(key, None)
                    rd["revision"] += 1
                    store.write(store.readiness_path, rd)
                    record(key, "incomplete", "Source check failed. Connect/repair it in Home Assistant, then Retry.")
            elif key == "presence":
                house = store.load()
                policy = r.policy_for(r.load(store, house), house, await _inventory(core), await core.states())
                chosen = r.load(store, house)["choices"]["presence"]["sources"]
                valid = bool(chosen) and set(policy.get("presence", [])) == set(chosen)
                record(
                    key,
                    "verified" if valid else "incomplete",
                    "Available source mapped to a confirmed member; no automation created." if valid else "Map a valid source to a household member.",
                )
            elif key == "music" and music_runtime is not None and await music_runtime.verified():
                record(
                    key,
                    "verified",
                    "Audible playback confirmed for the chosen source and speaker. Music shows device progress separately; other paths are untested.",
                )
            else:
                record(key, "incomplete", "Service configuration and an appropriate operation test remain incomplete. Fix now or deliberately skip.")
                if key == "music" and value["draft"]["install_music"]:
                    if "music_installer" not in results:
                        record("music_installer", "started", "Installer requested; provider and playback are separate tasks.")
                        operation = setup.start(user)
                        record("music_installer", "started", "Follow installer progress in Music; this does not verify playback.", operation_id=operation.id)
        for item in value["review"]["screens"]:
            generated = item["generated"]
            key = "display:" + generated["surface"]["id"]
            if results.get(key, {}).get("status") in ("published", "verified", "skipped"):
                continue
            try:
                records = store.read(store.publication_path, {})
                if calendar_access.load(store, store.load())["revision"] != value["review"].get("calendar_revision", 0):
                    raise ValueError("Calendar consent changed. Review the screen with the saved choices before publication.")
                # If an event check failed after review, do not publish stale calendar content.
                if any(results.get(k, {}).get("status") != "verified" for k in ("calendars", "waste") if k in value["draft"]["selected"]):
                    raise ValueError("Repair or skip the failed calendar source and review the screens again.")
                saved = await publish(core, generated, item["expected"], records)
                records[generated["url_path"]] = saved
                store.write(store.publication_path, records)
                record(key, "published", "Published and read back. Open the screen, then confirm it displayed correctly.", url_path=saved["url_path"])
            except (ValueError, CoreError):
                record(key, "incomplete", "Publication could not be verified. Existing dashboard edits are protected; inspect before retrying.")
        if "displays" in value["draft"]["selected"] and not value["review"]["screens"] and results.get("displays", {}).get("status") != "skipped":
            record("displays", "incomplete", "No screens selected for publication. Add a screen or deliberately skip displays.")
        finish(store, value)
    except (ValueError, CoreError, OSError, KeyError, TypeError):
        record("execution", "incomplete", "Execution was interrupted. Saved work is retained. Inspect current state before Retry.")
        value["phase"] = "verification_incomplete"
        write(store, value)


async def _inventory(core):
    from .inventory import collect_inventory

    return await collect_inventory(core)


def finish(store, value):
    pending = [v for v in value["results"].values() if v["status"] not in ("verified", "skipped") and v is not value["results"].get("music_installer")]
    value["phase"] = "verification_incomplete" if pending else "commissioned"
    if value["phase"] == "commissioned":
        value["active"] = False
    return write(store, value)
