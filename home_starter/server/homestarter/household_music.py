"""Household MA users and Spotify identity policy; provider login stays in MA."""

import re
import secrets

NAMES = ("Grant", "Renae", "Edie", "Maddie", "Flynn", "House")
IDENTITIES = ("Grant", "Renae", "House", "House #2")
OVERFLOW = ("House", "House #2", "Grant")
PROGRESS_DOMAINS = {"audiobookshelf", "audible", "storytel"}


def normalized(value):
    return re.sub(r"[^a-z0-9]", "", str(value).casefold().removeprefix("spotify"))


def providers_by_identity(providers):
    result = {}
    for name in IDENTITIES:
        matches = [p for p in providers if p.get("domain") == "spotify" and normalized(p.get("household_identity") or p.get("name")) == normalized(name)]
        if len(matches) > 1:
            raise ValueError("Duplicate Spotify account labels need administrator review. Existing providers are preserved.")
        if matches:
            result[name] = matches[0]
    return result


def connected(provider):
    return provider.get("available") is True and provider.get("enabled", True) is True


def source_access(name, providers):
    identities = providers_by_identity(providers)
    personal = name in {"Grant", "Renae"}
    names = [name] if personal else ["House", "House #2"]
    allowed = {identities[n]["id"] for n in names if n in identities}
    allowed.update(p["id"] for p in providers if p.get("domain") not in {"spotify", *PROGRESS_DOMAINS} and p.get("enabled", True))
    # MA treats [] as unrestricted, and prunes fabricated IDs on restart.
    # Never represent deny-all using either of those shortcuts.
    if not allowed:
        raise ValueError("Connect a shared non-personal source before provisioning a user with no authenticated personal source.")
    return sorted(allowed)


def collection_access(providers):
    """Native catalogue access after explicit sharing consent, never allocation."""
    allowed = {p["id"] for p in providers_by_identity(providers).values() if connected(p)}
    allowed.update(p["id"] for p in providers if p.get("domain") not in {"spotify", *PROGRESS_DOMAINS} and p.get("enabled", True))
    if not allowed:
        raise ValueError("Connect a household source before sharing native collections.")
    return sorted(allowed)


async def reconcile(command, providers, names=NAMES, *, share_collections=False):
    """Run under the runtime lock. Read back after every uncertain write on retry."""
    users = await command("auth/users")
    if not isinstance(users, list):
        raise ValueError("Music Assistant user administration is unavailable.")
    for name in names:
        matches = [u for u in users if normalized(u.get("display_name")) == normalized(name) or normalized(u.get("username")) == normalized(name)]
        if len(matches) > 1:
            raise ValueError("Duplicate household user names need administrator review. No users were removed.")
        access = collection_access(providers) if share_collections else source_access(name, providers)
        if matches:
            user = matches[0]
            if user.get("enabled") is False:
                raise ValueError("A household Music Assistant user is disabled. Review it in Music Assistant.")
            # Spotify sharing consent cannot grant or remove a person's progress
            # source. Preserve only explicit, existing native assignments.
            progress = {p["id"] for p in providers if p.get("domain") in PROGRESS_DOMAINS}
            access = sorted(set(access) | (set(user.get("provider_filter") or []) & progress))
            if sorted(user.get("provider_filter") or []) != access:
                await command("auth/user/update", user_id=user["user_id"], provider_filter=access)
        else:
            # Non-recoverable random password; never save it. Native MA can link a
            # login or reset it later. Home Starter playback uses its scoped API.
            await command("auth/user/create", username=name.casefold(), display_name=name, password=secrets.token_urlsafe(48), provider_filter=access)
        users = await command("auth/users")
        checked = [u for u in users if normalized(u.get("display_name")) == normalized(name) or normalized(u.get("username")) == normalized(name)]
        if len(checked) != 1 or sorted(checked[0].get("provider_filter") or []) != access:
            raise ValueError("Music Assistant household source access could not be verified. Retry with user-management permission.")
    return user_status(users, providers, names)


def user_status(users, providers, names=NAMES):
    identities = providers_by_identity(providers)
    count = sum(any(normalized(u.get("display_name")) == normalized(n) or normalized(u.get("username")) == normalized(n) for u in users) for n in names)
    rows = []
    for name in IDENTITIES:
        provider = identities.get(name)
        state = (
            "ready_for_authentication"
            if provider is None
            else "connected"
            if connected(provider)
            else "reauth_required"
            if provider.get("requires_auth")
            else "needs_attention"
            if provider.get("enabled") is False or provider.get("has_error")
            else "preparing"
        )
        rows.append({"name": name, "state": state})
    ready = all(connected(identities.get(n, {})) for n in OVERFLOW)
    running = [p for p in providers if p.get("domain") == "spotify" and connected(p)]
    unexpected = sum(p["id"] not in {i["id"] for i in identities.values()} for p in running)
    return {
        "state": "needs_review" if unexpected else "connected" if count == len(names) and ready else "connected_but_incomplete",
        "users": count,
        "summary": f"Music Assistant users: {count}/{len(names)} configured",
        "spotify": rows,
        "connected": len(running),
        "pending": sum(r["state"] != "connected" for r in rows),
        "unmapped": unexpected,
    }


def choose_provider(providers, occupied, *, personal=None, grant_free=False):
    identities = providers_by_identity(providers)
    order = (personal,) if personal in {"Grant", "Renae"} else OVERFLOW
    for name in order:
        if name == "Grant" and personal != "Grant" and not grant_free:
            continue  # Unknown personal playback state is not evidence of availability.
        provider = identities.get(name, {})
        if connected(provider) and provider["id"] not in occupied:
            return provider["id"]
    raise ValueError("Music accounts are busy. Try another source or wait for playback to finish.")


def item_sources(item):
    mappings = item.get("provider_mappings") or []
    sources = {m.get("provider_instance") for m in mappings if m.get("available", True)}
    provider = item.get("provider")
    if provider and provider != "library":
        sources.add(provider)
    uri = item.get("uri") or item.get("path") or ""
    if "://" in uri:
        sources.add(uri.split("://", 1)[0])
    return sources - {None}


def visible(item, name, providers):
    uri = str(item.get("uri") or "").casefold()
    if item.get("kind", item.get("media_type")) == "playlist" and "builtin" in uri and "infinite" in uri:
        return False
    spotify = {p["id"] for p in providers if p.get("domain") == "spotify"}
    sources = set(item.get("sources") or item_sources(item))
    # Explicit household collection sharing is metadata access, not permission
    # to select a personal playback account. Direct provider browsing stays scoped.
    if item.get("household_collection") is True and item.get("kind", item.get("media_type")) in {
        "playlist",
        "podcast",
        "podcast_episode",
        "audiobook",
        "album",
        "artist",
        "track",
        "radio",
    }:
        known = {p["id"] for p in providers_by_identity(providers).values() if connected(p)}
        if sources & known:
            return True
    if sources & spotify:
        return bool(sources & set(source_access(name, providers)) & spotify)
    if sources and sources <= {"library", "builtin"}:
        return False  # A mixed library folder does not establish source ownership.
    # Domain-only Spotify references cannot prove household ownership.
    return "spotify" not in sources
