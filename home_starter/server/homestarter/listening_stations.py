"""Saved station recipes and honest previews. No protected playback bridge yet."""

import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import catalogue, household_music, stations
from .music_runtime import digest


def sources(providers, access=None):
    return sorted(
        (
            p
            for p in providers
            if household_music.connected(p)
            and access is not None
            and p["id"] in access["sources"]
            and p.get("domain") not in {"spotify", "builtin", *household_music.PROGRESS_DOMAINS}
            and "search" in p.get("features", [])
            and bool(set(p.get("features", [])) & {"library_tracks", "similar_tracks"})
        ),
        key=lambda p: p["id"],
    )


def view(profile, providers, version=None, access=None):
    previews = profile.get("station_previews", {})
    current = next(
        (
            v
            for v in reversed(list(previews.values()))
            if v["expires"] >= time.time() and access is not None and v.get("catalogue_access") == access["signature"]
        ),
        None,
    )
    return {
        "recipes": [{"id": key, **row["recipe"]} for key, row in profile.get("station_recipes", {}).items()],
        "can_preview": bool(sources(providers, access)) and version == "2.10.7",
        "issue": "Preview only: station playback is not connected to protected account routing.",
        "coverage": "Assigned, supported configured sources only; household-wide catalogue coverage is not verified.",
        "notice": profile.get("station_notice"),
        "preview": {k: current[k] for k in ("id", "station", "state", "items", "coverage", "partial_sources")} if current else None,
    }


async def action(listening, endpoint, connection, profile, body, child, *, person=None):
    operation = body["action"]
    if child:
        raise PermissionError("A parent configures and previews station recipes. Your permitted listening choices stay available.")
    recipes = profile.setdefault("station_recipes", {})
    identifier = body.get("station")
    if operation == "station_reset":
        settings = body.get("settings")
        if (
            identifier not in recipes
            or not isinstance(settings, dict)
            or set(settings) != {"scope"}
            or settings["scope"] not in {"session", "station", "profile"}
        ):
            raise ValueError("Choose this profile's station and the feedback scope to reset.")
        scope = settings["scope"]
        preview = profile.get("station_previews", {}).get(body.get("preview"))
        if scope == "session" and (not preview or preview["station"] != identifier or preview["expires"] < time.time()):
            raise ValueError("Choose a current preview session to reset its feedback.")
        key = "profile" if scope == "profile" else "station:" + identifier if scope == "station" else "session:" + preview["id"]
        profile.get("station_feedback", {}).pop(key, None)
        profile["station_notice"] = "Selected preview feedback scope reset. Repeat limits and content restrictions were kept."
        return
    if operation == "station_save":
        spec = stations.recipe(body.get("settings"))
        if identifier is not None and identifier not in recipes:
            raise ValueError("Choose one of this profile's saved stations.")
        if identifier is None and len(recipes) >= 24:
            raise ValueError("This profile has 24 saved stations. Edit an existing recipe.")
        identifier = identifier or secrets.token_hex(12)
        previous = recipes.get(identifier, {})
        recipes[identifier] = {"recipe": spec, "runs": previous.get("runs", 0)}
        for run, preview in profile.get("station_previews", {}).items():
            if preview["station"] == identifier:
                preview["expires"] = 0
                profile.get("station_feedback", {}).pop("session:" + run, None)
        return
    if operation == "station_feedback":
        preview = profile.get("station_previews", {}).get(body.get("preview"))
        if not preview or preview["expires"] < time.time() or preview["station"] not in recipes:
            raise ValueError("Generate a fresh station preview before tuning it.")
        current_providers = (await listening.runtime.snapshot()).get("providers", [])
        current_access = await catalogue.policy(listening.runtime, endpoint, connection, listening.store.load(), person, current_providers)
        if preview.get("catalogue_access") != current_access["signature"]:
            raise PermissionError("Catalogue source assignments changed. Generate a fresh preview.")
        candidate = next((r for r in preview["items"] if r["entry"] == body.get("entry")), None)
        if not candidate:
            raise ValueError("Choose a track from this profile's preview.")
        settings = body.get("settings")
        if not isinstance(settings, dict) or set(settings) != {"scope"}:
            raise ValueError("Choose where this feedback applies.")
        private = preview["identities"][candidate["entry"]]
        stations.steer(profile, preview["station"], preview["id"], private, body.get("value"), settings["scope"])
        profile["station_notice"] = (
            "Preview feedback saved. Regenerate this preview or start a new preview session to apply the selected scope; repeat limits stay enforced."
        )
        return
    if operation not in {"station_preview", "station_refine"} or identifier not in recipes:
        raise ValueError("Choose one of this profile's saved stations.")
    providers = (await listening.runtime.snapshot()).get("providers", [])
    house = listening.store.load()
    access = await catalogue.policy(listening.runtime, endpoint, connection, house, person, providers)
    eligible = sources(providers, access)
    if not eligible or not isinstance(endpoint, dict) or endpoint.get("version") != "2.10.7":
        raise ValueError(
            "No supported station catalogue preview is available. Spotify needs reviewed account-pinned station support; no personal-library fallback was used."
        )
    profile.pop("station_notice", None)
    context = {}
    try:
        config = await listening.core.config()
        date = datetime.now(ZoneInfo(config["time_zone"]))
        context = {"hour": date.hour, "weekday": date.weekday()}
    except Exception:
        context = {}  # Unknown context contributes no fabricated ranking signal.

    partial = [False]

    async def search(query, limit):
        result = await catalogue.search(listening.runtime, endpoint, connection, query, eligible, access, kinds={"track"}, limit=limit, tracks=True)
        partial[0] = partial[0] or result["incomplete"]
        if result["sources"] and all(s["state"] != "ready" for s in result["sources"]):
            raise ValueError("Catalogue sources unavailable")
        return result["items"]

    now = time.time()
    history = profile.get("station_history", [])
    history = [r for i, r in enumerate(history) if now - r["at"] < 30 * 86400 or i >= len(history) - 50]
    if len(history) > 4995:
        raise ValueError("Station proposal history is full. Review it before generating more; repeat restrictions were preserved.")
    saved = recipes[identifier]
    previous = profile.get("station_previews", {}).get(body.get("preview")) if operation == "station_refine" else None
    if operation == "station_refine" and (not previous or previous["station"] != identifier or previous["expires"] < now):
        raise ValueError("Generate a fresh station preview before refining its session.")
    run = previous["id"] if previous else secrets.token_hex(12)
    result = await stations.plan(
        saved["recipe"],
        {"providers": [p["id"] for p in eligible], "provider_domains": {p["id"]: p["domain"] for p in eligible}, "coverage": "unverified", "search": search},
        history,
        stations.feedback_state(profile, identifier, run),
        context,
        saved["runs"] + 1,
        now,
    )
    preview = {
        "id": run,
        "station": identifier,
        "state": result["state"],
        "expires": now + 600,
        "coverage": "Assigned configured sources; search limits and outages may omit matches. Not verified household-wide discovery.",
        "partial_sources": result["partial_sources"] or partial[0],
        "items": [],
        "identities": {},
        "catalogue_access": access["signature"],
        "native_user": access["user_id"],
    }
    for selected in result["items"]:
        entry = digest([run, selected["key"]])[:24]
        name = selected["track"].get("name")
        preview["items"].append({"entry": entry, "title": name[:240] if isinstance(name, str) and "://" not in name else "Catalogue track"})
        preview["identities"][entry] = {k: selected[k] for k in ("key", "artists", "provider", "item_id")}
        history.append({"key": selected["key"], "artists": selected["artists"], "at": now, "kind": "proposed"})
    if result["items"]:
        saved["runs"] += 1
        profile["station_history"] = history
    previews = profile.setdefault("station_previews", {})
    previews.pop(run, None)
    previews[run] = preview
    while len(previews) > 4:
        expired = next(iter(previews))
        previews.pop(expired)
        profile.get("station_feedback", {}).pop("session:" + expired, None)
