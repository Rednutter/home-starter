"""Listener-owned MA control behind authenticated HA ingress; devices remain destinations."""

from __future__ import annotations

import asyncio
import secrets
import time
from copy import deepcopy
from pathlib import Path

from . import (
    catalogue,
    household_music,
    household_services,
    listening_books,
    listening_sessions,
    listening_stations,
    listening_transfer,
    radio_metadata,
    readiness,
    screen_identity,
)
from .music_runtime import MusicRuntimeError, digest, number, private_write


def profile_key(person):
    return "person:" + person if person else "house"


def audiobook_status(config, providers, person):
    """A library binding is setup evidence, never proof of playback or progress sync."""
    if person is None:
        return {"state": "choose_listener", "message": "Choose who is listening to keep their audiobook progress separate."}
    libraries = [r for r in config["libraries"] if person in r["people"]]
    if not libraries or any(not r["provider_id"] for r in libraries):
        return {"state": "not_connected", "message": "Your audiobook library is not connected yet."}
    available = {p["id"] for p in providers if p.get("domain") in {"audiobookshelf", "audible", "storytel"} and household_music.connected(p)}
    if any(r["provider_id"] not in available for r in libraries):
        return {"state": "unavailable", "message": "Your audiobook library is temporarily unavailable. Saved progress is kept."}
    return {"state": "needs_verification", "message": "Your audiobook library needs playback verification. Saved progress stays with this person."}


def media_record(value):
    if not isinstance(value, dict):
        return None
    uri = value.get("uri")
    kind = value.get("media_type")
    folder = kind in {"folder", "podcast"}
    path = value.get("path") if kind == "folder" else uri
    if not isinstance(path, str) or not path or len(path) > 2048:
        return None
    if kind == "playlist" and "builtin" in path.casefold() and "infinite" in path.casefold():
        return None
    return {
        "id": digest([path, value["catalogue_access"]] if value.get("catalogue_access") else path)[:24],
        "title": (radio_metadata.text(value.get("name")) or "Radio") if kind == "radio" else str(value.get("name") or "Untitled")[:240],
        "kind": value.get("media_type"),
        "uri": path,
        "folder": folder,
        "sources": sorted(household_music.item_sources(value)),
        **({"catalogue_access": value["catalogue_access"]} if value.get("catalogue_access") else {}),
        **(
            {"progress_source": True}
            if value.get("provider") in household_music.PROGRESS_DOMAINS
            or any(m.get("provider_domain") in household_music.PROGRESS_DOMAINS for m in value.get("provider_mappings") or [])
            else {}
        ),
        **({"household_collection": True} if value.get("household_collection") is True else {}),
        **({"continuation": True} if value.get("continuation") is True else {}),
    }


class ListeningRuntime:
    def __init__(self, runtime, core, store):
        self.runtime, self.core, self.store = runtime, core, store
        self.path = Path(store.path).parent / "music-listeners.json"
        self.lock = asyncio.Lock()
        self.catalog = {}
        self.mapping_cache = None
        self.regional_cache = None
        from .media_catalogue import MediaCatalogue

        self.media = MediaCatalogue(runtime, core, store)
        from .listening_collections import Collections

        self.collections = Collections(runtime)
        self.collection_view = None
        self.search_view = None
        from .listening_sessions import QueueSessions

        self.sessions = QueueSessions(self)
        self.transfers = listening_transfer.Transfers(self)

    async def regional_radio(self, endpoint, connection, region):
        if not region:
            return []
        key = digest([connection["server_id"], connection["generation"], region])
        if self.regional_cache and self.regional_cache[0] == key and time.monotonic() - self.regional_cache[1] < 600:
            rows = self.regional_cache[2]
        else:
            unique = {}
            results = await asyncio.gather(
                *(
                    self.runtime.command(endpoint, connection, "music/search", search_query=term, media_types=["radio"], providers=["radiobrowser"], limit=12)
                    for term in region["search_terms"][:4]
                ),
                return_exceptions=True,
            )
            if results and all(isinstance(raw, Exception) for raw in results):
                raise MusicRuntimeError("Local radio discovery is unavailable.")
            for raw in results:
                for value in raw.get("radio", []) if isinstance(raw, dict) else []:
                    record = media_record(value)
                    if record and record["kind"] == "radio":
                        unique.setdefault(" ".join(record["title"].casefold().split()), record)
            rows = list(unique.values())[:24]
            self.regional_cache = key, time.monotonic(), rows
        for row in rows:
            self.catalog[row["id"]] = row
        return rows

    def load(self, house, connection):
        identity = digest([connection["server_id"], connection["app"]])
        value = self.store.read(self.path, None)
        if value is None or isinstance(value, dict) and (value.get("epoch") != house["epoch"] or value.get("server") != identity):
            return {"version": 1, "epoch": house["epoch"], "server": identity, "profiles": {}, "leases": {}}
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("profiles"), dict) or not isinstance(value.get("leases"), dict):
            raise MusicRuntimeError("Saved listening state needs checking. Existing progress is preserved.")
        return value

    def save(self, data):
        private_write(self.path, data)

    @staticmethod
    def profile(data, person):
        return data["profiles"].setdefault(profile_key(person), {"favorites": [], "recent": [], "books": {}, "destination": None})

    async def authorize(self, user_id, surface_id, person):
        house = self.store.load()
        surface = next((s for s in house["surfaces"] if s["id"] == surface_id), None)
        if not surface or person and person not in {p["id"] for p in house["people"]}:
            raise ValueError("Choose a current household view.")
        if surface.get("person_id") and person != surface["person_id"]:
            raise PermissionError("This screen is assigned to a specific listening profile.")
        if not user_id:
            raise PermissionError("Use the signed-in household display.")
        admin = await self.core.is_admin(user_id)
        if not admin:
            record = screen_identity.load(self.store, house)["screens"].get(surface_id, {})
            accounts = await screen_identity.accounts(self.core, self.store)
            account = next((u for u in accounts if u["id"] == user_id and not u["issue"] and u["permission"] == "control"), None)
            if (
                record.get("user_id") != user_id
                or not account
                or record.get("user_signature") != account["signature"]
                or record.get("surface_signature") != screen_identity.signature(surface)
            ):
                raise PermissionError("This account is not the configured control display.")
        saved = readiness.load(self.store, house)
        choice = saved["choices"].get("music", {})
        if choice.get("intent") != "wanted" or surface_id not in choice.get("screens", []):
            raise ValueError("Select Music for this display in Home Readiness.")
        return house, surface, saved, admin

    async def bootstrap(self, user_id):
        if not user_id:
            raise PermissionError("Use the signed-in household display.")
        house = self.store.load()
        surfaces = []
        for surface in house["surfaces"]:
            try:
                await self.authorize(user_id, surface["id"], surface.get("person_id"))
            except (PermissionError, ValueError):
                continue
            surfaces.append({"id": surface["id"], "name": surface["name"], "person_id": surface["person_id"]})
        return {"surfaces": surfaces}

    async def players(self, house, surface, saved, person, snapshot):
        # Native MA unique_id is the provider's exact player_id. Never match names.
        if not self.mapping_cache or time.monotonic() - self.mapping_cache[0] > 30:
            async with self.core.websocket() as ws:
                entities = await ws.command("config/entity_registry/list")
                devices = await ws.command("config/device_registry/list")
            self.mapping_cache = time.monotonic(), entities, {d["id"]: d for d in devices}
        _, entities, devices = self.mapping_cache
        choice = saved["choices"]["music"]
        member = saved["members"].get(person, {}) if person else {}
        configured = next((p for p in house["people"] if p["id"] == person), None)
        child = bool(configured and (configured["audience"] != "adult" or member.get("kind") == "child"))
        own_rooms = member.get("rooms", [])
        hidden = set(house.get("preferences", {}).get("surface:" + surface["id"], {}).get("hide", []))
        if person:
            hidden |= set(house.get("preferences", {}).get(person, {}).get("hide", []))
        ma = {p["id"]: p for p in snapshot["players"]}
        result = []
        for e in entities:
            device = devices.get(e.get("device_id"), {})
            area = e.get("area_id") or device.get("area_id")
            player = ma.get(e.get("unique_id"))
            if e.get("platform") != "music_assistant" or e.get("disabled_by") or e.get("hidden_by") or not player:
                continue
            if e["entity_id"] not in choice.get("sources", []) or e["entity_id"] in hidden or e.get("device_id") in saved["devices"]:
                continue
            if child and area not in own_rooms and e.get("device_id") not in member.get("devices", []):
                continue
            result.append(
                {
                    "entity_id": e["entity_id"],
                    "player_id": player["id"],
                    "name": player["name"],
                    "available": player["available"],
                    "single": player["single"],
                    "state": player["state"],
                    "features": player.get("features", []),
                    "own_room": area in own_rooms,
                }
            )
        return result, child

    async def catalog_items(self, endpoint, connection, folder=None, query=None, providers=(), *, access=None, searched=None):
        from .listening_collections import KINDS, roots, selection

        collection = self.catalog.get(folder, {}) if folder else {}
        path = collection.get("uri") if folder else None
        if collection.get("catalogue_access"):
            if access is None:
                raise PermissionError("This catalogue page needs a current profile mapping. Search again.")
            catalogue.require_record(collection, access)
        self.collection_view = None
        self.search_view = None
        selected = selection(path)
        if query:
            if access is None and searched is None:
                raise MusicRuntimeError("This profile's catalogue source assignments need review. Search again after setup.")
            searched = searched or await catalogue.search(self.runtime, endpoint, connection, query, providers, access)
            values = searched["items"]
            if selected:
                values = [v for v in values if v.get("media_type") == KINDS[selected[0]][1]]
            self.search_view = {k: searched[k] for k in ("sources", "incomplete", "issue", "coverage")}
        elif selected:
            values, incomplete, total = await self.collections.page(endpoint, connection, path, providers, query)
            kind = selected[0]
            root = media_record(roots()[list(KINDS).index(kind)])
            self.catalog[root["id"]] = root
            self.collection_view = {"title": KINDS[kind][0], "root": root["id"], "total": total, "incomplete": incomplete, "search": bool(query)}
        elif isinstance(collection.get("_page"), list):
            if collection.get("catalogue_access"):
                if access is None:
                    raise PermissionError("This search page needs a current profile mapping. Search again.")
                catalogue.require_record(collection, access)
            values = collection["_page"]
            self.search_view = collection.get("_search")
        else:
            if folder and path is None:
                raise ValueError("This library selection expired. Open the library again.")
            if collection.get("kind") == "podcast":
                show = await self.runtime.command(endpoint, connection, "music/item_by_uri", uri=path)
                if (
                    not isinstance(show, dict)
                    or show.get("media_type") != "podcast"
                    or not all(isinstance(show.get(k), str) and show[k] for k in ("item_id", "provider"))
                ):
                    raise MusicRuntimeError("This podcast could not be confirmed. Search again before opening episodes.")
                episode_provider, episode_item = show["provider"], show["item_id"]
                if collection.get("catalogue_access"):
                    episode_provider = path.split("://", 1)[0]
                    episode_item = path.split("://", 1)[1].split("/", 1)[1]
                values = await self.runtime.command(
                    endpoint, connection, "music/podcasts/podcast_episodes", item_id=episode_item, provider_instance_id_or_domain=episode_provider
                )
                if collection.get("catalogue_access"):
                    selected = next((p for p in providers if p["id"] == path.split("://", 1)[0]), None)
                    if not selected:
                        raise PermissionError("This podcast source changed. Search again.")
                    values = [{**row, "catalogue_access": access["signature"]} for value in values if (row := catalogue.sanitise(value, selected)) is not None]
                if collection.get("household_collection"):
                    values = [{**v, "household_collection": True} for v in values]
            else:
                values = await self.runtime.command(endpoint, connection, "music/browse", path=path)
        if not isinstance(values, list):
            raise MusicRuntimeError("Music Assistant library could not be read.")
        if not folder and not query and any(p.get("domain") == "spotify" for p in providers):
            spotify = {p["id"] for p in providers if p.get("domain") == "spotify"}
            values = [*roots(), *(v for v in values if not household_music.item_sources(v) & spotify and v.get("provider") != "spotify")]
        continuation = None
        if not selected and len(values) > 60:
            more = {
                "media_type": "folder",
                "name": "More results",
                "path": "homestarter-page://" + secrets.token_hex(16),
                "provider": "household_collections",
                "continuation": True,
            }
            continuation = media_record(more)
            continuation["_page"] = values[60:]
            continuation["_search"] = self.search_view
            if query or collection.get("catalogue_access"):
                continuation["catalogue_access"] = access["signature"]
            values = [*values[:60], more]
        result = []
        for value in values:
            if record := media_record(value):
                if record["kind"] not in {"folder", "track", "album", "artist", "playlist", "radio", "audiobook", "podcast", "podcast_episode", "sound_effect"}:
                    continue
                self.catalog[record["id"]] = record
                result.append(record)
        if continuation:
            self.catalog[continuation["id"]] = continuation
            result[-1] = continuation
        if len(self.catalog) > 3000:
            self.catalog = {r["id"]: r for r in result}
        return result

    async def item(self, identifier, profile, shared=()):
        value = self.catalog.get(identifier)
        if value is None:
            value = next((r for r in [*profile["favorites"], *profile["recent"], *profile["books"].values(), *shared] if r["id"] == identifier), None)
        if value is None or value.get("folder"):
            raise ValueError("Choose an item from this listening library.")
        return value

    async def sample(self, endpoint, connection, data, player_id, lease):
        if listening_transfer.pending(data, player_id):
            return False
        if lease.get("item", {}).get("catalogue_access"):
            try:
                await self.record_access(endpoint, connection, lease["item"], lease["scope"])
            except (MusicRuntimeError, PermissionError, ValueError):
                data["leases"].pop(player_id, None)
                return False
        if lease.get("progress_route"):
            try:
                checked = await self.book_route(endpoint, connection, lease["scope"])
            except (MusicRuntimeError, ValueError, PermissionError):
                data["leases"].pop(player_id, None)
                return False
            if checked != lease["progress_route"]:
                data["leases"].pop(player_id, None)
                return False
        player = await self.runtime.command(endpoint, connection, "players/get", player_id=player_id)
        queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=player_id)
        item = (queue or {}).get("current_item") or {}
        media = player.get("current_media") or {}
        if lease.get("transfer_staged"):
            if player.get("playback_state", player.get("state")) == "idle":
                return await self.transfers.staged(endpoint, connection, data, player_id, lease)
            lease.pop("transfer_staged", None)
        current_id = item.get("queue_item_id")
        if lease.get("progress_uri") and not listening_books.confirms(item.get("media_item") or {}, lease["progress_uri"]):
            data["leases"].pop(player_id, None)
            return False
        if lease.get("native_session") and lease.get("kind") not in {"audiobook", "podcast_episode"}:
            context = await self.runtime.command(endpoint, connection, "homestarter/queue_context", queue_id=player_id)
            owned = (
                context.get("session") == lease["native_session"] or lease.get("logical_session") and context.get("logical_session") == lease["logical_session"]
            )
            if not owned or context.get("item") != current_id:
                data["leases"].pop(player_id, None)
                return False
            lease["native_session"], lease["queue_item_id"] = context["session"], current_id
        state = player.get("playback_state", player.get("state"))
        idle_stamp = [(queue or {}).get("elapsed_time_last_updated"), media.get("elapsed_time_last_updated")]
        protocols = [p for p in player.get("output_protocols", []) if p.get("available", True)]
        protocol = next((p for p in protocols if p.get("output_protocol_id") == player.get("active_output_protocol")), None)
        if protocol is None and player.get("active_output_protocol") is None and len(protocols) == 1:
            # MA clears active_output_protocol when stopping the Sendspin stream.
            protocol = protocols[0]
        idle_ack = {"queue_item_id": lease.get("queue_item_id"), "protocol": (protocol or {}).get("output_protocol_id")}
        pause_pending = (
            state == "idle"
            and (queue or {}).get("state") in {"playing", "paused", "idle"}
            and (protocol or {}).get("protocol_domain") == "sendspin"
            and number(lease.get("pause_requested_at"))
            and 0 <= time.time() - lease["pause_requested_at"] <= 3
        )
        idle_pause = (
            state == "idle"
            and (queue or {}).get("state") == "idle"
            and all(number(stamp) for stamp in idle_stamp)
            and (protocol or {}).get("protocol_domain") == "sendspin"
            and (lease.get("idle_pause_ack") == idle_ack or number(lease.get("pause_requested_at")) and 0 <= time.time() - lease["pause_requested_at"] <= 15)
        )
        if lease.get("kind") not in {"audiobook", "podcast_episode"} and current_id in lease.get("queue_items", []):
            lease["queue_item_id"] = current_id
        if (
            not queue
            or not queue.get("active")
            or player.get("available") is False
            or state not in {"playing", "paused", "buffering"}
            and not idle_pause
            and not pause_pending
            or queue.get("queue_id") != player_id
            or player.get("active_source") != player_id
            or item.get("queue_item_id") != lease.get("queue_item_id")
            or media.get("queue_item_id") != lease.get("queue_item_id")
            or connection["generation"] != lease.get("generation")
        ):
            data["leases"].pop(player_id, None)
            return False
        if pause_pending and not idle_pause:
            # Device and queue acknowledgements can arrive in separate updates.
            # Wait briefly with all identity checks above; never save progress.
            return False
        if idle_pause:
            if lease.get("idle_pause_ack") != idle_ack:
                candidate = lease.get("idle_pause_candidate", {})
                if candidate.get("ack") != idle_ack:
                    lease["idle_pause_candidate"] = {"ack": idle_ack, "at": time.time()}
                    return False
                if time.time() - candidate["at"] < 0.2:
                    return False
            # Sendspin stops a paused stream. Keep only our explicitly acknowledged
            # pause with unchanged queue/source/transport IDs, never a generic idle.
            # Metadata timestamps may change while stopped; they cannot transfer
            # ownership and never update a listener's saved progress on their own.
            lease["idle_pause_ack"] = idle_ack
            lease.pop("idle_pause_candidate", None)
        elif state == "playing":
            lease.pop("idle_pause_ack", None)
            lease.pop("idle_pause_candidate", None)
        # Only raw fresh feedback, never an extrapolated queue clock, owns progress.
        position, stamp = player.get("elapsed_time"), player.get("elapsed_time_last_updated")
        paused_queue = (
            (state == "paused" and queue.get("state") == "paused" or idle_pause)
            and number(lease.get("pause_requested_at"))
            and 0 <= time.time() - lease["pause_requested_at"] <= 15
            and number(queue.get("elapsed_time_last_updated"))
            and queue["elapsed_time_last_updated"] >= lease["pause_requested_at"]
        )
        if lease.get("kind") not in {"audiobook", "podcast_episode"} and (state == "paused" or idle_pause):
            lease.pop("pause_requested_at", None)
        if paused_queue:
            # Cast may report only its initial anchor. After an explicit pause
            # acknowledged by this device, MA's frozen owned queue is canonical.
            position, stamp = queue.get("elapsed_time"), queue["elapsed_time_last_updated"]
        elif number(position):
            position += lease.get("position_offset", 0)
        if (
            player.get("playback_state", player.get("state")) == "buffering"
            or lease.get("kind") not in {"audiobook", "podcast_episode"}
            or not number(position)
            or not number(stamp)
            or not 0 <= time.time() - stamp <= 20
            or stamp <= lease.get("last_sample", 0)
        ):
            return False
        duration = item.get("duration")
        if not number(duration) or not 0 <= position <= duration:
            return False
        if "awaiting_position" in lease and not paused_queue:
            if abs(position - lease["awaiting_position"]) > 20:
                return False
            lease.pop("awaiting_position")
        profile = data["profiles"].get(lease["scope"])
        if profile is None:
            return False
        profile["books"][lease["item"]["id"]] = {
            **lease["item"],
            "position": position,
            "duration": duration,
            "updated_at": stamp,
            "position_source": "ma_paused_queue" if paused_queue else "device_position",
        }
        if paused_queue:
            lease.pop("pause_requested_at", None)
            lease.pop("awaiting_position", None)
        lease["last_sample"] = stamp
        return True

    async def pause_owned(self, endpoint, connection, data, pid, lease):
        if lease.get("transfer_staged"):
            await self.sample(endpoint, connection, data, pid, lease)
            if data["leases"].get(pid) is lease and lease.get("transfer_staged"):
                return  # Already quiet; do not resume a transferred paused queue to stop it.

        lease["pause_requested_at"] = time.time()
        await self.runtime.control(endpoint, connection, "player_queues/pause", queue_id=pid)
        for _ in range(10):
            await self.sample(endpoint, connection, data, pid, lease)
            if pid not in data["leases"] or "pause_requested_at" not in lease:
                break
            await asyncio.sleep(0.25)

    async def view(self, user, surface_id, person=None, folder=None, query=None):
        searched, initial_access = None, None
        if query:
            outside_house, outside_surface, outside_saved, _ = await self.authorize(user, surface_id, person)
            outside_snapshot = await self.runtime.snapshot()
            outside_connection = self.runtime.connection()
            outside_endpoint = await self.runtime.endpoint()
            if not outside_connection or not outside_snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant in Home Starter.")
            _, outside_child = await self.players(outside_house, outside_surface, outside_saved, person, outside_snapshot)
            if outside_child:
                raise PermissionError("This view uses its permitted listening choices.")
            try:
                initial_access = await catalogue.policy(
                    self.runtime, outside_endpoint, outside_connection, outside_house, person, outside_snapshot.get("providers", [])
                )
                searched = await catalogue.search(
                    self.runtime, outside_endpoint, outside_connection, query, outside_snapshot.get("providers", []), initial_access
                )
            except MusicRuntimeError:
                searched = {
                    "items": [],
                    "sources": [],
                    "incomplete": True,
                    "issue": "This profile's catalogue mapping is unavailable or needs review. No unrestricted search was used.",
                    "coverage": "Catalogue access not verified.",
                }
        async with self.lock:
            house, surface, saved, _ = await self.authorize(user, surface_id, person)
            snapshot = await self.runtime.snapshot()
            connection, endpoint = self.runtime.connection(), await self.runtime.endpoint()
            if not connection or not snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant in Home Starter.")
            data = self.load(house, connection)
            profile = self.profile(data, person)
            players, child = await self.players(house, surface, saved, person, snapshot)
            await self.transfers.reconcile(endpoint, connection, data, profile_key(person), players)
            for permitted_player in players:
                permitted_player["transfer_pending"] = listening_transfer.pending(data, permitted_player["player_id"])
            if child and (folder or query):
                raise PermissionError("This view uses its permitted listening choices.")
            try:
                access = await catalogue.policy(self.runtime, endpoint, connection, house, person, snapshot.get("providers", []))
            except MusicRuntimeError:
                access = None
            if searched is not None and (initial_access is None or access is None or initial_access["signature"] != access["signature"]):
                searched = {
                    "items": [],
                    "sources": [],
                    "incomplete": True,
                    "issue": "Profile source assignments changed or are unavailable. Search again after review.",
                    "coverage": "Catalogue access not verified.",
                }
            library = (
                [] if child else await self.catalog_items(endpoint, connection, folder, query, snapshot.get("providers", []), access=access, searched=searched)
            )
            listener = next((p["name"] for p in house["people"] if p["id"] == person), "House")
            providers = snapshot.get("providers", [])
            discovery, discovery_issue = False, None
            try:
                identities = household_music.providers_by_identity(providers)
                candidates = (listener,) if listener in {"Grant", "Renae"} else household_music.OVERFLOW
                if any(household_music.connected(identities.get(name, {})) for name in candidates):
                    await self.runtime.account_guard(endpoint, connection)
                    discovery = True
                elif listener in {"Grant", "Renae"}:
                    discovery_issue = "Your music account is not connected yet."
            except (MusicRuntimeError, ValueError):
                discovery_issue = "Music discovery is temporarily unavailable. You can still browse your listening choices."
            library = [r for r in library if household_music.visible(r, listener, providers)]
            service_config = household_services.load(self.store, house)
            region = service_config["region"]
            local_radio, radio_issue = [], None
            if not child and not folder and not query and region:
                try:
                    local_radio = await self.regional_radio(endpoint, connection, region)
                except MusicRuntimeError:
                    radio_issue = "Local radio discovery is unavailable. Your saved stations are still available."
            for player_id, lease in list(data["leases"].items()):
                if lease["scope"] == profile_key(person):
                    if any(p["player_id"] == player_id and p["available"] and p["single"] for p in players):
                        await self.sample(endpoint, connection, data, player_id, lease)
                    else:
                        data["leases"].pop(player_id, None)
            self.save(data)
            default = next((p["entity_id"] for p in players if p["entity_id"] == profile["destination"]), None)
            default = default or next((p["entity_id"] for p in players if p["own_room"]), None)
            if not person:
                default = default or next((p["entity_id"] for p in players if p["available"]), None)

            def public(r):
                return {
                    **{k: r[k] for k in ("id", "title", "kind", "folder", "continuation") if k in r},
                    "queueable": bool(listening_sessions.queueable(r, providers)),
                    "source_scoped": bool(r.get("catalogue_access")),
                }

            def admitted(r, name):
                return household_music.visible(r, name, providers) and (
                    not r.get("catalogue_access") or access is not None and r["catalogue_access"] == access["signature"]
                )

            books = sorted(profile["books"].values(), key=lambda b: b.get("updated_at", 0), reverse=True)
            channels = []
            for row in self.media.view()["items"]:
                record = media_record({"uri": row["uri"], "media_type": row.get("kind") or "radio", "name": row["name"]})
                if record:
                    record.update(
                        id=digest(row["id"])[:24],
                        catalogue_id=row["id"],
                        category=row["category"],
                        subcategory=row["subcategory"],
                        sources=["ambient" if row["category"] == "ambient" else "listnr"],
                    )
                    self.catalog[record["id"]] = record
                    channels.append({**public(record), "category": row["category"], "subcategory": row["subcategory"]})
            sessions = await self.sessions.view(endpoint, connection, data, house, players, profile_key(person))
            if child:
                for session in sessions:
                    session["can_takeover"] = False
            takeover = profile.get("takeover")
            if takeover and takeover.get("expires", 0) < time.time():
                profile.pop("takeover", None)
                takeover = None
            self.save(data)
            preferred_pid = next((p["player_id"] for p in players if p["entity_id"] == default), None)
            owned_session = next(
                (
                    (pid, lease)
                    for pid, lease in sorted(data["leases"].items(), key=lambda pair: pair[0] != preferred_pid)
                    if lease["scope"] == profile_key(person)
                ),
                None,
            )
            sleep = profile.get("sleep")
            if sleep and (not owned_session or sleep.get("player_id") != owned_session[0] or sleep.get("session") != owned_session[1].get("session")):
                sleep = None
            session_title = owned_session[1]["item"]["title"] if owned_session else None
            if owned_session and owned_session[1].get("kind") == "radio":
                session_title = radio_metadata.text(session_title) or "Radio"
            if owned_session and owned_session[1].get("kind") == "track":
                checked_session = next((s for s in sessions if s["player_id"] == owned_session[0]), {})
                current_title = next((r["title"] for r in checked_session.get("queue", []) if r["current"]), None)
                if current_title and current_title != "Queued audio":
                    session_title = current_title
            keep_it_going = bool(owned_session and await self.continuation_supported(endpoint, connection, providers, owned_session[0], owned_session[1]))
            try:
                final_access = await catalogue.policy(self.runtime, endpoint, connection, house, person, providers)
            except MusicRuntimeError:
                final_access = None
            if access is not None and (final_access is None or final_access["signature"] != access["signature"]):
                self.search_view = {
                    "sources": [],
                    "incomplete": True,
                    "issue": "Source assignments changed while loading. Search again.",
                    "coverage": "Catalogue access needs review.",
                }
            access = final_access
            library = [r for r in library if not r.get("catalogue_access") or access is not None and r["catalogue_access"] == access["signature"]]
            return {
                "epoch": house["epoch"],
                "person_id": person,
                "bound_profile": surface.get("person_id"),
                "profiles": [{"id": p["id"], "name": p["name"]} for p in house["people"] if not surface["person_id"] or surface["person_id"] == p["id"]],
                "players": players,
                "sessions": sessions,
                "takeover": takeover,
                "transfer": await self.transfers.model(
                    endpoint, data, profile, profile_key(person), players, source_pid=owned_session[0] if owned_session else None
                ),
                "stations": listening_stations.view(profile, providers, endpoint.get("version") if isinstance(endpoint, dict) else None, access),
                "default_destination": default,
                "browse": not child,
                "library": [public(r) for r in library],
                "search": self.search_view,
                "collection": self.collection_view if not child else None,
                "channels": channels,
                "discovery": discovery,
                "keep_it_going": keep_it_going,
                "discovery_issue": discovery_issue,
                "regional_radio": {"name": region["name"], "items": [public(r) for r in local_radio], "issue": radio_issue}
                if region and not child and not folder and not query
                else None,
                "favorites": [public(r) for r in profile["favorites"] if admitted(r, listener)],
                "shared": [public(r) for r in self.profile(data, None)["favorites"] if admitted(r, "House")] if person else [],
                "recent": [public(r) for r in profile["recent"] if admitted(r, listener)],
                "books": [{**public(r), "position": r["position"], "duration": r["duration"]} for r in books if admitted(r, listener)],
                "audiobooks": audiobook_status(service_config, providers, person),
                "session": {"player_id": owned_session[0], "title": session_title} if owned_session else None,
                "delayed": {"at": profile["delayed"]["at"], "title": profile["delayed"]["item"]["title"], "item": profile["delayed"]["item"]["id"]}
                if profile.get("delayed")
                else None,
                "sleep": sleep,
            }

    async def action(self, user, surface_id, person, body, *, expected_job=None):
        if body.get("action") in {"station_preview", "station_refine"}:
            return await self.preview_station(user, surface_id, person, body)
        async with self.lock:
            house, surface, saved, _ = await self.authorize(user, surface_id, person)
            if (
                set(body) - {"epoch", "action", "player", "item", "value", "settings", "session", "entry", "confirmation", "station", "preview", "target"}
                or body.get("epoch") != house["epoch"]
            ):
                raise ValueError("Refresh this listening view before using it.")
            snapshot = await self.runtime.snapshot()
            connection, endpoint = self.runtime.connection(), await self.runtime.endpoint()
            if not connection or not snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant in Home Starter.")
            data = self.load(house, connection)
            profile = self.profile(data, person)
            shared = self.profile(data, None)["favorites"] if person else []
            if expected_job is not None and profile.get("delayed") != expected_job:
                return
            players, child = await self.players(house, surface, saved, person, snapshot)
            await self.transfers.reconcile(endpoint, connection, data, profile_key(person), players)
            action = body.get("action")
            if action in {"transfer_prepare", "transfer_confirm", "transfer_cancel", "transfer_recheck"}:
                await self.transfers.action(endpoint, connection, data, profile, profile_key(person), players, snapshot.get("providers", []), body)
                self.save(data)
                return

            if action in {"station_save", "station_preview", "station_refine", "station_feedback", "station_reset"}:
                await listening_stations.action(self, endpoint, connection, profile, body, child, person=person)
                self.save(data)
                return
            if action == "start_now" or expected_job is not None:
                job = profile.get("delayed")
                if not job:
                    raise ValueError("There is no scheduled listening session.")
                self.catalog[job["item"]["id"]] = job["item"]
                body = {**body, "player": job["player"], "item": job["item"]["id"]}
                action = "play_item"
            if action in {"favorite", "unfavorite"}:
                item = await self.item(body.get("item"), profile, shared)
                await self.record_access(endpoint, connection, item, profile_key(person))
                listener = next((p["name"] for p in house["people"] if p["id"] == person), "House")
                if not household_music.visible(item, listener, snapshot.get("providers", [])):
                    raise PermissionError("This source is private. Choose from your listening library.")
                if child and item["id"] not in {r["id"] for r in [*profile["favorites"], *profile["recent"], *shared]}:
                    raise PermissionError("Choose permitted listening content.")
                profile["favorites"] = [r for r in profile["favorites"] if r["id"] != item["id"]]
                if action == "favorite":
                    profile["favorites"] = [item, *profile["favorites"]][:60]
                self.save(data)
                return
            if action == "cancel_delay":
                profile.pop("delayed", None)
                self.save(data)
                return
            player = next((p for p in players if p["entity_id"] == body.get("player") and p["available"] and p["single"]), None)
            if not player:
                raise ValueError("Choose an available permitted single speaker.")
            pid, scope = player["player_id"], profile_key(person)
            if listening_transfer.pending(data, pid):
                raise ValueError(listening_transfer.UNKNOWN)
            if action == "destination":
                profile["destination"] = player["entity_id"]
                self.save(data)
                return
            lease = data["leases"].get(pid)
            if action in {
                "queue_join",
                "queue_leave",
                "queue_add",
                "queue_next",
                "queue_move",
                "queue_remove",
                "queue_takeover_prepare",
                "queue_takeover",
                "queue_takeover_cancel",
            }:
                if child and action in {"queue_takeover_prepare", "queue_takeover"}:
                    raise PermissionError("A parent must confirm taking over another person's queue.")
                item = await self.item(body.get("item"), profile, shared) if action in {"queue_add", "queue_next"} else None
                if item:
                    await self.record_access(endpoint, connection, item, scope)
                    listener = next((p["name"] for p in house["people"] if p["id"] == person), "House")
                    if not household_music.visible(item, listener, snapshot.get("providers", [])):
                        raise PermissionError("This source is private. Choose from your listening library.")
                    if child and item["id"] not in {r["id"] for r in [*profile["favorites"], *profile["recent"], *shared]}:
                        raise PermissionError("Choose permitted listening content.")
                await self.sessions.action(endpoint, connection, data, profile, scope, player, body, item, user=user, surface=surface_id)
                if action == "queue_takeover":
                    profile["destination"] = player["entity_id"]
                self.save(data)
                return
            if action in {"play_radio", "play_ambient"}:
                if not body.get("item"):
                    row = self.media.choose("radio" if action == "play_radio" else "ambient", body.get("value"))
                    record = media_record({"uri": row["uri"], "media_type": row.get("kind") or "radio", "name": row["name"]})
                    record.update(
                        id=digest(row["id"])[:24],
                        catalogue_id=row["id"],
                        category=row["category"],
                        sources=["ambient" if row["category"] == "ambient" else "listnr"],
                    )
                    self.catalog[record["id"]] = record
                    body = {**body, "item": record["id"]}
                action = "play_item"
            if action == "play_playlist":
                if (await self.item(body.get("item"), profile, shared))["kind"] != "playlist":
                    raise ValueError("Choose a playlist from your listening choices.")
                action = "play_item"
            if action in {"surprise_me", "something_different"}:
                from .media_discovery import constraints

                options = constraints(body.get("settings", profile.get("discovery_settings", {}) if action == "something_different" else {}))
                if child:
                    options["exclude_explicit"] = True
                if action == "something_different" and (not lease or lease["scope"] != scope):
                    raise ValueError("Start your listening session before choosing something different.")
                item = {"id": "discovery", "title": "Surprise Me", "kind": "track", "uri": "spotify://track/discovery", "sources": ["spotify"]}
                await self.play(endpoint, connection, data, profile, scope, player, item, user, surface_id, discovery=options)
                profile["discovery_settings"] = options
                self.save(data)
                return
            if action == "keep_it_going":
                if not lease or lease["scope"] != scope:
                    raise ValueError("Start your listening session before enabling Keep It Going.")
                if not await self.continuation_supported(endpoint, connection, snapshot.get("providers", []), pid, lease):
                    raise ValueError("Keep It Going is unavailable for this protected source/session. Your queue was kept.")
                await self.sample(endpoint, connection, data, pid, lease)
                if pid not in data["leases"]:
                    raise ValueError("The speaker session changed. Choose your music again.")
                await self.runtime.control(endpoint, connection, "homestarter/keep_going", queue_id=pid, expected_item=lease["queue_item_id"])
                return
            if action in {"play_item", "resume", "delay"}:
                item = await self.item(body.get("item"), profile, shared)
                await self.record_access(endpoint, connection, item, scope)
                if item.get("catalogue_id"):
                    await self.media.sync()
                    row = self.media.item(item["catalogue_id"])
                    item = {**item, "uri": row["uri"], "title": row["name"]}
                listener = next((p["name"] for p in house["people"] if p["id"] == person), "House")
                if not household_music.visible(item, listener, snapshot.get("providers", [])):
                    raise PermissionError("This source is private. Choose from your listening library.")
                if (
                    child
                    and not item.get("catalogue_id")
                    and item["id"] not in {r["id"] for r in [*profile["favorites"], *profile["recent"], *profile["books"].values(), *shared]}
                ):
                    raise PermissionError("Choose permitted listening content.")
                if action == "delay":
                    if type(body.get("value")) is not int or body["value"] not in {300, 600, 900}:
                        raise ValueError("Choose a supported delay.")
                    profile["delayed"] = {"at": time.time() + body["value"], "item": item, "player": player["entity_id"], "surface": surface_id, "user": user}
                    self.save(data)
                    return
                await self.play(endpoint, connection, data, profile, scope, player, item, user, surface_id)
            elif action == "sleep":
                if type(body.get("value")) is not int or body["value"] not in {0, 900, 1800, 3600}:
                    raise ValueError("Choose a supported sleep timer.")
                if not lease or lease["scope"] != scope:
                    raise ValueError("Start your listening session before setting its timer.")
                lease.setdefault("session", secrets.token_hex(12))
                profile["sleep"] = {"at": time.time() + body["value"], "player_id": pid, "session": lease["session"]} if body["value"] else None
            else:
                if action != "volume" and (not lease or lease["scope"] != scope):
                    raise ValueError("This speaker is playing another listening session. Choose your content first.")
                if lease:
                    await self.sample(endpoint, connection, data, pid, lease)
                    if action != "volume" and pid not in data["leases"]:
                        self.save(data)
                        raise ValueError("The speaker session changed. Choose your content again.")
                if action == "volume":
                    if not number(body.get("value")) or not 0 <= body["value"] <= 100:
                        raise ValueError("Choose a speaker volume from 0 to 100.")
                    await self.runtime.control(endpoint, connection, "players/cmd/volume_set", player_id=pid, volume_level=round(body["value"]))
                elif action in {"pause", "play", "stop", "next", "previous"}:
                    if action == "pause" or action == "stop" and lease.get("kind") in {"audiobook", "podcast_episode"}:
                        await self.pause_owned(endpoint, connection, data, pid, lease)
                        if action == "stop":
                            if pid not in data["leases"]:
                                self.save(data)
                                raise ValueError("The speaker session changed while pausing. Saved progress was preserved; check the speaker before stopping.")
                            await self.runtime.control(endpoint, connection, "player_queues/stop", queue_id=pid)
                    else:
                        await self.runtime.control(endpoint, connection, "player_queues/" + action, queue_id=pid)
                    if action in {"play", "stop", "next", "previous"}:
                        lease.pop("idle_pause_ack", None)
                else:
                    raise ValueError("Unsupported listening action.")
            profile["destination"] = player["entity_id"]
            self.save(data)

    async def preview_station(self, user, surface_id, person, body):
        """Catalogue latency must not block room controls, timers or progress saves."""
        async with self.lock:
            house, surface, saved, _ = await self.authorize(user, surface_id, person)
            if set(body) - {"epoch", "action", "station", "preview", "player"} or body.get("epoch") != house["epoch"]:
                raise ValueError("Refresh this station view before using it.")
            connection = self.runtime.connection()
            snapshot = await self.runtime.snapshot()
            endpoint = await self.runtime.endpoint()
            if not connection or not snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant in Home Starter.")
            _, child = await self.players(house, surface, saved, person, snapshot)
            bound_access = await catalogue.policy(self.runtime, endpoint, connection, house, person, snapshot.get("providers", []))
            data = self.load(house, connection)
            profile = self.profile(data, person)
            before = digest({k: v for k, v in profile.items() if k.startswith("station_")})
            working = deepcopy(profile)
        await listening_stations.action(self, endpoint, connection, working, body, child, person=person)
        async with self.lock:
            fresh_house, fresh_surface, fresh_saved, _ = await self.authorize(user, surface_id, person)
            current = self.runtime.connection()
            if not current or fresh_house["epoch"] != house["epoch"] or any(current[k] != connection[k] for k in ("server_id", "app", "generation")):
                raise ValueError("The household connection changed. Generate a new preview.")
            _, now_child = await self.players(fresh_house, fresh_surface, fresh_saved, person, snapshot)
            if now_child:
                raise PermissionError("A parent configures station previews.")
            fresh_providers = (await self.runtime.snapshot()).get("providers", [])
            fresh_access = await catalogue.policy(self.runtime, endpoint, current, fresh_house, person, fresh_providers)
            if fresh_access["signature"] != bound_access["signature"]:
                raise PermissionError("Catalogue source assignments changed while searching. Generate a fresh preview.")
            data = self.load(fresh_house, current)
            profile = self.profile(data, person)
            if digest({k: v for k, v in profile.items() if k.startswith("station_")}) != before:
                raise ValueError("Station recipes or feedback changed while searching. Generate a fresh preview; your newer choices were kept.")
            for key in list(profile):
                if key.startswith("station_"):
                    profile.pop(key)
            profile.update({k: v for k, v in working.items() if k.startswith("station_")})
            self.save(data)

    async def book_route(self, endpoint, connection, scope, providers=None):
        house = self.store.load()
        config = household_services.load(self.store, house)
        providers = providers if providers is not None else (await self.runtime.snapshot()).get("providers", [])
        users = await self.runtime.command(endpoint, connection, "auth/users")
        if not isinstance(users, list):
            raise MusicRuntimeError("Your audiobook progress connection needs administrator review. Playback was not started.")
        person = scope.removeprefix("person:") if scope.startswith("person:") else None
        return listening_books.route(house, config, providers, users, person, endpoint.get("version") if isinstance(endpoint, dict) else None)

    async def continuation_supported(self, endpoint, connection, providers, pid, lease):
        if not lease or not lease.get("native_session") or lease.get("kind") != "track":
            return False
        try:
            await self.runtime.account_guard(endpoint, connection)
            status = await self.runtime.command(endpoint, connection, "homestarter/media_status")
            selected = next((s.get("provider") for s in status.get("sessions", []) if s.get("queue") == pid), None)
            return any(
                p["id"] == selected and p.get("domain") == "spotify" and household_music.connected(p) and "similar_tracks" in p.get("features", [])
                for p in providers
            )
        except (MusicRuntimeError, ValueError, AttributeError):
            return False

    async def record_access(self, endpoint, connection, item, scope, providers=None):
        if not item.get("catalogue_access"):
            return None
        providers = providers if providers is not None else (await self.runtime.snapshot()).get("providers", [])
        access = await catalogue.policy(
            self.runtime, endpoint, connection, self.store.load(), scope.removeprefix("person:") if scope.startswith("person:") else None, providers
        )
        catalogue.require_record(item, access)
        primary = item["uri"].split("://", 1)[0]
        if primary not in access["sources"] or not any(p["id"] == primary and household_music.connected(p) and p.get("domain") != "spotify" for p in providers):
            raise PermissionError("This catalogue source is unavailable or no longer assigned. Search again.")
        return access

    async def play(self, endpoint, connection, data, profile, scope, player, item, user, surface_id, *, discovery=None):
        pid = player["player_id"]
        sources = set(item.get("sources", [])) | household_music.item_sources(item)
        providers = (await self.runtime.snapshot()).get("providers", [])
        catalogue_access = await self.record_access(endpoint, connection, item, scope, providers)
        progress_route, playback_uri = None, item["uri"]
        bound_books = item["kind"] == "audiobook" and household_services.load(self.store, self.store.load())["libraries"]
        if listening_books.needs_route(item, providers) or bound_books:
            # Resolve before sampling, pausing or replacing any household queue.
            progress_route = await self.book_route(endpoint, connection, scope, providers)
            native = await self.runtime.command(endpoint, connection, "music/item_by_uri", uri=item["uri"])
            if not isinstance(native, dict):
                raise MusicRuntimeError("This audiobook source is unavailable. Choose it again from your library.")
            playback_uri = listening_books.native_uri(native, progress_route)
            item = {**item, "progress_source": True}
        spotify = progress_route is None and bool(sources & ({p["id"] for p in providers if p.get("domain") == "spotify"} | {"spotify"}))
        if spotify:
            await self.runtime.account_guard(endpoint, connection)  # Check before pausing/replacing any existing queue.
            person = scope.removeprefix("person:") if scope.startswith("person:") else None
            listener = next((p["name"] for p in self.store.load()["people"] if p["id"] == person), "House")
            if listener in {"Grant", "Renae"} and listener not in household_music.providers_by_identity(providers):
                raise MusicRuntimeError("Connect Spotify — " + listener + " in household setup before starting personal music.")
        current = await self.runtime.command(endpoint, connection, "players/get", player_id=pid)
        lease = data["leases"].get(pid)
        if lease:
            await self.sample(endpoint, connection, data, pid, lease)
            lease = data["leases"].get(pid)
        target_queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
        if (
            current.get("playback_state", current.get("state")) in {"playing", "paused", "buffering"}
            or (target_queue or {}).get("state") in {"playing", "paused", "buffering"}
            or lease
            and lease["scope"] != scope
        ) and (not lease or lease["scope"] != scope):
            raise ValueError("This speaker is already in use. Join listening or choose another speaker; its queue was kept.")
        for old_pid, old in list(data["leases"].items()):
            if old["scope"] == scope:
                await self.sample(endpoint, connection, data, old_pid, old)
                if old_pid != pid and old_pid in data["leases"]:
                    await self.runtime.control(endpoint, connection, "player_queues/pause", queue_id=old_pid)
                if discovery is None:
                    data["leases"].pop(old_pid, None)
        self.save(data)  # retain the final raw sample before any queue replacement
        previous_queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
        previous_item = ((previous_queue or {}).get("current_item") or {}).get("queue_item_id")
        if discovery is not None:
            result = await self.runtime.control(
                endpoint,
                connection,
                "homestarter/media_play",
                queue_id=pid,
                listener=listener,
                options=discovery,
                expected_session=lease.get("native_session") if lease else None,
                expected_item=lease["queue_item_id"] if lease else None,
                idle_only=lease is None,
            )
            item = media_record(result.get("item"))
            if not item:
                raise MusicRuntimeError("Spotify discovery returned no playable track.")
            # Public catalogue discovery is independent of whichever account
            # supplied overflow. It must not become a Grant browsing source.
            item["sources"] = ["spotify_catalogue"]
            self.catalog[item["id"]] = item
        elif spotify:
            await self.runtime.control(endpoint, connection, "homestarter/play", queue_id=pid, media=item["uri"], listener=listener)
        else:
            await self.runtime.control(
                endpoint,
                connection,
                "player_queues/play_media",
                queue_id=pid,
                media=playback_uri,
                option="replace",
                start_from_beginning=progress_route is None,
                **(
                    {"user": {"provider": "builtin", "user_id": (progress_route or catalogue_access)["user_id"], "required": True}}
                    if progress_route or catalogue_access
                    else {}
                ),
            )
        if item.get("category") == "ambient" and item["kind"] == "sound_effect":
            await self.runtime.control(endpoint, connection, "player_queues/repeat", queue_id=pid, repeat_mode="one")
        elif lease and lease.get("item", {}).get("category") == "ambient" and lease["kind"] == "sound_effect":
            await self.runtime.control(endpoint, connection, "player_queues/repeat", queue_id=pid, repeat_mode="off")
        queue = None
        for _ in range(15):
            queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
            feedback = await self.runtime.command(endpoint, connection, "players/get", player_id=pid)
            if (
                queue
                and queue.get("active")
                and queue.get("state") == "playing"
                and queue.get("current_item", {}).get("queue_item_id")
                and (
                    queue["current_item"]["queue_item_id"] != previous_item
                    or item["kind"] in {"audiobook", "podcast_episode"}
                    and (
                        listening_books.confirms(queue["current_item"].get("media_item") or {}, playback_uri)
                        if progress_route
                        else (queue["current_item"].get("media_item") or {}).get("uri") == item["uri"]
                    )
                )
                and feedback.get("playback_state", feedback.get("state")) == "playing"
                and feedback.get("active_source") == pid
                and (feedback.get("current_media") or {}).get("queue_item_id") == queue["current_item"]["queue_item_id"]
            ):
                break
            await asyncio.sleep(0.5)
        else:
            raise MusicRuntimeError("Playback was requested but not confirmed. Check the speaker before retrying.")
        if item["kind"] in {"audiobook", "podcast_episode"}:
            confirmed = queue["current_item"].get("media_item") or {}
            if not (listening_books.confirms(confirmed, playback_uri) if progress_route else confirmed.get("uri") == item["uri"]):
                raise MusicRuntimeError("The speaker queue changed. Listening progress was not assigned.")
            # A native progress provider fetches the selected listener's position
            # under MA's required user context. Never overwrite it with local UI
            # history from an earlier provider/session.
            position = feedback.get("elapsed_time", 0) if progress_route else profile["books"].get(item["id"], {}).get("position", 0)
            if progress_route and (not number(position) or position < 0):
                raise MusicRuntimeError("Your audiobook position was not confirmed. Saved progress was preserved; check the speaker.")
            # MA's start_from_beginning already owns zero. A redundant zero seek
            # restarts Cast playback and can report idle between loads.
            if progress_route is None and (
                position or queue["current_item"]["queue_item_id"] == previous_item or not number(feedback.get("elapsed_time")) or feedback["elapsed_time"] > 20
            ):
                expected_item = queue["current_item"]["queue_item_id"]
                seek_started = time.time()
                await self.runtime.control(endpoint, connection, "player_queues/seek", queue_id=pid, position=int(position))
                for _ in range(15):
                    feedback = await self.runtime.command(endpoint, connection, "players/get", player_id=pid)
                    checked = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
                    if (
                        checked
                        and checked.get("active")
                        and checked.get("queue_id") == pid
                        and (checked.get("current_item") or {}).get("queue_item_id") == expected_item
                        and feedback.get("playback_state", feedback.get("state")) == "playing"
                        and feedback.get("active_source") == pid
                        and (feedback.get("current_media") or {}).get("queue_item_id") == expected_item
                        and number(feedback.get("elapsed_time"))
                        and number(feedback.get("elapsed_time_last_updated"))
                        and feedback["elapsed_time_last_updated"] >= seek_started
                        and number(checked.get("elapsed_time"))
                        and number(checked.get("elapsed_time_last_updated"))
                        and checked["elapsed_time_last_updated"] >= seek_started
                        and abs(checked["elapsed_time"] - position) <= 3
                    ):
                        break
                    await asyncio.sleep(0.5)
                else:
                    raise MusicRuntimeError("Your saved position was requested but not confirmed. Progress was preserved; check the speaker before retrying.")
                queue = checked
        # Catalogue failure may leave the original native queue playing. Keep
        # its controls/retry ownership until a replacement is actually confirmed.
        for old_pid, old in list(data["leases"].items()):
            if old_pid != pid and old["scope"] == scope:
                data["leases"].pop(old_pid, None)
        data["leases"][pid] = {
            "scope": scope,
            "item": item,
            "kind": item["kind"],
            "queue_item_id": queue["current_item"]["queue_item_id"],
            "generation": connection["generation"],
            "last_sample": time.time(),
            "user": user,
            "surface": surface_id,
            "session": secrets.token_hex(12),
        }
        if progress_route:
            data["leases"][pid].update(progress_route=progress_route, progress_uri=playback_uri)
        if spotify:
            context = await self.runtime.command(endpoint, connection, "homestarter/queue_context", queue_id=pid)
            if context.get("item") != queue["current_item"]["queue_item_id"] or not context.get("session"):
                raise MusicRuntimeError("The music session could not be confirmed. Check the speaker.")
            data["leases"][pid].update(native_session=context["session"], logical_session=context.get("logical_session"))
        if item["kind"] not in {"audiobook", "podcast_episode"}:
            queued = await self.runtime.command(endpoint, connection, "player_queues/items", queue_id=pid, limit=500)
            if not isinstance(queued, list):
                raise MusicRuntimeError("Playback queue could not be confirmed.")
            data["leases"][pid]["queue_items"] = [q["queue_item_id"] for q in queued if isinstance(q, dict) and q.get("queue_item_id")]
        if item["kind"] in {"audiobook", "podcast_episode"}:
            data["leases"][pid]["awaiting_position"] = position
            if number(queue.get("elapsed_time")) and number(feedback.get("elapsed_time")):
                difference = queue["elapsed_time"] - feedback["elapsed_time"]
                data["leases"][pid]["position_offset"] = position if abs(difference - position) < abs(difference) else 0
        profile["recent"] = [item, *[r for r in profile["recent"] if r["id"] != item["id"]]][:30]
        profile.pop("delayed", None)
        self.save(data)

    async def tick(self):
        # Timers and progress survive browser closure; expired permissions never play.
        connection = self.runtime.connection()
        if not connection:
            return
        async with self.lock:
            house = self.store.load()
            data = self.load(house, connection)
            if not data["leases"] and not any(p.get("delayed") for p in data["profiles"].values()):
                return
            endpoint = await self.runtime.endpoint()
            snapshot = await self.runtime.snapshot()
            for scope in {r["scope"] for r in data.get("handoffs", {}).values()}:
                record = next(r for r in data["handoffs"].values() if r["scope"] == scope)
                owner = record["lease"]
                person = scope[7:] if scope.startswith("person:") else None
                try:
                    current_house, surface, saved, _ = await self.authorize(owner.get("user"), owner.get("surface"), person)
                    permitted, _ = await self.players(current_house, surface, saved, person, snapshot)
                    await self.transfers.reconcile(endpoint, connection, data, scope, permitted)
                except (ValueError, PermissionError, MusicRuntimeError):
                    pass
            for pid, lease in list(data["leases"].items()):
                person = lease["scope"][7:] if lease["scope"].startswith("person:") else None
                try:
                    current_house, surface, saved, _ = await self.authorize(lease.get("user"), lease.get("surface"), person)
                    permitted, _ = await self.players(current_house, surface, saved, person, snapshot)
                    if not any(p["player_id"] == pid and p["available"] and p["single"] for p in permitted):
                        raise PermissionError("Speaker permission changed.")
                except (ValueError, PermissionError):
                    data["leases"].pop(pid, None)
                    continue
                await self.sample(endpoint, connection, data, pid, lease)
            for scope, profile in data["profiles"].items():
                timer = profile.get("sleep")
                if timer and timer["at"] <= time.time() and not listening_transfer.pending(data, timer["player_id"]):
                    lease = data["leases"].get(timer["player_id"])
                    if lease and lease["scope"] == scope and lease.get("session") == timer.get("session") and timer.get("session"):
                        await self.pause_owned(endpoint, connection, data, timer["player_id"], lease)
                    profile.pop("sleep", None)
            self.save(data)
            due = [(scope, p["delayed"]) for scope, p in data["profiles"].items() if p.get("delayed", {}).get("at", float("inf")) <= time.time()]
        for scope, job in due:
            person = scope[7:] if scope.startswith("person:") else None
            try:
                self.catalog[job["item"]["id"]] = job["item"]
                await self.action(
                    job["user"],
                    job["surface"],
                    person,
                    {"epoch": house["epoch"], "action": "play_item", "player": job["player"], "item": job["item"]["id"]},
                    expected_job=job,
                )
            except (ValueError, PermissionError, MusicRuntimeError):
                async with self.lock:
                    data = self.load(self.store.load(), connection)
                    profile = self.profile(data, person)
                    if profile.get("delayed") == job:
                        profile.pop("delayed", None)
                    self.save(data)
