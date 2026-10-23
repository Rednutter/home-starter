"""Profile-scoped MA catalogue aggregation, without a library or account fallback."""

import asyncio

from .household_music import connected, normalized
from .listening_collections import merge
from .music_runtime import MusicRuntimeError, digest

KINDS = {"track", "album", "artist", "playlist", "radio", "podcast", "podcast_episode", "audiobook"}
GLOBAL_IDS = {"spotify", "qobuz", "deezer", "tidal", "apple_music"}


async def policy(runtime, endpoint, connection, house, person, providers):
    people = [p for p in house["people"] if p["id"] == person] if person else [{"name": "House"}]
    message = "This profile's catalogue source assignments need review. No unrestricted library fallback was used."
    if len(people) != 1 or not connection:
        raise MusicRuntimeError(message)
    try:
        users = await runtime.command(endpoint, connection, "auth/users")
    except (MusicRuntimeError, ValueError, KeyError, TypeError):
        raise MusicRuntimeError(message) from None
    if not isinstance(users, list):
        raise MusicRuntimeError(message)
    matches = [
        u
        for u in users
        if isinstance(u, dict)
        and (normalized(u.get("display_name")) == normalized(people[0]["name"]) or normalized(u.get("username")) == normalized(people[0]["name"]))
    ]
    if len(matches) != 1 or matches[0].get("enabled") is False or not isinstance(matches[0].get("user_id"), str) or not matches[0]["user_id"]:
        raise MusicRuntimeError(message)
    native = matches[0]
    filters = native.get("provider_filter")
    known = {p["id"]: p for p in providers}
    if not isinstance(filters, list) or not filters or any(not isinstance(f, str) for f in filters) or not set(filters) <= known.keys():
        raise MusicRuntimeError(message)
    scope = "person:" + person if person else "house"
    signature = digest(
        [
            house["epoch"],
            scope,
            native["user_id"],
            [(k, known[k].get("domain")) for k in sorted(set(filters))],
            *[connection[k] for k in ("server_id", "app", "generation")],
        ]
    )
    return {"user_id": native["user_id"], "sources": sorted(set(filters)), "scope": scope, "signature": signature}


def eligible(providers, access, *, tracks=False):
    return sorted(
        (
            p
            for p in providers
            if p["id"] in access["sources"]
            and connected(p)
            and p.get("domain") not in {"spotify", "library"}
            and p["id"] != "library"
            and "search" in p.get("features", [])
            and (not tracks or bool(set(p.get("features", [])) & {"library_tracks", "similar_tracks"}))
        ),
        key=lambda p: p["id"],
    )


def sanitise(value, provider):
    if not isinstance(value, dict) or value.get("media_type") not in KINDS:
        return None
    mappings = value.get("provider_mappings") or []
    selected = [
        m
        for m in mappings
        if isinstance(m, dict)
        and m.get("provider_instance") == provider["id"]
        and m.get("available", True)
        and isinstance(m.get("item_id"), str)
        and m["item_id"]
    ]
    keys = {m["item_id"] for m in selected}
    if value.get("provider") == provider["id"] and isinstance(value.get("item_id"), str) and value["item_id"]:
        keys.add(value["item_id"])
    if len(keys) != 1:
        return None
    key = keys.pop()
    kind = value["media_type"]
    name = value.get("name")
    return {
        **value,
        "name": name[:240] if isinstance(name, str) and "://" not in name else "Catalogue item",
        "provider": provider["id"],
        "item_id": key,
        "uri": provider["id"] + "://" + kind + "/" + key,
        "provider_mappings": [
            {
                "provider_instance": provider["id"],
                "provider_domain": provider.get("domain") or provider["id"],
                "catalogue_namespace": provider["domain"] if provider.get("domain") in GLOBAL_IDS else provider["id"],
                "item_id": key,
                "available": True,
            }
        ],
    }


async def search(runtime, endpoint, connection, query, providers, access, *, kinds=None, timeout=5, limit=50, tracks=False):
    if not isinstance(query, str) or not query.strip() or len(query) > 100:
        raise ValueError("Use a search of 1-100 characters.")
    if not isinstance(endpoint, dict) or endpoint.get("version") != "2.10.7":
        raise MusicRuntimeError("Catalogue aggregation needs a reviewed Music Assistant version.")
    targets = eligible(providers, access, tracks=tracks)
    semaphore = asyncio.Semaphore(4)

    async def one(provider):
        async with semaphore:
            try:
                raw = await asyncio.wait_for(
                    runtime.command(
                        endpoint,
                        connection,
                        "music/search",
                        search_query=query,
                        providers=[provider["id"]],
                        media_types=sorted(kinds or KINDS),
                        limit=limit,
                        user={"provider": "builtin", "user_id": access["user_id"], "required": True},
                    ),
                    timeout,
                )
                if not isinstance(raw, dict):
                    raise ValueError("Unsupported source response")
                rows = [r for values in raw.values() if isinstance(values, list) for r in values]
                values = [v for row in rows if (v := sanitise(row, provider)) is not None and (not kinds or v["media_type"] in kinds)]
                return values, {
                    "domain": provider.get("domain"),
                    "state": "ready",
                    "may_have_more": any(isinstance(v, list) and len(v) >= limit for v in raw.values()),
                }
            except TimeoutError:
                return [], {"domain": provider.get("domain"), "state": "timed_out"}
            except Exception:
                return [], {"domain": provider.get("domain"), "state": "unavailable"}

    results = await asyncio.gather(*(one(p) for p in targets))
    values = [v for rows, _ in results for v in rows]
    combined = []
    for kind in sorted(kinds or KINDS):
        for row in merge(values, kind):
            row.pop("household_collection", None)
            row["catalogue_access"] = access["signature"]
            combined.append(row)
    states = [status for _, status in results]
    queried = {p["id"] for p in targets}
    for p in providers:
        if p["id"] in access["sources"] and p["id"] not in queried:
            states.append(
                {
                    "domain": p.get("domain"),
                    "state": "protected_bridge_unavailable" if p.get("domain") == "spotify" else "unavailable" if not connected(p) else "unsupported",
                }
            )
    blocked = any(p["id"] in access["sources"] and p.get("domain") == "spotify" for p in providers)
    return {
        "items": combined,
        "access": access,
        "sources": states,
        "incomplete": blocked or any(s["state"] != "ready" or s.get("may_have_more") for s in states),
        "issue": "Spotify discovery is not available yet. Browse saved Spotify collections or search other connected sources." if blocked else None,
        "coverage": "Configured, assigned catalogue searches only; source limits and unavailable sources can omit matches.",
    }


def require_record(record, access):
    if record.get("catalogue_access") != access["signature"]:
        raise PermissionError("This catalogue selection belongs to a different or changed profile. Search again.")
