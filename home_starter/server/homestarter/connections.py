"""Resumable household connection checks, shared by onboarding and maintenance."""

from . import calendar_access, google_setup, household_music, household_services, readiness
from .core import CoreError
from .inventory import collect_inventory
from .music_runtime import MusicRuntimeError
from .supervisor import SupervisorError


async def inspect(state, *, prepare=False):
    house = state.household.load()
    states = await state.core.states()
    inventory = await collect_inventory(state.core)
    calendars = calendar_access.discover(state.household, house, states)
    registry = {e["entity_id"]: e for e in readiness.entities(inventory)}
    entries = {e["entry_id"]: e for e in inventory["integrations"]}
    for row in calendars["rows"]:
        entity = registry.get(row["id"], {})
        entry = entries.get(entity.get("config_entry_id"), {})
        row["source"] = {"integration": entry.get("domain") or entity.get("platform") or "Home Assistant", "account": entry.get("title") or ""}
    google = await google_setup.inspect(state.core, inventory, calendars, verify=prepare)
    try:
        music = await state.music_runtime.household(prepare=prepare)
        if prepare:
            await reconcile_mappings(state)
        if hasattr(state, "listening"):
            try:
                endpoint, connection = await state.music_runtime.endpoint(), state.music_runtime.connection()
                policy = (
                    await state.music_runtime.control(endpoint, connection, "homestarter/media_prepare")
                    if prepare
                    else await state.music_runtime.command(endpoint, connection, "homestarter/media_status")
                )
                catalogue = await state.listening.media.sync() if prepare else state.listening.media.view()
                surface_issues = []
                if prepare:
                    from . import media_surfaces

                    surface_issues = await media_surfaces.refresh(state.core, state.household)
                music["media"] = {
                    "state": "connected"
                    if all(r["state"] == "connected" for r in policy["policy"]) and catalogue["ready"] == catalogue["selected"] and catalogue["ready"]
                    else "connected_but_incomplete",
                    "detail": f"{catalogue['ready']} household radio and ambient stations ready · provider-only continuation",
                }
                if surface_issues:
                    music["media"] = {"state": "connected_but_incomplete", "detail": "Media controls need review on an edited household screen"}
            except (MusicRuntimeError, ValueError, TypeError, KeyError, OSError):
                music["media"] = {"state": "connected_but_incomplete", "detail": "Prepare household media and check playback policy"}
    except (MusicRuntimeError, SupervisorError, CoreError, ValueError, TypeError, KeyError):
        music = {
            "state": "failed",
            "summary": "Music Assistant administration needs attention. Reconnect with user-management permission, then retry.",
            "spotify": [],
        }
    airtouch = [d for d in inventory["devices"] if any("airtouch" in e.get("domain", "") for e in d.get("integrations", []))]
    climate_ids = {e["entity_id"] for d in airtouch for e in d["entities"] if e["entity_id"].startswith("climate.")}
    climate = [s for s in states if s["entity_id"] in climate_ids]
    climate_ready = bool(climate) and all(s["state"] not in {"unknown", "unavailable"} for s in climate)
    history = state.household.read(state.household.observation_path, {})
    if history.get("epoch") != house["epoch"]:
        history = {}
    drift = any(
        (old := history.get("known", {}).get("device:" + d["id"]))
        and old.get("connection") != d.get("connection_fingerprint")
        or history.get("pending", {}).get("device:" + d["id"], {}).get("category") == "connection"
        for d in airtouch
    )
    updates = sum(s["entity_id"].startswith("update.") and s["state"] == "on" for s in states)
    checks = [
        {"name": "Home Assistant", "state": "needs_review" if updates else "connected", "detail": f"{updates} pending updates" if updates else "Reachable"},
        {"name": "Music Assistant", "state": music["state"], "detail": music["summary"]},
        {"name": "Music account protection", **music.get("allocator", {"state": "not_detected", "detail": "Check household music account protection"})},
        {"name": "Household media", **music.get("media", {"state": "not_detected", "detail": "Prepare music discovery, radio and ambient sources"})},
        *[
            {
                "name": "Spotify — " + row["name"] + " audio",
                "state": row["state"],
                "detail": "Audio read successfully"
                if row["state"] == "connected"
                else "Spotify rejected the audio key. Complete the existing account's Spotify Soloist consent and pairing."
                if row.get("issue") == "audio_key_unavailable"
                else "Connected, but audio could not start. Check the existing account's playback setup and retry.",
            }
            for row in music.get("playback_checks", [])
        ],
        *[
            {
                "name": "Spotify — " + r["name"],
                "state": r["state"],
                "detail": "Connect Spotify — " + r["name"]
                if r["state"] in {"ready_for_authentication", "reauth_required"}
                else "Connected"
                if r["state"] == "connected"
                else "Waiting for Music Assistant to load this account"
                if r["state"] == "preparing"
                else "Check the existing music account",
            }
            for r in music["spotify"]
        ],
        {"name": "Google Calendar", "state": google["state"], "detail": google["detail"]},
        {"name": "Calendars", "state": calendars["state"], "detail": "Review calendars" if calendars["counts"]["review"] else "Calendar choices saved"},
        {
            "name": "AirTouch",
            "state": "needs_review" if drift else "connected" if climate_ready else "connected_but_incomplete" if airtouch else "not_detected",
            "detail": "AirTouch endpoint changed. Check its native integration before relying on climate controls."
            if drift
            else "AirTouch zones reachable"
            if climate_ready
            else "Connect AirTouch or repair its native integration.",
        },
        {"name": "Household people", "state": "connected" if house["people"] else "not_detected", "detail": f"{len(house['people'])} configured"},
        {"name": "Household screens", "state": "connected" if house["surfaces"] else "not_detected", "detail": f"{len(house['surfaces'])} configured"},
    ]
    return {"epoch": house["epoch"], "google": google, "calendars": calendars, "music": music, "checks": checks}


async def reconcile_mappings(state):
    """Bind uniquely named existing providers; missing identities remain pending."""
    house = state.household.load()
    config = household_services.load(state.household, house)
    providers = household_music.providers_by_identity((await state.music_runtime.snapshot())["providers"])
    if not providers and not config["media_identities"]:
        return
    people = {p["name"].casefold(): p["id"] for p in house["people"]}
    for name in household_music.IDENTITIES:
        personal = name in {"Grant", "Renae"}
        if personal and name.casefold() not in people:
            continue
        matches = [r for r in config["media_identities"] if household_music.normalized(r["name"]) == household_music.normalized(name)]
        if len(matches) > 1:
            raise ValueError("Review duplicate household account mappings.")
        if not matches:
            row = {
                "id": "spotify_" + household_music.normalized(name),
                "name": name,
                "service": "spotify",
                "scope": "personal" if personal else "shared",
                "people": [people[name.casefold()]] if personal else [],
                "provider_id": None,
            }
            config["media_identities"].append(row)
        else:
            row = matches[0]
        if not row["provider_id"] and name in providers:
            row["provider_id"] = providers[name]["id"]
    household_services.save(state.household, house, config)


async def verify_calendars(state):
    """A successful native read, including an empty list, proves a usable calendar."""
    house = state.household.load()
    states = await state.core.states()
    access = calendar_access.load(state.household, house)
    selected = [s for s in states if access["calendars"].get(s["entity_id"]) in {"show", "context"}]
    wanted = [s["entity_id"] for s in selected]
    rd = readiness.load(state.household, house)
    if not wanted:
        old = rd["choices"].get("calendars")
        if old and access["calendars"] and not any(v == "review" for v in access["calendars"].values()):
            updated = {**old, "intent": "not_wanted", "sources": []}
            if old != updated:
                rd["choices"]["calendars"] = updated
                rd["verified"].pop("calendars", None)
                rd["revision"] += 1
                state.household.write(state.household.readiness_path, rd)
        return False
    # Classification is the user's calendar decision. Complete the old readiness
    # wiring automatically; never make them select the same sources twice.
    previous = rd["choices"].get("calendars", {})
    choice = {
        "intent": "wanted",
        "sources": wanted,
        "screens": previous.get("screens") or [s["id"] for s in house["surfaces"]],
        "answers": previous.get("answers", {}),
        "permissions": previous.get("permissions", {}),
    }
    unchanged = previous == choice
    rd["choices"]["calendars"] = choice
    inventory = await collect_inventory(state.core)
    if unchanged and all(s["state"] not in {"unknown", "unavailable"} for s in selected) and readiness.proof_valid(rd, "calendars", inventory):
        return True
    from datetime import UTC, datetime, timedelta
    from urllib.parse import urlencode

    now = datetime.now(UTC)
    query = urlencode({"start": now.isoformat(), "end": (now + timedelta(days=30)).isoformat()})
    rd["verified"].pop("calendars", None)
    rd["revision"] += 1
    state.household.write(state.household.readiness_path, rd)
    if any(s["state"] in {"unknown", "unavailable"} for s in selected):
        raise ValueError("A selected calendar is unavailable. Repair its native connection and retry.")
    for source in wanted:
        raw = await state.core.rest_get("/calendars/" + source + "?" + query)
        if not isinstance(raw, list):
            raise ValueError("A selected calendar could not be read. Retry after repairing the connection.")
    rd["verified"]["calendars"] = {"at": now.isoformat(), "signature": readiness.selection_signature(choice, inventory)}
    state.household.write(state.household.readiness_path, rd)
    return True


async def resume_commissioning(state, music=None):
    """Recheck completed consent/auth work without replaying installations or publications."""
    from . import commissioning

    value = commissioning.load(state.household)
    if value["phase"] != "verification_incomplete" or value["results"].get("household", {}).get("status") != "verified":
        return
    changed = False
    if value["results"].get("calendars", {}).get("status") == "incomplete":
        house = state.household.load()
        calendars = calendar_access.discover(state.household, house, await state.core.states())
        if calendars["rows"] and not calendars["counts"]["review"]:
            if not calendars["counts"]["show"] and not calendars["counts"]["context"]:
                value["results"]["calendars"] = {"status": "skipped", "detail": "All discovered calendars explicitly ignored."}
                changed = True
            elif await verify_calendars(state):
                value["results"]["calendars"] = {"status": "verified", "detail": "Calendar choices saved and native calendar feeds read successfully."}
                changed = True
    if value["results"].get("music", {}).get("status") == "incomplete" and (music or {}).get("state") == "connected" and await state.music_runtime.verified():
        value["results"]["music"] = {
            "status": "verified",
            "detail": "Chosen source and speaker playback verified. Pending optional identities do not block this path.",
        }
        changed = True
    if changed:
        commissioning.finish(state.household, value)


async def continue_setup(state, music=None):
    from . import context_runtime

    if state.commissioning_task and not state.commissioning_task.done():
        return {"state": "preparing", "detail": "Calendar choices saved. Applying them after the current setup operation finishes."}
    verification = {"state": "connected", "detail": "Calendar choices saved; selected calendars checked."}
    try:
        checked = await verify_calendars(state)
        if not checked:
            discovery = calendar_access.discover(state.household, state.household.load(), await state.core.states())
            verification = (
                {"state": "needs_review", "detail": "Review the discovered calendars before enabling shared calendar content."}
                if discovery["counts"]["review"]
                else {"state": "connected", "detail": "Calendar choices saved; no calendar feeds selected."}
            )
    except (CoreError, ValueError):
        verification = {"state": "connected_but_incomplete", "detail": "Calendar choices saved. A source could not be read; connection checks will retry."}
    house = state.household.load()
    revision = (house["epoch"], calendar_access.load(state.household, house)["revision"], readiness.load(state.household, house)["revision"])
    if revision != getattr(state, "calendar_revision_applied", None):
        screens = await calendar_access.refresh_publications(state.core, state.household, house, await collect_inventory(state.core), await state.core.states())
        if screens:
            verification = {"state": "needs_review", "detail": "Calendar choices saved. Some screens need attention.", "screens": screens}
        else:
            await context_runtime.update(state.core, state.household, state.wall_sessions)
            state.calendar_revision_applied = revision
    await resume_commissioning(state, music)
    return verification


async def calendar_preview(core, source):
    """Ephemeral admin response. Never persist descriptions, attendees or feed URLs."""
    from datetime import UTC, datetime, timedelta
    from urllib.parse import urlencode

    if not calendar_access.valid_id(source):
        raise ValueError("Choose a discovered calendar.")
    states = await core.states()
    if source not in {s["entity_id"] for s in states if calendar_access.valid_id(s.get("entity_id"))}:
        raise ValueError("This calendar is no longer discovered. Refresh the choices.")
    now = datetime.now(UTC)
    query = urlencode({"start": now.isoformat(), "end": (now + timedelta(days=30)).isoformat()})
    raw = await core.rest_get("/calendars/" + source + "?" + query)
    if not isinstance(raw, list):
        raise ValueError("Calendar preview is unavailable. Your saved choice is unchanged.")
    events = [{"title": str(e.get("summary") or "Private event")[:180], "start": e.get("start"), "end": e.get("end")} for e in raw[:5] if isinstance(e, dict)]
    return {
        "events": events,
        "detail": "Next 30 days · preview only; event contents are not saved"
        if events
        else "No upcoming events in the next 30 days. Check this calendar in HA if you need older events to identify it.",
    }
