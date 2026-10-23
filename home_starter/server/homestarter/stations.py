"""Deterministic station recipes and bounded catalogue planning; no playback engine."""

import asyncio
import re

from .music_runtime import digest, number


def recipe(value):
    defaults = {"name": "", "seeds": [], "genres": [], "era": None, "exclude_explicit": False, "track_gap_days": 1, "artist_gap": 3, "discovery": 50}
    if not isinstance(value, dict) or set(value) - defaults.keys():
        raise ValueError("Choose supported station recipe fields.")
    result = {**defaults, **value}
    if not isinstance(result["name"], str) or not 1 <= len(result["name"].strip()) <= 80 or any(ord(c) < 32 for c in result["name"]):
        raise ValueError("Give this station a short name.")
    result["name"] = result["name"].strip()
    for key in ("seeds", "genres"):
        if (
            not isinstance(result[key], list)
            or len(result[key]) > 8
            or any(not isinstance(s, str) or not re.fullmatch(r"[\w '&,.\-]{1,80}", s) for s in result[key])
        ):
            raise ValueError("Use up to eight plain-text station seeds or genres.")
        result[key] = list(dict.fromkeys(s.strip() for s in result[key] if s.strip()))
    if len(result["seeds"]) + len(result["genres"]) > 8:
        raise ValueError("Use up to eight station seeds and genres in total.")
    if not result["seeds"] and not result["genres"]:
        raise ValueError("Add an artist, song, genre or text seed. No personal-library fallback is used.")
    if result["era"] is not None and (type(result["era"]) is not int or result["era"] not in range(1960, 2030, 10)):
        raise ValueError("Choose a supported decade or any era.")
    if type(result["exclude_explicit"]) is not bool:
        raise ValueError("Choose an explicit-content preference.")
    for key, high in (("track_gap_days", 30), ("artist_gap", 50), ("discovery", 100)):
        if type(result[key]) is not int or not 0 <= result[key] <= high:
            raise ValueError("Review station repeat and discovery settings.")
    return result


def identity(track, provider):
    matches = [m for m in track.get("provider_mappings") or [] if isinstance(m, dict) and m.get("provider_instance") == provider and m.get("available") is True]
    if track.get("media_type") != "track" or not matches or not track.get("item_id"):
        return None
    key = matches[0].get("item_id") or track["item_id"]
    artists = track.get("artists") or []
    if (
        not isinstance(key, str)
        or not isinstance(artists, list)
        or any(not isinstance(a, dict) for a in artists)
        or not isinstance(track.get("metadata") or {}, dict)
    ):
        return None
    domain = matches[0].get("catalogue_namespace") or matches[0].get("provider_domain") or provider
    artist_ids = [str(domain) + ":" + str(a["item_id"]) for a in artists if isinstance(a, dict) and a.get("item_id")]
    return {"key": str(domain) + ":" + key, "artists": sorted(set(artist_ids)), "provider": provider, "item_id": key}


def tags(track):
    metadata = track.get("metadata") or {}
    genres = metadata.get("genres") or []
    return {str(g).casefold() for g in genres if isinstance(g, str)} if isinstance(genres, list) else set()


def context_score(track, context, explicit=False):
    if explicit:
        return 0
    hour, weekday = context.get("hour"), context.get("weekday")
    if type(hour) is not int or not 0 <= hour < 24:
        return 0
    calm = bool(tags(track) & {"ambient", "sleep", "calm", "relaxing"})
    upbeat = bool(tags(track) & {"upbeat", "pop", "dance"})
    if type(weekday) is int and 0 <= weekday < 5 and 6 <= hour < 10:
        return (15 if upbeat else 0) - (20 if calm else 0)
    if hour >= 21 or hour < 6:
        return (15 if calm else 0) - (10 if upbeat else 0)
    return 0


def feedback_state(profile, station, session):
    return [
        *profile.get("station_feedback", {}).get("profile", []),
        *profile.get("station_feedback", {}).get("station:" + station, []),
        *profile.get("station_feedback", {}).get("session:" + session, []),
    ]


def steer(profile, station, session, candidate, action, scope):
    if action not in {"more", "less", "never"} or scope not in {"session", "station", "profile"}:
        raise ValueError("Choose More, Less or Never, and where it should apply.")
    key = scope if scope == "profile" else scope + ":" + (station if scope == "station" else session)
    records = profile.setdefault("station_feedback", {}).setdefault(key, [])
    record = next((r for r in records if r["key"] == candidate["key"]), None)
    if record is None:
        if len(records) >= 1000:
            raise ValueError("Station feedback is full. Review it before adding more exclusions.")
        record = {"key": candidate["key"], "artists": candidate["artists"], "weight": 0, "never": False}
        records.append(record)
    if action == "never":
        record["never"] = True
    else:
        record["weight"] = max(-5, min(5, record["weight"] + (1 if action == "more" else -1)))


async def plan(spec, gateway, history, feedback, context, run, now, *, count=5, explicit=None, restricted=False):
    """Gateway must already be authorised/pinned. Spotify routing is not implemented here."""
    spec = recipe(spec)
    provider_ids = gateway.get("providers") or [gateway["provider"]]
    if gateway.get("domain") == "spotify" or "spotify" in gateway.get("provider_domains", {}).values():
        raise ValueError("Spotify station discovery requires a separately reviewed pinned account bridge.")
    if gateway.get("search") is None or gateway.get("coverage") not in {"provider", "local", "unverified"}:
        raise ValueError("This source cannot search a station catalogue.")
    queries = list(dict.fromkeys([*spec["seeds"], *spec["genres"]]))
    candidates, failures = {}, 0
    for query in queries:
        try:
            rows = await asyncio.wait_for(gateway["search"](query, 50), timeout=8)
            if not isinstance(rows, list):
                raise ValueError("Invalid catalogue response")
        except Exception:
            failures += 1
            continue
        for track in rows:
            if not isinstance(track, dict):
                continue
            ident = next((i for provider in provider_ids if (i := identity(track, provider)) is not None), None)
            if not ident or (spec["exclude_explicit"] or restricted) and (track.get("metadata") or {}).get("explicit") is not False:
                continue
            if spec["artist_gap"] and not ident["artists"]:
                continue  # Unknown artist metadata cannot prove repeat-gap eligibility.
            candidates.setdefault(ident["key"], {"track": track, **ident})
    recent = [r for r in history if number(r.get("at")) and now - r["at"] < spec["track_gap_days"] * 86400]
    recent_keys = {r["key"] for r in recent}
    ordered_history = sorted(history, key=lambda r: r.get("at", 0))
    chosen, remaining = [], list(candidates.values())
    while remaining and len(chosen) < count:
        artists_recent = {a for r in (ordered_history + chosen)[-spec["artist_gap"] :] for a in r.get("artists", [])} if spec["artist_gap"] else set()
        eligible = []
        for candidate in remaining:
            key, artists, track = candidate["key"], set(candidate["artists"]), candidate["track"]
            if any(f["key"] == key and f.get("never") for f in feedback):
                continue
            requested = explicit == key
            if not requested and (key in recent_keys or artists & artists_recent):
                continue
            seed_text = " ".join([str(track.get("name") or ""), *(str(a.get("name") or "") for a in track.get("artists", [])), *tags(track)]).casefold()
            seed_score = sum(100 for seed in spec["seeds"] if seed.casefold() in seed_text)
            genre_score = 80 * len(set(g.casefold() for g in spec["genres"]) & tags(track))
            year = track.get("year")
            era_score = 60 if type(year) is int and spec["era"] is not None and spec["era"] <= year < spec["era"] + 10 else 0
            familiar = any(artists & set(r.get("artists", [])) for r in history)
            discovery_score = (100 - spec["discovery"] if familiar else spec["discovery"]) / 10
            tuning = sum(f.get("weight", 0) * (30 if f["key"] == key else 10 if artists & set(f.get("artists", [])) else 0) for f in feedback)
            score = (10000 if requested else 0) + seed_score + genre_score + era_score + discovery_score + tuning + context_score(track, context, requested)
            eligible.append((score, digest([spec, run, key]), candidate))
        if not eligible:
            break
        selected = max(eligible, key=lambda row: (row[0], row[1]))[2]
        chosen.append(selected)
        remaining = [r for r in remaining if r["key"] != selected["key"]]
    return {
        "items": chosen,
        "state": "provider_unavailable" if failures == len(queries) else "exhausted" if not chosen else "partial" if len(chosen) < count else "ready",
        "coverage": gateway["coverage"],
        "partial_sources": bool(failures),
    }
