"""Shared read-only catalogue projection; no playback/configuration writes."""

from __future__ import annotations

import asyncio
import copy
import time

from .ma_compatibility import provider_contract, user_contract
from .media_discovery import MediaDiscovery, radio_rank
from .metadata_projection import ArtworkLedger, fingerprint, native_record, project, record_ids


class MetadataPreview:
    def __init__(self, command, app_read, art_read, house, surface):
        self.command, self.app_read, self.art_read = command, app_read, art_read
        self.house, self.surface = house, surface
        self.profiles = [{"id": "house", "name": "House"}, *[{"id": p["id"], "name": p["name"]} for p in house["people"]]]
        self.providers = {}
        self.rows = {"artists": [], "albums": [], "playlists": [], "tracks": []}
        self.states, self.saved = [], {}
        self.ledger, self.bytes = ArtworkLedger(), {}
        self.model_cache = {}
        self.offered = {}
        self.region = {}
        self.directory_lookup = None
        self.discovery_children = {}
        self.discovery_cache = {}
        self.catalogue_task = None
        self.user_bindings = None
        self.read_health = None

    async def policy(self, profile):
        person = next((p for p in self.profiles if p["id"] == profile), None)
        if not person:
            raise PermissionError("Choose a current household profile.")
        users = await self.command("auth/users")
        if user_contract(users) is None:
            raise PermissionError("Native user response needs a compatibility check.")
        matches = (
            [u for u in users if u.get("user_id") == self.user_bindings.get(profile)]
            if self.user_bindings is not None
            else [u for u in users if str(u.get("display_name") or u.get("username") or "").strip().casefold() == person["name"].casefold()]
        )
        if len(matches) != 1 or not matches[0].get("enabled", True):
            raise PermissionError("This profile's native source mapping needs checking.")
        user = matches[0]
        sources = user.get("provider_filter")
        if not isinstance(sources, list) or not sources or any(not isinstance(s, str) for s in sources) or not set(sources) <= self.providers.keys():
            raise PermissionError("This profile's source filters are missing or changed.")
        allowed = [s for s in sources if self.providers[s].get("available")]
        return allowed, fingerprint([self.house["epoch"], profile, user["user_id"], sorted(sources)])

    async def prepare(self, *, defer_catalogue=False):
        self.providers = provider_contract(await self.command("providers"))
        if self.providers is None:
            raise ValueError("Native provider response needs a compatibility check.")

        async def saved_profile(profile):
            person = None if profile["id"] == "house" else profile["id"]
            view = await self.app_read("/api/listening/" + self.surface + ("?person=" + person if person else ""))
            return profile["id"], view

        for identity, view in await asyncio.gather(*(saved_profile(p) for p in self.profiles)):
            self.saved[identity] = {key: view.get(key, []) for key in ("favorites", "recent")}
            self.discovery_children[identity] = view.get("browse") is not True
        self.catalogue_pending = defer_catalogue
        if not defer_catalogue:
            await self.load_catalogue()

    async def ensure_catalogue(self):
        if not getattr(self, "catalogue_pending", False):
            return
        if self.catalogue_task is None:
            self.catalogue_task = asyncio.create_task(asyncio.wait_for(self.load_catalogue(), 60))
        # A cancelled browser read must not cancel another reader's shared load.
        await asyncio.shield(self.catalogue_task)
        self.catalogue_pending = False

    async def load_catalogue(self):
        categories = ("artists", "albums", "playlists")

        async def library(category):
            rows, offset, seen = [], 0, set()
            try:
                while True:
                    page = await asyncio.wait_for(self.command("music/" + category + "/library_items", limit=500, offset=offset, summary=False), 15)
                    if isinstance(page, dict):
                        page = page.get("items", [])
                    if not isinstance(page, list):
                        raise ValueError("Unsupported catalogue page")
                    identity = fingerprint([r.get("uri") for r in page])
                    if page and identity in seen:
                        raise ValueError("Source did not advance its page")
                    seen.add(identity)
                    rows.extend(page)
                    offset += len(page)
                    if len(page) < 500:
                        break
                return [(category, rows, {"category": category, "source": "MA combined library", "state": "ready"})]
            except (TimeoutError, RuntimeError, ValueError):
                return [(category, rows, {"category": category, "source": "MA combined library", "state": "partial"})]

        async def account(provider):
            try:
                root = await asyncio.wait_for(self.command("music/browse", path=provider["instance_id"] + "://"), 3)
            except (TimeoutError, RuntimeError, ValueError):
                return [(None, [], {"source": "Spotify account collection", "state": "unavailable"})]

            async def folder(category):
                selected = next(
                    (r for r in root if r.get("media_type") == "folder" and (r.get("item_id") == category or str(r.get("name", "")).casefold() == category)),
                    None,
                )
                if not selected:
                    return None
                try:
                    values = await asyncio.wait_for(self.command("music/browse", path=selected["path"]), 3)
                    partial = any(r.get("media_type") == "folder" and r.get("name") != ".." for r in values)
                    rows = [r for r in values if isinstance(r, dict) and r.get("media_type") != "folder"]
                    return category, rows, {"category": category, "source": "Spotify account collection", "state": "partial" if partial else "ready"}
                except (TimeoutError, RuntimeError, ValueError):
                    return category, [], {"category": category, "source": "Spotify account collection", "state": "unavailable"}

            return [r for r in await asyncio.gather(*(folder(c) for c in categories)) if r]

        tasks = [*(library(c) for c in categories), *(account(p) for p in self.providers.values() if p.get("domain") == "spotify" and p.get("available"))]
        results = await asyncio.gather(*tasks)
        # Deterministic merge order, independent of network completion order.
        for values in results:
            for category, rows, state in values:
                if category:
                    self.rows[category].extend(rows)
                self.states.append(state)

    async def models(self, profile, category):
        allowed, policy = await self.policy(profile)
        saved = {
            r["id"]
            for key in ("favorites", "recent")
            for r in self.saved[profile][key]
            if isinstance(r, dict) and r.get("kind") in {"track", "artist", "album", "playlist"}
        }
        cache_key = (profile, category, policy, fingerprint(sorted(saved)))
        if cache_key in self.model_cache:
            values, unassigned = self.model_cache[cache_key]
            return values, allowed, policy, unassigned
        values, unassigned = project(self.rows[category], category, profile, allowed, saved=saved)
        favourites = {r["id"] for r in self.saved[profile]["favorites"] if isinstance(r, dict) and r.get("kind") in {"track", "artist", "playlist"}}
        for value in values:
            value["favorite"] = bool(record_ids(value) & favourites)
        self.model_cache[cache_key] = values, unassigned
        return values, allowed, policy, unassigned

    async def read(self, context, body):
        if set(body) - {"profile", "generation", "command", "args"}:
            raise PermissionError("Unsupported read request.")
        profile, generation, command = body.get("profile"), body.get("generation"), body.get("command")
        args = body.get("args") or {}
        if not isinstance(args, dict):
            raise PermissionError("Unsupported read arguments.")
        if set(args) & {"user", "token", "password", "url", "force_refresh"}:
            raise PermissionError("Unsupported read arguments.")
        if (
            self.read_health is not None
            and not self.read_health["features"]["catalogue_read_contract"]
            and (command.startswith("music/") and command != "providers/icon" or command in {"household/favourites", "household/recent", "household/shelves"})
        ):
            raise ValueError("Library format needs a compatibility check. Radio and podcast discovery remain separate.")
        allowed, policy = await self.policy(profile)
        if getattr(self, "catalogue_pending", False) and (
            command.startswith("music/") or command in {"household/favourites", "household/recent", "household/shelves"}
        ):
            await self.ensure_catalogue()
            fresh_allowed, fresh_policy = await self.policy(profile)
            if fresh_policy != policy or set(fresh_allowed) != set(allowed):
                raise PermissionError("Source assignments changed while the catalogue loaded.")
        self.ledger.select(context, profile, generation, policy)
        binding = dict(self.ledger.contexts[context])

        def publish(rows):
            if self.ledger.contexts.get(context) != binding:
                raise PermissionError("This metadata request was superseded.")
            output = []
            for row in rows:
                value = self.ledger.register(context, row, binding)
                selection = fingerprint([context, binding["profile"], binding["policy"], row.get("uri")])
                self.offered[selection] = {"profile": profile, "policy": policy, "row": row}
                value["household_selection"] = selection
                output.append(value)
            return output

        if command == "providers/icon" and args.get("provider") in {p["domain"] for p in self.providers.values()}:
            return None  # Native accessible icon fallback; no arbitrary image read.

        if command == "music/get_library_item":
            category = {"artist": "artists", "album": "albums", "playlist": "playlists", "track": "tracks"}.get(args.get("media_type"))
            if not category:
                raise PermissionError("Unsupported library item.")
            values, _, _, _ = await self.models(profile, category)
            item = next(
                (v for v in values if str(v.get("item_id")) == str(args.get("item_id")) and v.get("provider") == args.get("provider_instance_id_or_domain")),
                None,
            )
            if not item:
                item = next(
                    (
                        o["row"]
                        for o in self.offered.values()
                        if o["profile"] == profile
                        and o["policy"] == policy
                        and o["row"].get("media_type") == args.get("media_type")
                        and str(o["row"].get("item_id")) == str(args.get("item_id"))
                        and o["row"].get("provider") == args.get("provider_instance_id_or_domain")
                    ),
                    None,
                )
            if not item:
                raise PermissionError("Item unavailable for this profile.")
            return publish([item])[0] if item.get("provider") == "library" else None

        if command == "household/discovery":
            if set(args) - {"category", "query", "offset", "limit"}:
                raise PermissionError("Unsupported discovery request.")
            offset, limit = args.get("offset", 0), args.get("limit")
            if type(offset) is not int or not 0 <= offset <= 1_000_000 or (limit is not None and (type(limit) is not int or not 1 <= limit <= 100)):
                raise PermissionError("Choose a supported discovery page.")
            search_args = {k: v for k, v in args.items() if k in {"category", "query"}}
            # Reuse the existing listening permission projection, not names or
            # inferred age. Missing commissioning evidence stays restrictive.
            child = self.discovery_children.get(profile, True)
            key = fingerprint([profile, policy, sorted(allowed), child, self.region, self.saved[profile], search_args])
            cached = self.discovery_cache.get(key)
            now = time.monotonic()
            if cached and now - cached[0] < 300:
                result = copy.deepcopy(cached[1])
            else:
                result = await MediaDiscovery(self.command, self.providers, region=self.region, directory_lookup=self.directory_lookup).find(
                    args.get("category"), args.get("query", ""), allowed, child=child, saved=self.saved[profile] if profile != "house" else {}
                )
                failed = {s["source"] for s in result["sources"] if s["state"] == "unavailable"}
                if cached and now - cached[0] < 86400 and failed:
                    for row in cached[1]["items"]:
                        if any(m.get("provider_domain") in failed and m.get("provider_instance") in allowed for m in row.get("provider_mappings", [])):
                            result["items"].append(copy.deepcopy(row))
                    result["note"] += (
                        " Previously verified catalogue suggestions are shown for unavailable sources; playback availability is checked when selected."
                    )
                    for state in result["sources"]:
                        if state["source"] in failed:
                            state["state"] = "cached"
                if result["items"] and not failed:
                    # Raw native models only. Profile-bound image/selection tokens
                    # are issued afresh below, never reused across browsers.
                    self.discovery_cache[key] = now, copy.deepcopy(result)
                    while len(self.discovery_cache) > 24:
                        self.discovery_cache.pop(next(iter(self.discovery_cache)))
            fresh_allowed, fresh_policy = await self.policy(profile)
            if fresh_policy != policy or set(fresh_allowed) != set(allowed):
                raise PermissionError("Source assignments changed during discovery.")
            from homestarter.listening_collections import merge

            values = [value for row in result["items"] if (value := native_record(row, allowed))]
            values = merge(values, args["category"])
            if args["category"] == "radio":
                values.sort(key=radio_rank)
            result["total"] = len(values)
            result["offset"] = offset
            # Keep unpaged callers compatible; production explicitly asks for
            # one page. Only that page receives artwork/selection capabilities.
            result["items"] = publish(values[offset : offset + limit] if limit is not None else values[offset:])
            return result

        if command == "config/core/get_value" and args.get("domain") == "player_queues" and str(args.get("key", "")).startswith("default_click_action_"):
            return "details"
        if command in {"music/genres/genres_for_media_item", "music/genres/genre_exclusions_for_media_item", "music/genres/library_items"}:
            return []
        if command in {"household/favourites", "household/recent"}:
            key = "favorites" if command.endswith("favourites") else "recent"
            selected = {r["id"] for r in self.saved[profile][key] if r.get("kind") in {"track", "artist", "playlist"}}
            rows = []
            for category in ("artists", "playlists"):
                values, _, _, _ = await self.models(profile, category)
                rows.extend(v for v in values if record_ids(v) & selected)
            return publish(rows)
        parts = str(command).split("/")
        if len(parts) != 3 or parts[0] != "music" or parts[1] not in self.rows:
            raise PermissionError("This preview only reads catalogue metadata.")
        category, operation = parts[1:]
        values, allowed, policy, _ = await self.models(profile, category)
        if policy != binding["policy"] or self.ledger.contexts.get(context) != binding:
            raise PermissionError("Source assignments changed while reading metadata.")
        if operation == "count":
            return None if any(s.get("state") != "ready" for s in self.states) else len(values)
        if operation == "library_items":
            query = str(args.get("search") or "").casefold()
            values = [v for v in values if not query or query in str(v.get("name", "")).casefold()]
            if args.get("favorite") or args.get("favorite_only"):
                values = [v for v in values if v.get("favorite")]
            chosen = args.get("provider") or []
            chosen = [chosen] if isinstance(chosen, str) else chosen
            if not isinstance(chosen, list) or not set(chosen) <= set(allowed):
                raise PermissionError("Source filter unavailable for this profile.")
            if chosen:
                values = [v for v in values if any(m.get("provider_instance") in chosen for m in v.get("provider_mappings", []))]
            offset, limit = args.get("offset") or 0, args.get("limit") or 100
            if type(offset) is not int or type(limit) is not int or not 0 <= offset <= 1_000_000 or not 1 <= limit <= 500:
                raise PermissionError("Choose a supported catalogue page.")
            return publish(values[offset : offset + limit])
        item = next(
            (
                v
                for v in values
                if str(v.get("item_id")) == str(args.get("item_id")) and v.get("provider") == args.get("provider_instance_id_or_domain", "library")
            ),
            None,
        )
        if not item:
            item = next(
                (
                    offered["row"]
                    for offered in self.offered.values()
                    if offered["profile"] == profile
                    and offered["policy"] == policy
                    and offered["row"].get("media_type") == {"artists": "artist", "albums": "album", "playlists": "playlist", "tracks": "track"}[category]
                    and str(offered["row"].get("item_id")) == str(args.get("item_id"))
                    and offered["row"].get("provider") == args.get("provider_instance_id_or_domain", "library")
                ),
                None,
            )
        if not item:
            raise PermissionError("Item unavailable for this profile.")
        if operation in {"get_artist", "get_album", "get_playlist", "get_track"}:
            return publish([item])[0]
        if category == "artists" and operation == "artist_albums":
            albums, _, _, _ = await self.models(profile, "albums")
            return publish([a for a in albums if any(record_ids(r) & record_ids(item) for r in a.get("artists", []))])
        if category == "albums" and operation == "album_versions":
            return []
        if category == "tracks" and operation == "track_versions":
            return []
        if category == "tracks" and operation == "track_albums":
            album = item.get("album")
            return publish([album]) if isinstance(album, dict) else []
        if category in {"artists", "albums", "playlists"} and operation in {"artist_tracks", "album_tracks", "playlist_tracks"}:
            rows = await self.command(command, item_id=item["item_id"], provider_instance_id_or_domain=item["provider"])
            if isinstance(rows, dict):
                rows = rows.get("items", [])
            result = [v for r in rows if (v := native_record(r, allowed)) is not None]
            # A profile/permission switch during the native read invalidates it.
            fresh_allowed, fresh_policy = await self.policy(profile)
            if fresh_policy != policy or self.ledger.contexts[context]["generation"] != generation or set(fresh_allowed) != set(allowed):
                raise PermissionError("Profile or source assignments changed during this read.")
            return publish(result)
        raise PermissionError("This metadata operation is unavailable.")

    async def artwork(self, context, identity):
        selected = self.ledger.contexts.get(context)
        if not selected:
            raise PermissionError("Reopen the selected profile.")
        allowed, policy = await self.policy(selected["profile"])
        reference = self.ledger.reference(context, identity, policy, allowed)
        key = fingerprint(reference)
        if key not in self.bytes:
            if len(self.bytes) >= 64:
                self.bytes.pop(next(iter(self.bytes)))
            fetched = await self.art_read(reference)
            if fetched:
                self.bytes[key] = fetched
        allowed, policy = await self.policy(selected["profile"])
        self.ledger.reference(context, identity, policy, allowed)
        return self.bytes.get(key)
