"""Listener-owned MA control behind authenticated HA ingress; devices remain destinations."""

from __future__ import annotations

import asyncio
import secrets
import time
from pathlib import Path

from . import household_services, readiness, screen_identity
from .music_runtime import MusicRuntimeError, digest, number, private_write


def profile_key(person):
    return "person:" + person if person else "house"


def media_record(value):
    if not isinstance(value, dict):
        return None
    uri = value.get("uri")
    kind = value.get("media_type")
    folder = kind in {"folder", "podcast"}
    path = value.get("path") if kind == "folder" else uri
    if not isinstance(path, str) or not path or len(path) > 2048:
        return None
    return {"id": digest(path)[:24], "title": str(value.get("name") or "Untitled")[:240], "kind": value.get("media_type"), "uri": path, "folder": folder}


class ListeningRuntime:
    def __init__(self, runtime, core, store):
        self.runtime, self.core, self.store = runtime, core, store
        self.path = Path(store.path).parent / "music-listeners.json"
        self.lock = asyncio.Lock()
        self.catalog = {}
        self.mapping_cache = None
        self.regional_cache = None

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
                    "own_room": area in own_rooms,
                }
            )
        return result, child

    async def catalog_items(self, endpoint, connection, folder=None, query=None):
        if query:
            raw = await self.runtime.command(endpoint, connection, "music/search", search_query=query, limit=12)
            values = [v for rows in raw.values() if isinstance(rows, list) for v in rows] if isinstance(raw, dict) else []
        else:
            collection = self.catalog.get(folder, {}) if folder else {}
            path = collection.get("uri") if folder else None
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
                values = await self.runtime.command(
                    endpoint, connection, "music/podcasts/podcast_episodes", item_id=show["item_id"], provider_instance_id_or_domain=show["provider"]
                )
            else:
                values = await self.runtime.command(endpoint, connection, "music/browse", path=path)
        if not isinstance(values, list):
            raise MusicRuntimeError("Music Assistant library could not be read.")
        result = []
        for value in values[:80]:
            if record := media_record(value):
                if record["kind"] not in {"folder", "track", "album", "playlist", "radio", "audiobook", "podcast", "podcast_episode", "sound_effect"}:
                    continue
                self.catalog[record["id"]] = record
                result.append(record)
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
        player = await self.runtime.command(endpoint, connection, "players/get", player_id=player_id)
        queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=player_id)
        item = (queue or {}).get("current_item") or {}
        media = player.get("current_media") or {}
        current_id = item.get("queue_item_id")
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
        lease["pause_requested_at"] = time.time()
        await self.runtime.control(endpoint, connection, "player_queues/pause", queue_id=pid)
        for _ in range(10):
            await self.sample(endpoint, connection, data, pid, lease)
            if pid not in data["leases"] or "pause_requested_at" not in lease:
                break
            await asyncio.sleep(0.25)

    async def view(self, user, surface_id, person=None, folder=None, query=None):
        async with self.lock:
            house, surface, saved, _ = await self.authorize(user, surface_id, person)
            snapshot = await self.runtime.snapshot()
            connection, endpoint = self.runtime.connection(), await self.runtime.endpoint()
            if not connection or not snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant in Home Starter.")
            data = self.load(house, connection)
            profile = self.profile(data, person)
            players, child = await self.players(house, surface, saved, person, snapshot)
            if child and (folder or query):
                raise PermissionError("This view uses its permitted listening choices.")
            library = [] if child else await self.catalog_items(endpoint, connection, folder, query)
            region = household_services.load(self.store, house)["region"]
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
                return {k: r[k] for k in ("id", "title", "kind", "folder") if k in r}

            books = sorted(profile["books"].values(), key=lambda b: b.get("updated_at", 0), reverse=True)
            return {
                "epoch": house["epoch"],
                "person_id": person,
                "players": players,
                "default_destination": default,
                "browse": not child,
                "library": [public(r) for r in library],
                "regional_radio": {"name": region["name"], "items": [public(r) for r in local_radio], "issue": radio_issue}
                if region and not child and not folder and not query
                else None,
                "favorites": [public(r) for r in profile["favorites"]],
                "shared": [public(r) for r in self.profile(data, None)["favorites"]] if person else [],
                "recent": [public(r) for r in profile["recent"]],
                "books": [{**public(r), "position": r["position"], "duration": r["duration"]} for r in books],
                "session": next(
                    ({"player_id": pid, "title": lease["item"]["title"]} for pid, lease in data["leases"].items() if lease["scope"] == profile_key(person)),
                    None,
                ),
                "delayed": {"at": profile["delayed"]["at"], "title": profile["delayed"]["item"]["title"], "item": profile["delayed"]["item"]["id"]}
                if profile.get("delayed")
                else None,
                "sleep": profile.get("sleep"),
            }

    async def action(self, user, surface_id, person, body, *, expected_job=None):
        async with self.lock:
            house, surface, saved, _ = await self.authorize(user, surface_id, person)
            if set(body) - {"epoch", "action", "player", "item", "value"} or body.get("epoch") != house["epoch"]:
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
            action = body.get("action")
            if action == "start_now" or expected_job is not None:
                job = profile.get("delayed")
                if not job:
                    raise ValueError("There is no scheduled listening session.")
                self.catalog[job["item"]["id"]] = job["item"]
                body = {**body, "player": job["player"], "item": job["item"]["id"]}
                action = "play_item"
            if action in {"favorite", "unfavorite"}:
                item = await self.item(body.get("item"), profile, shared)
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
            if action == "destination":
                profile["destination"] = player["entity_id"]
                self.save(data)
                return
            lease = data["leases"].get(pid)
            if action in {"play_item", "resume", "delay"}:
                item = await self.item(body.get("item"), profile, shared)
                if child and item["id"] not in {r["id"] for r in [*profile["favorites"], *profile["recent"], *profile["books"].values(), *shared]}:
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

    async def play(self, endpoint, connection, data, profile, scope, player, item, user, surface_id):
        pid = player["player_id"]
        current = await self.runtime.command(endpoint, connection, "players/get", player_id=pid)
        lease = data["leases"].get(pid)
        if lease:
            await self.sample(endpoint, connection, data, pid, lease)
            lease = data["leases"].get(pid)
        if current.get("playback_state", current.get("state")) == "playing" and (not lease or lease["scope"] != scope):
            raise ValueError("This speaker is already in use. Choose an idle speaker.")
        for old_pid, old in list(data["leases"].items()):
            if old["scope"] == scope:
                await self.sample(endpoint, connection, data, old_pid, old)
                if old_pid != pid and old_pid in data["leases"]:
                    await self.runtime.control(endpoint, connection, "player_queues/pause", queue_id=old_pid)
                data["leases"].pop(old_pid, None)
        self.save(data)  # retain the final raw sample before any queue replacement
        previous_queue = await self.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
        previous_item = ((previous_queue or {}).get("current_item") or {}).get("queue_item_id")
        await self.runtime.control(
            endpoint, connection, "player_queues/play_media", queue_id=pid, media=item["uri"], option="replace", start_from_beginning=True
        )
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
                    and (queue["current_item"].get("media_item") or {}).get("uri") == item["uri"]
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
            if confirmed.get("uri") != item["uri"]:
                raise MusicRuntimeError("The speaker queue changed. Listening progress was not assigned.")
            position = profile["books"].get(item["id"], {}).get("position", 0)
            # MA's start_from_beginning already owns zero. A redundant zero seek
            # restarts Cast playback and can report idle between loads.
            if position or queue["current_item"]["queue_item_id"] == previous_item or not number(feedback.get("elapsed_time")) or feedback["elapsed_time"] > 20:
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
                if timer and timer["at"] <= time.time():
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
