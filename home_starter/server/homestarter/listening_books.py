"""Fail-closed native audiobook routing. This module never provisions access."""

from .household_music import PROGRESS_DOMAINS, connected, normalized
from .music_runtime import MusicRuntimeError


def needs_route(item, providers):
    if item.get("kind") not in {"audiobook", "podcast_episode"}:
        return False
    sources = set(item.get("sources") or [])
    return bool(
        item.get("progress_source")
        or sources & PROGRESS_DOMAINS
        or any(str(source).startswith(domain + "--") for source in sources for domain in PROGRESS_DOMAINS)
        or any(p.get("domain") in PROGRESS_DOMAINS and (p["id"] in sources or item.get("kind") == "audiobook") for p in providers)
    )


def route(house, config, providers, users, person, version):
    """Require one person, one provider and an exclusive, nonempty native filter."""
    error = "Your audiobook progress connection needs administrator review. Playback was not started."
    people = [p for p in house["people"] if p["id"] == person]
    libraries = [r for r in config["libraries"] if person is not None and person in r["people"]]
    if version != "2.10.7" or len(people) != 1 or len(libraries) != 1 or libraries[0]["people"] != [person]:
        raise MusicRuntimeError(error)
    provider_id = libraries[0]["provider_id"]
    providers_by_id = {p["id"]: p for p in providers}
    provider = providers_by_id.get(provider_id, {})
    if provider.get("domain") != "audiobookshelf" or not connected(provider):
        raise MusicRuntimeError(error)
    if any(r is not libraries[0] and r.get("provider_id") == provider_id for r in config["libraries"]):
        raise MusicRuntimeError(error)
    name = normalized(people[0]["name"])
    matches = [u for u in users if normalized(u.get("display_name")) == name or normalized(u.get("username")) == name]
    if len(matches) != 1 or matches[0].get("enabled") is False or not matches[0].get("user_id"):
        raise MusicRuntimeError(error)
    user = matches[0]
    progress_ids = {p["id"] for p in providers if p.get("domain") in PROGRESS_DOMAINS}
    filters = user.get("provider_filter")
    if not isinstance(filters, list) or not filters or not set(filters) <= providers_by_id.keys() or set(filters) & progress_ids != {provider_id}:
        raise MusicRuntimeError(error)
    for other in users:
        if other is user or other.get("enabled") is False:
            continue
        # Empty native filters mean unrestricted access, including after source
        # deletion. Do not convert that into implicit household consent.
        allowed = other.get("provider_filter")
        if other.get("user_id") == user["user_id"] or not isinstance(allowed, list) or not allowed or provider_id in allowed:
            raise MusicRuntimeError(error)
    return {"user_id": user["user_id"], "provider_id": provider_id}


def native_uri(value, selected):
    """Pin the exact provider instance rather than letting library choice drift."""
    provider = selected["provider_id"]
    kind = value.get("media_type")
    if kind not in {"audiobook", "podcast_episode"}:
        raise MusicRuntimeError("This audiobook source is unavailable. Choose it again from your library.")
    ids = {
        m.get("item_id")
        for m in value.get("provider_mappings") or []
        if m.get("provider_instance") == provider and m.get("available", True) and m.get("item_id")
    }
    if value.get("provider") == provider and value.get("item_id"):
        ids.add(value["item_id"])
    if len(ids) != 1:
        raise MusicRuntimeError("This audiobook source is unavailable. Choose it again from your library.")
    return f"{provider}://{kind}/{ids.pop()}"


def confirms(value, uri):
    if value.get("uri") == uri:
        return True
    provider, rest = uri.split("://", 1)
    kind, item_id = rest.split("/", 1)
    return value.get("media_type") == kind and any(
        m.get("provider_instance") == provider and m.get("item_id") == item_id and m.get("available", True) for m in value.get("provider_mappings") or []
    )
