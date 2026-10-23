"""Household collection metadata; playback credentials and allocation stay separate."""

import asyncio
import re
import time

from .household_music import connected, providers_by_identity, visible
from .music_runtime import MusicRuntimeError

KINDS = {
    "playlists": ("Playlists", "playlist"),
    "podcasts": ("Podcasts", "podcast"),
    "audiobooks": ("Audiobooks", "audiobook"),
    "albums": ("Albums", "album"),
    "artists": ("Artists", "artist"),
    "tracks": ("Tracks", "track"),
    "radios": ("Saved radio", "radio"),
}
PAGE_SIZE = 60
PREFIX = "homestarter-collections://"


def folder(kind, offset=0):
    return {
        "media_type": "folder",
        "name": ("More " + KINDS[kind][0].lower()) if offset else KINDS[kind][0],
        "path": PREFIX + kind + "/" + str(offset),
        "provider": "household_collections",
        "continuation": offset > 0,
    }


def roots():
    return [folder(kind) for kind in KINDS]


def selection(path):
    match = re.fullmatch(re.escape(PREFIX) + r"([a-z]+)/(\d{1,7})", path or "")
    if not match or match[1] not in KINDS:
        return None
    return match[1], int(match[2])


def merge(values, kind):
    """Merge exact upstream identities, never names or cross-provider lookalikes."""
    records, aliases = [], {}
    for value in values:
        if not isinstance(value, dict) or value.get("media_type") != kind:
            continue
        mappings = value.get("provider_mappings") or []
        keys = {
            (m.get("catalogue_namespace") or m.get("provider_domain") or m.get("provider_instance"), str(m["item_id"]))
            for m in mappings
            if isinstance(m, dict) and m.get("item_id") is not None
        }
        provider = value.get("provider")
        if isinstance(provider, str) and value.get("item_id") is not None:
            keys.add(("spotify" if provider.startswith("spotify") else provider, str(value["item_id"])))
        if not keys:
            keys.add(("uri", value.get("uri")))
        matches = {aliases[key] for key in keys if key in aliases}
        if matches:
            index = min(matches)
            target = records[index]
            combined = [*target.get("provider_mappings", []), *mappings]
            for other in matches - {index}:
                combined.extend(records[other].get("provider_mappings", []))
                records[other] = None
                aliases = {key: index if value == other else value for key, value in aliases.items()}
            target["provider_mappings"] = list({(m.get("provider_instance"), m.get("item_id")): m for m in combined}.values())
        else:
            index = len(records)
            records.append({**value, "provider_mappings": list(mappings), "household_collection": True})
        for key in keys:
            aliases[key] = index
    return sorted((r for r in records if r is not None), key=lambda r: (str(r.get("name") or "").casefold(), str(r.get("uri") or "")))


class Collections:
    def __init__(self, runtime):
        self.runtime = runtime
        self.cache = {}

    async def page(self, endpoint, connection, path, providers, query=None):
        kind, offset = selection(path)
        spotify = [p for p in providers_by_identity(providers).values() if connected(p)]
        key = (connection["generation"], connection["server_id"], tuple(sorted(p["id"] for p in spotify)), kind, query or "")
        cached = self.cache.get(key)
        if not cached or time.monotonic() - cached[0] > 120:
            values, incomplete = await self.collect(endpoint, connection, kind, spotify, query)
            values = [v for v in values if isinstance(v, dict) and visible({**v, "household_collection": True}, "House", providers)]
            cached = (time.monotonic(), merge(values, KINDS[kind][1]), incomplete)
            self.cache = {k: v for k, v in self.cache.items() if time.monotonic() - v[0] < 120}
            if len(self.cache) >= 30:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = cached
        values = cached[1][offset : offset + PAGE_SIZE]
        if offset + PAGE_SIZE < len(cached[1]):
            values = [*values, folder(kind, offset + PAGE_SIZE)]
        return values, cached[2], len(cached[1])

    async def collect(self, endpoint, connection, kind, spotify, query):
        async def command(name, **args):
            return await self.runtime.command(endpoint, connection, name, **args)

        if query:
            values, incomplete = await self.collect(endpoint, connection, kind, spotify, None)
            return [v for v in values if isinstance(v, dict) and query.casefold() in str(v.get("name") or "").casefold()], incomplete
        values, incomplete = [], False
        try:
            # Native MA already merges provider mappings for many shared items.
            for offset in range(0, 10000, 500):
                batch = await command("music/" + kind + "/library_items", limit=500, offset=offset, summary=False)
                if isinstance(batch, dict):
                    batch = batch.get("items", [])
                if not isinstance(batch, list):
                    raise MusicRuntimeError("The combined library could not be read.")
                values.extend(batch)
                if len(batch) < 500:
                    break
            else:
                incomplete = True
        except MusicRuntimeError:
            incomplete = True

        async def account(provider):
            # Union MA's account collections as well as its combined library.
            # This never changes sync-back, follows, ownership or playback settings.
            root = await command("music/browse", path=provider["id"] + "://")
            category = next(
                (r for r in root if r.get("media_type") == "folder" and (r.get("item_id") == kind or str(r.get("name", "")).casefold() == kind)), None
            )
            return await command("music/browse", path=category["path"]) if category else []

        if kind != "radios":
            results = await asyncio.gather(*(account(p) for p in spotify), return_exceptions=True)
            for result in results:
                if isinstance(result, list):
                    values.extend(result)
                else:
                    incomplete = True
        return values, incomplete
