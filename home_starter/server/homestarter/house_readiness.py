"""Read existing capability evidence; never turn discovery into a functional test."""

from datetime import UTC, datetime, timedelta

from . import readiness


def report(inventory, people, checks):
    found = readiness.discover(inventory, [])
    entries = {e["domain"] for e in inventory["integrations"] if e.get("source") != "ignore"}
    decisions = checks.get("readiness")
    readable = all(inventory["sources"].get(k, {}).get("status") == "ok" for k in ("entities", "states", "integrations"))
    rows = []
    for key, (title, _, route) in readiness.CAPABILITIES.items():
        sources = found[key]
        if key == "waste":
            sources = [s for s in sources if s.get("likely")]
        choice = (decisions or {}).get("choices", {}).get(key, {})
        available = sum(s["available"] for s in sources)
        state, confidence = "not_configured", "Unknown"
        detail = "No sources or setup choices found in HA/Home Starter. External configuration has not been tested."
        if choice.get("intent") in {"later", "not_wanted"}:
            state, confidence = "not_applicable", "Confirmed"
            detail = "Deferred by your saved choice." if choice["intent"] == "later" else "Not wanted by your saved choice."
        elif sources:
            state = "partial" if available else "problem"
            confidence = "Confirmed"
            detail = f"{available} of {len(sources)} sources report a usable state. Functional operation is unverified."
            if not available and not any(
                e.get("state") == "unavailable" for e in readiness.entities(inventory) if e["entity_id"] in {s["id"] for s in sources}
            ):
                state, confidence = "unknown", "Unknown"
        elif choice.get("intent") == "wanted":
            state, detail = "needs_setup", "Wanted, but no usable source has been selected and verified."
        if not readable and choice.get("intent") not in {"later", "not_wanted"}:
            state, confidence, detail = "unknown", "Unknown", "HA source discovery is incomplete. Missing data does not establish missing configuration."
        if key == "music" and choice.get("intent") not in {"later", "not_wanted"}:
            music = checks.get("music")
            if music is None:
                state, detail = "unknown", "The Music Assistant connection could not be inspected. Existing settings and playback proof are preserved."
                confidence = "Unknown"
            else:
                proof = music.get("proof") or {}
                try:
                    age = datetime.now(UTC) - datetime.fromisoformat(proof["at"])
                    valid = timedelta(0) <= age <= timedelta(days=1) and proof.get("provider_id") and proof.get("player_id")
                except (KeyError, TypeError, ValueError):
                    valid = False
                if music.get("connected") and valid:
                    state, confidence = "ready", "Confirmed"
                    detail = "Audible playback verified for one source and speaker within 24 hours; other paths remain untested."
                elif music.get("connected"):
                    state, detail = "needs_setup", "MA is connected; no current source-and-speaker playback proof. Run the existing playback check."
                elif sources or "music_assistant" in entries:
                    state, detail = "needs_setup", "Music is discovered; connect and verify a chosen source and speaker. Installation is not playback proof."
        elif key in {"calendars", "waste"} and readable and choice.get("intent") not in {"later", "not_wanted"}:
            selected = set(choice.get("sources", []))
            present = {s["id"] for s in sources if s["available"]}
            if selected and not selected <= present:
                state, detail = "problem", "A selected calendar source is missing or not reporting. Review its native integration."
            elif selected and decisions and readiness.proof_valid(decisions, key, inventory):
                state, confidence = "ready", "Confirmed"
                detail = (
                    "The selected source returned a credible upcoming event in its current 24-hour verification window. Event contents are not retained here."
                )
            elif sources:
                state, detail = "needs_setup", "Calendar sources exist; select the household source and verify a real event in the existing readiness flow."
                if key == "waste":
                    confidence = "Likely"
                    detail = "A calendar name or integration suggests collection dates; confirm its purpose and verify a real collection event."
            if decisions is None:
                state, confidence, detail = "unknown", "Unknown", "Saved calendar choices could not be read. Existing choices are preserved."
        elif key == "presence" and readable and choice.get("intent") not in {"later", "not_wanted"}:
            members = [p for p in people if p["role"] in {"adult", "child"}]
            untracked = sum(p["presence_plan"] == "untracked" for p in members)
            reporting = sum(p["usable_tracker"] and p["presence_plan"] != "untracked" for p in members)
            state = "partial" if members else "needs_setup"
            confidence = "Confirmed" if members else "Unknown"
            detail = (
                f"{reporting} member trackers reporting; {untracked} members intentionally untracked. "
                "Arrival/departure accuracy is unverified; missing tracking never means away."
            )
            route = "#this-house-people"
        elif key == "communications" and readable and entries & readiness.SIP and choice.get("intent") not in {"later", "not_wanted"}:
            state, detail = "partial", "A calling integration exists. Registration, internal calls, gate calls and intercom audio remain unverified."
        elif key == "voice" and readable and entries & {"google_assistant", "alexa"} and choice.get("intent") not in {"later", "not_wanted"}:
            state, detail = "partial", "A voice integration exists. Microphone, response and household controls remain unverified."
        if key == "cameras" and sources:
            detail += " Camera images, live streams, doorbell events and intercom audio have not been checked here."
        if key == "climate" and sources:
            detail += " Temperature/mode reporting does not prove that the equipment responds to commands."
        if key in {"calendars", "waste"}:
            route = "#home-readiness"
        if key == "waste" and (bins := checks.get("waste")) and bins["configured"]:
            state = "ready" if bins["status"] == "current" and bins["entities_ready"] else "partial" if bins["status"] == "last_known_valid" else "problem"
            confidence = "Verified" if bins["status"] == "current" else "Last verified"
            detail = bins["message"] + (" " + bins["entity_issue"] if bins["entity_issue"] else "")
            route = "#waste-collection"
        rows.append({"id": key, "title": title, "state": state, "confidence": confidence, "detail": detail, "route": route})
    screens = checks.get("screens")
    if screens is None:
        state, detail = "unknown", "Saved dashboard targets could not be read. Existing publications are preserved."
    elif not screens:
        state, detail = "not_configured", "No Home Starter dashboard targets configured. Existing native dashboards are unaffected."
    else:
        matched = sum(s["status"] == "published" for s in screens)
        statuses = {s["status"] for s in screens}
        state = "ready" if matched == len(screens) else "problem" if "missing" in statuses else "unknown" if "unavailable" in statuses else "partial"
        detail = (
            f"{matched} of {len(screens)} saved dashboard configurations match readback. "
            "Physical display wake, visibility and controls are unverified by publication."
        )
    rows.append(
        {
            "id": "dashboards",
            "title": "Saved dashboards",
            "state": state,
            "confidence": "Confirmed" if screens is not None and state != "unknown" else "Unknown",
            "detail": detail,
            "route": "#house-status",
        }
    )
    fixed = [s for s in screens or [] if s.get("commissioning", {}).get("required", s.get("profile") != "phone")]
    commissioned = sum(s.get("commissioning", {}).get("stage") == "commissioned" for s in fixed)
    rows.append(
        {
            "id": "display_commissioning",
            "title": "Physical household screens",
            "state": "unknown" if screens is None else "not_configured" if not fixed else "ready" if commissioned == len(fixed) else "partial",
            "confidence": "Unknown" if screens is None else "Scoped checks",
            "detail": (
                f"{commissioned} of {len(fixed)} fixed/shared screens commissioned. "
                "Dashboard publication alone does not verify identity, physical use or restart persistence. Screen power is separate."
            ),
            "route": "#screen-identity",
        }
    )
    return rows
