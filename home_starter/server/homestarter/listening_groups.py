"""Temporary native MA sync cohorts. Never create players or independent streams."""

import asyncio
import secrets
import time

from .listening_transfer import pending as transfer_pending
from .music_runtime import MusicRuntimeError, digest

ACTIONS = {"group_prepare", "group_confirm", "group_cancel", "group_recheck"}
BUSY = {"playing", "paused", "buffering"}
UNKNOWN = "Speaker membership is not confirmed. Recheck it; no grouping command will be retried automatically."


def members(raw, pid):
    return {pid, *(raw.get("group_members") or [])}


def pending(data, pid):
    return any(pid in r["involved"] and r["phase"] != "prepared" for r in data.get("group_changes", {}).values()) or any(
        pid in r["involved"] and r["phase"] != "prepared" for r in data.get("group_handoffs", {}).values()
    )


def bound(data, pid, raw):
    record = data.get("groups", {}).get(pid)
    lease = data["leases"].get(pid)
    return bool(
        record
        and lease
        and not pending(data, pid)
        and not raw.get("synced_to")
        and set(record["members"]) == members(raw, pid)
        and record["owner"] == lease["scope"]
        and record["session"] == lease.get("session")
        and record["generation"] == lease.get("generation")
    )


def decorate(data, players):
    allowed = {p["player_id"] for p in players if p["available"]}
    for player in players:
        pid = player["player_id"]
        player["native_single"] = player["single"]
        record = data.get("groups", {}).get(pid)
        if record:
            actual = {pid, *player.get("group_members", [])}
            player["managed_group"] = True
            player["single"] = set(record["members"]) <= allowed and actual == set(record["members"]) and not pending(data, pid)
        for leader, group in data.get("groups", {}).items():
            if pid != leader and pid in group["members"]:
                player["group_parent"] = leader
    return players


def lease_identity(lease):
    return [lease.get(k) for k in ("scope", "session", "generation", "queue_item_id", "native_session", "logical_session", "progress_route")]


class Groups:
    def __init__(self, listening):
        self.listening = listening

    async def verified(self, endpoint, connection, data, leader):
        record = data.get("groups", {}).get(leader)
        if not record:
            return False
        try:
            raw = await asyncio.gather(*(self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid) for pid in record["members"]))
        except MusicRuntimeError:
            return False
        values = dict(zip(record["members"], raw, strict=True))
        return bool(
            all(isinstance(v, dict) and v.get("available") is not False for v in raw)
            and bound(data, leader, values[leader])
            and all(pid == leader or v.get("synced_to") == leader or v.get("active_group") == leader for pid, v in values.items())
        )

    async def inspect(self, endpoint, connection, data, players, leader, desired, *, idle_start=False):
        from .ma_control_contract import supports

        if not supports(endpoint, "groups"):
            raise ValueError("Grouping needs the reviewed Music Assistant 2.10.7 connection.")
        from .ma_control_contract import check_progress_start

        check_progress_start(endpoint, data.get("leases", {}).get(leader, {}).get("kind"))
        permitted = {p["player_id"]: p for p in players if p["available"]}
        old = data.get("groups", {}).get(leader, {})
        involved = set(desired) | set(old.get("members", [leader]))
        if leader not in desired or not 1 <= len(desired) <= 12 or not involved <= permitted.keys():
            raise ValueError("Choose available permitted speakers and keep the current leader selected.")
        raw, queues, identities, occupied = {}, {}, {}, []
        scopes = {"house", *("person:" + p["id"] for p in self.listening.store.load()["people"])}
        for pid in sorted(involved):
            if any(
                key != leader and pid in r["involved"] and (r["phase"] != "prepared" or r["expires"] >= time.time())
                for key, r in data.get("group_changes", {}).items()
            ):
                raise ValueError("A selected room is part of another group review. Finish it first.")
            if transfer_pending(data, pid):
                raise ValueError("Finish the pending playback handoff before changing speakers.")
            raw[pid] = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            queues[pid] = await self.listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
            value = raw[pid]
            if not isinstance(value, dict) or value.get("available") is False or value.get("type") not in (None, "player"):
                raise ValueError("A selected speaker is unavailable or cannot form a temporary sync group.")
            if value.get("synced_to") not in (None, leader) or value.get("active_group") not in (None, leader):
                raise ValueError("A selected speaker belongs to another group. Leave that group first.")
            if pid == leader and value.get("synced_to"):
                raise ValueError("Choose a speaker that is not following another leader.")
            lease = data["leases"].get(pid)
            if lease:
                if lease.get("scope") not in scopes or lease["scope"] not in data["profiles"]:
                    raise ValueError("A selected room's listening profile is no longer mapped.")
                await self.listening.sample(endpoint, connection, data, pid, lease)
                if data["leases"].get(pid) is not lease:
                    raise ValueError("A listening session changed. Review the speaker selection again.")
                identities[pid] = lease_identity(lease)
            if pid != leader and pid not in old.get("members", []) and value.get("playback_state", value.get("state")) in BUSY:
                if not lease:
                    raise ValueError("A selected room has unmanaged playback. Choose another room or stop it in its current app first.")
                occupied.append(pid)
        current = members(raw[leader], leader)
        if leader not in identities and raw[leader].get("playback_state", raw[leader].get("state")) in BUSY:
            raise ValueError("The leader has unmanaged playback. Keep its existing controls or choose another room.")
        if current != set(old.get("members", [leader])):
            raise ValueError("Native group membership changed outside this session. Check it before continuing.")
        if "set_members" not in raw[leader].get("supported_features", []):
            raise ValueError("This leader does not support native synchronised member changes.")
        if len(desired) > 1:
            if leader not in identities and not idle_start:
                raise ValueError("Start a household session on the leader first, then group its speakers.")
            for pid in desired:
                if set(desired) - {pid} - set(raw[pid].get("can_group_with", [])):
                    raise ValueError("These speakers do not advertise compatible native synchronisation.")
        if idle_start and (
            identities
            or old
            or any(value.get("playback_state", value.get("state")) in BUSY or (queues[pid] or {}).get("state") in BUSY for pid, value in raw.items())
        ):
            raise ValueError("Starting on several speakers needs idle rooms without managed sessions. Keep existing audio or choose other rooms.")
        state = [
            [
                pid,
                raw[pid].get("playback_state", raw[pid].get("state")),
                raw[pid].get("active_source"),
                raw[pid].get("synced_to"),
                sorted(members(raw[pid], pid)),
                (queues[pid] or {}).get("queue_id"),
                (queues[pid] or {}).get("state"),
                ((queues[pid] or {}).get("current_item") or {}).get("queue_item_id"),
                identities.get(pid),
                sorted(raw[pid].get("can_group_with", [])),
            ]
            for pid in sorted(involved)
        ]
        return {
            "before": digest([connection["server_id"], connection["app"], connection["generation"], state]),
            "current": sorted(current),
            "involved": sorted(involved),
            "occupied": occupied,
            "identities": identities,
            "leader_state": raw[leader].get("playback_state", raw[leader].get("state")),
            "idle_item": ((queues[leader] or {}).get("current_item") or {}).get("queue_item_id"),
        }

    async def reconcile(self, endpoint, connection, data, players, leader):
        change = data.get("group_changes", {}).get(leader)
        if not change or change["phase"] == "prepared":
            return False
        allowed = {p["player_id"] for p in players if p["available"]}
        if not set(change["involved"]) <= allowed:
            return False
        raw = {pid: await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid) for pid in change["involved"]}
        if not all(isinstance(v, dict) and v.get("available") is not False for v in raw.values()):
            return False
        if change.get("start"):
            return await self.finish_start(endpoint, connection, data, players, leader)
        desired = set(change["desired"])
        if members(raw[leader], leader) != desired or raw[leader].get("synced_to"):
            return False
        if raw[leader].get("playback_state", raw[leader].get("state")) != change["leader_state"]:
            return False
        for pid in change["involved"]:
            if pid == leader:
                continue
            linked = raw[pid].get("synced_to") == leader or raw[pid].get("active_group") == leader
            if linked != (pid in desired):
                return False
        owner = data["leases"].get(leader)
        if change["leader_identity"]:
            if not owner or lease_identity(owner) != change["leader_identity"]:
                return False
            scopes = {"house", *("person:" + p["id"] for p in self.listening.store.load()["people"])}
            if owner["scope"] not in scopes:
                return False
            if owner.get("progress_route") and await self.listening.book_route(endpoint, connection, owner["scope"]) != owner["progress_route"]:
                return False
            if owner.get("item", {}).get("catalogue_access"):
                await self.listening.record_access(endpoint, connection, owner["item"], owner["scope"])
            queue = await self.listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=leader)
            if not queue or queue.get("queue_id") != leader or (queue.get("current_item") or {}).get("queue_item_id") != owner["queue_item_id"]:
                return False
            if raw[leader].get("active_source") != leader or (raw[leader].get("current_media") or {}).get("queue_item_id") != owner["queue_item_id"]:
                return False
            if owner.get("native_session"):
                context = await self.listening.runtime.command(endpoint, connection, "homestarter/queue_context", queue_id=leader)
                if context.get("session") != owner["native_session"] and (
                    not owner.get("logical_session") or context.get("logical_session") != owner["logical_session"]
                ):
                    return False
        if len(desired) > 1:
            data.setdefault("groups", {})[leader] = {
                "members": sorted(desired),
                "owner": owner["scope"],
                "session": owner["session"],
                "generation": connection["generation"],
            }
        else:
            data.setdefault("groups", {}).pop(leader, None)
        for pid in change["occupied"]:
            lease = data["leases"].get(pid)
            if pid in desired and lease and lease_identity(lease) == change["identities"][pid]:
                data["leases"].pop(pid)
        data["group_changes"].pop(leader)
        return True

    def view(self, data, players, scope):
        allowed = {p["player_id"] for p in players}
        result = {"available": any("set_members" in p.get("features", []) for p in players), "groups": [], "pending": None}
        result["reason"] = "Choose media for idle compatible speakers, or keep an existing session leader; review before changing native membership."
        for leader, record in data.get("groups", {}).items():
            if set(record["members"]) <= {p["player_id"] for p in players}:
                result["groups"].append({"leader": leader, "members": record["members"]})
        for leader, change in data.get("group_changes", {}).items():
            if set(change["involved"]) <= allowed and (change["actor"] == scope or change["phase"] != "prepared"):
                names = {p["player_id"]: p["name"] for p in players}
                result["pending"] = {
                    "leader": leader,
                    "phase": change["phase"],
                    "confirmation": change["confirmation"] if change["actor"] == scope and change["phase"] == "prepared" else None,
                    "members": [names.get(p, "Unavailable speaker") for p in change["desired"]],
                    "occupied": [names.get(p, "Unavailable speaker") for p in change["occupied"]],
                    "removed": [names.get(p, "Unavailable speaker") for p in set(change["current"]) - set(change["desired"])],
                    "start": {"title": change["start"]["item"]["title"]} if change.get("start") else None,
                }
        return result

    async def action(self, endpoint, connection, data, house, players, person, body, *, user, surface, child=False):
        from .listening import profile_key

        action, actor = body["action"], profile_key(person)
        leader = next((p["player_id"] for p in players if p["entity_id"] == body.get("player")), None)
        if not leader:
            raise ValueError("Choose a permitted leader speaker.")
        changes = data.setdefault("group_changes", {})
        previous = changes.get(leader)
        if action == "group_recheck":
            if not await self.reconcile(endpoint, connection, data, players, leader):
                raise ValueError(UNKNOWN)
            return
        if previous and previous["phase"] != "prepared":
            raise ValueError(UNKNOWN)
        if action == "group_cancel":
            if previous and previous["actor"] == actor:
                changes.pop(leader)
            return
        if action == "group_prepare":
            if previous and previous["actor"] != actor and previous["expires"] >= time.time():
                raise ValueError("Another profile is reviewing this group. Wait or choose another leader.")
            if any(r["actor"] == actor and key != leader for key, r in changes.items()):
                raise ValueError("Cancel or reconcile your current group review first.")
            selection = (body.get("settings") or {}).get("members")
            by_entity = {p["entity_id"]: p["player_id"] for p in players}
            if not isinstance(selection, list) or any(not isinstance(v, str) or v not in by_entity for v in selection) or len(selection) != len(set(selection)):
                raise ValueError("Choose a unique set of permitted speakers.")
            desired = sorted(by_entity[v] for v in selection)
            start = await self.prepare_start(endpoint, connection, data, house, person, body, child) if body.get("item") else None
            checked = await self.inspect(endpoint, connection, data, players, leader, desired, idle_start=bool(start))
            changes[leader] = {
                **checked,
                "desired": desired,
                **({"start": start} if start else {}),
                "leader_identity": checked["identities"].get(leader),
                "actor": actor,
                "phase": "prepared",
                "expires": time.time() + 120,
                "confirmation": secrets.token_hex(16),
            }
            return
        if (
            action != "group_confirm"
            or not previous
            or previous["actor"] != actor
            or body.get("confirmation") != previous["confirmation"]
            or previous["expires"] < time.time()
        ):
            raise ValueError("Review a fresh speaker-group change before confirming.")
        if previous.get("start"):
            start = await self.prepare_start(
                endpoint, connection, data, house, person, {"item": previous["start"]["item"]["id"], "settings": {"sleep": previous["start"]["sleep"]}}, child
            )
            if start != previous["start"]:
                raise ValueError("The selected content or progress source changed. Review the start again.")
        checked = await self.inspect(endpoint, connection, data, players, leader, previous["desired"], idle_start=bool(previous.get("start")))
        if checked["before"] != previous["before"]:
            raise ValueError("A room changed since the review. Prepare a new speaker selection.")
        if checked["occupied"] and body.get("value") != "replace":
            raise ValueError("Explicitly confirm replacing audio in the occupied speakers.")
        if child and (checked["occupied"] or set(previous["desired"]) - set(previous["current"])):
            raise PermissionError("A parent must confirm adding rooms or replacing another room's session.")
        lease = data["leases"].get(leader)
        if lease and lease.get("native_session"):
            await self.listening.runtime.account_guard(endpoint, connection)
        previous["phase"] = "applying"
        self.listening.save(data)
        try:
            for pid in checked["occupied"]:
                await self.listening.sample(endpoint, connection, data, pid, data["leases"][pid])
                if pid not in data["leases"] or lease_identity(data["leases"][pid]) != checked["identities"][pid]:
                    raise MusicRuntimeError("A selected session changed before it could be paused.")
                await self.listening.pause_owned(endpoint, connection, data, pid, data["leases"][pid])
                if pid not in data["leases"] or lease_identity(data["leases"][pid]) != checked["identities"][pid]:
                    raise MusicRuntimeError("A displaced room changed. Membership was not safely confirmed.")
                self.listening.save(data)
            fresh_house, fresh_surface, saved, _ = await self.listening.authorize(user, surface, person)
            fresh_connection = self.listening.runtime.connection()
            if fresh_house != house or not fresh_connection or any(fresh_connection[k] != connection[k] for k in ("server_id", "app", "generation")):
                raise MusicRuntimeError("The household connection changed. Membership was not confirmed.")
            fresh_players, child_now = await self.listening.players(fresh_house, fresh_surface, saved, person, await self.listening.runtime.snapshot())
            if child_now and (checked["occupied"] or set(previous["desired"]) - set(previous["current"])):
                raise PermissionError("A parent must confirm adding rooms or replacing another room's session.")
            if not set(previous["involved"]) <= {p["player_id"] for p in fresh_players if p["available"]}:
                raise MusicRuntimeError("Speaker access changed. Membership was not confirmed.")
            current = await self.listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=leader)
            if lease and (
                not current or current.get("queue_id") != leader or (current.get("current_item") or {}).get("queue_item_id") != lease.get("queue_item_id")
            ):
                raise MusicRuntimeError("The leader session changed before grouping.")
            if lease:
                if lease.get("progress_route") and await self.listening.book_route(endpoint, connection, lease["scope"]) != lease["progress_route"]:
                    raise MusicRuntimeError("The owner's progress source changed before grouping.")
                if lease.get("item", {}).get("catalogue_access"):
                    await self.listening.record_access(endpoint, connection, lease["item"], lease["scope"])
                if lease.get("native_session"):
                    await self.listening.runtime.account_guard(endpoint, connection)
                    context = await self.listening.runtime.command(endpoint, connection, "homestarter/queue_context", queue_id=leader)
                    if context.get("item") != lease["queue_item_id"] or (
                        context.get("session") != lease["native_session"]
                        and (not lease.get("logical_session") or context.get("logical_session") != lease["logical_session"])
                    ):
                        raise MusicRuntimeError("The protected source session changed before grouping.")
            if previous.get("start"):
                idle = await self.inspect(endpoint, connection, data, fresh_players, leader, previous["desired"], idle_start=True)
                if idle["before"] != previous["before"]:
                    raise MusicRuntimeError("A selected room changed before grouping. Playback was not started.")
            await self.listening.runtime.control(
                endpoint,
                connection,
                "players/cmd/set_members",
                target_player=leader,
                player_ids_to_add=sorted(set(previous["desired"]) - set(previous["current"])),
                player_ids_to_remove=sorted(set(previous["current"]) - set(previous["desired"])),
            )
            if previous.get("start"):
                await self.start_playback(endpoint, connection, data, fresh_house, fresh_players, person, leader, previous, user, surface)
            if not await self.reconcile(endpoint, connection, data, players, leader):
                raise MusicRuntimeError(UNKNOWN)
        except (MusicRuntimeError, ValueError, PermissionError, TimeoutError, OSError, asyncio.CancelledError):
            if leader in changes:
                changes[leader]["phase"] = "uncertain"
            raise
        finally:
            self.listening.save(data)

    async def prepare_start(self, endpoint, connection, data, house, person, body, child):
        from . import household_music, listening_books
        from .listening import profile_key

        scope = profile_key(person)
        profile = self.listening.profile(data, person)
        shared = self.listening.profile(data, None)["favorites"] if person else []
        item = await self.listening.item(body.get("item"), profile, shared)
        from .ma_control_contract import check_progress_start

        check_progress_start(endpoint, item["kind"])
        providers = (await self.listening.runtime.snapshot()).get("providers", [])
        await self.listening.record_access(endpoint, connection, item, scope, providers)
        listener = next((p["name"] for p in house["people"] if p["id"] == person), "House")
        if not household_music.visible(item, listener, providers):
            raise PermissionError("This source is private. Choose from your listening library.")
        if child:
            raise PermissionError("A parent must confirm starting audio in multiple rooms.")
        if item.get("catalogue_id"):
            await self.listening.media.sync()
            row = self.listening.media.item(item["catalogue_id"])
            item = {**item, "uri": row["uri"], "title": row["name"]}
        sources = set(item.get("sources", [])) | household_music.item_sources(item)
        if sources & ({p["id"] for p in providers if p.get("domain") == "spotify"} | {"spotify"}):
            await self.listening.runtime.account_guard(endpoint, connection)
        route = None
        if listening_books.needs_route(item, providers) or item["kind"] == "audiobook":
            # play() repeats the authoritative route resolution before the one native start.
            from . import household_services

            if listening_books.needs_route(item, providers) or household_services.load(self.listening.store, house)["libraries"]:
                route = await self.listening.book_route(endpoint, connection, scope, providers)
        if any(lease["scope"] == scope for lease in data["leases"].values()):
            raise ValueError("This profile already has a session. Keep it or stop it before starting a new group.")
        sleep = (body.get("settings") or {}).get("sleep", 0)
        if type(sleep) is not int or sleep not in {0, 900, 1800, 3600}:
            raise ValueError("Choose a supported sleep timer.")
        return {"scope": scope, "item": item, "sleep": sleep, "confirmed": False, "progress_route": route}

    async def start_idle(self, endpoint, connection, data, leader, change):
        """Check the actual native cohort; this read cannot make an external client atomic."""
        for pid in change["desired"]:
            raw = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            queue = await self.listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
            if (
                not isinstance(raw, dict)
                or raw.get("available") is False
                or raw.get("playback_state", raw.get("state")) in BUSY
                or (queue or {}).get("state") in BUSY
                or pid in data["leases"]
            ):
                raise MusicRuntimeError("A selected room is no longer idle. Playback was not started.")
            if pid == leader:
                if raw.get("synced_to") or members(raw, pid) != set(change["desired"]):
                    raise MusicRuntimeError(UNKNOWN)
                if not queue or queue.get("queue_id") != leader or (queue.get("current_item") or {}).get("queue_item_id") != change["idle_item"]:
                    raise MusicRuntimeError("The leader queue changed. Playback was not started.")
            elif raw.get("synced_to") != leader and raw.get("active_group") != leader:
                raise MusicRuntimeError(UNKNOWN)

    async def start_playback(self, endpoint, connection, data, house, players, person, leader, change, user, surface):
        async def before_start():
            fresh_house, fresh_surface, saved, _ = await self.listening.authorize(user, surface, person)
            current = self.listening.runtime.connection()
            if fresh_house != house or current != connection:
                raise MusicRuntimeError("The household connection changed. Playback was not started.")
            fresh, child = await self.listening.players(fresh_house, fresh_surface, saved, person, await self.listening.runtime.snapshot())
            if child or not set(change["desired"]) <= {p["player_id"] for p in fresh if p["available"]}:
                raise PermissionError("Speaker access changed. Playback was not started.")
            validated = await self.prepare_start(
                endpoint, connection, data, fresh_house, person, {"item": change["start"]["item"]["id"], "settings": {"sleep": change["start"]["sleep"]}}, child
            )
            if validated != change["start"]:
                raise PermissionError("Content access or the progress source changed. Playback was not started.")
            await self.start_idle(endpoint, connection, data, leader, change)
            change["phase"] = "starting"
            self.listening.save(data)  # persisted before the one native start; never retry it

        await before_start()
        start = change["start"]
        player = next(p for p in players if p["player_id"] == leader)
        profile = self.listening.profile(data, person)
        await self.listening.play(endpoint, connection, data, profile, start["scope"], player, start["item"], user, surface, before_start=before_start)
        start["confirmed"] = True
        start["identity"] = lease_identity(data["leases"][leader])
        self.listening.save(data)

    async def finish_start(self, endpoint, connection, data, players, leader):
        change = data["group_changes"][leader]
        start = change["start"]
        lease = data["leases"].get(leader)
        if not start["confirmed"] or not lease or lease_identity(lease) != start.get("identity") or lease["scope"] != start["scope"]:
            return False  # lost acknowledgement cannot safely assign ownership or trigger another start
        if lease.get("progress_route") and await self.listening.book_route(endpoint, connection, lease["scope"]) != lease["progress_route"]:
            return False
        if lease.get("item", {}).get("catalogue_access"):
            await self.listening.record_access(endpoint, connection, lease["item"], lease["scope"])
        if lease.get("native_session"):
            await self.listening.runtime.account_guard(endpoint, connection)
            context = await self.listening.runtime.command(endpoint, connection, "homestarter/queue_context", queue_id=leader)
            if context.get("session") != lease["native_session"] or context.get("item") != lease["queue_item_id"]:
                return False
        for pid in change["desired"]:
            raw = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            if not isinstance(raw, dict) or raw.get("available") is False:
                return False
            if pid == leader:
                queue = await self.listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
                if (
                    members(raw, pid) != set(change["desired"])
                    or raw.get("synced_to")
                    or raw.get("active_source") != leader
                    or (raw.get("current_media") or {}).get("queue_item_id") != lease["queue_item_id"]
                    or not queue
                    or queue.get("queue_id") != leader
                    or (queue.get("current_item") or {}).get("queue_item_id") != lease["queue_item_id"]
                ):
                    return False
            elif raw.get("synced_to") != leader and raw.get("active_group") != leader:
                return False
        data.setdefault("groups", {})[leader] = {
            "members": change["desired"],
            "owner": lease["scope"],
            "session": lease["session"],
            "generation": connection["generation"],
        }
        profile = data["profiles"][lease["scope"]]
        profile["destination"] = next(p["entity_id"] for p in players if p["player_id"] == leader)
        profile["sleep"] = {"at": time.time() + start["sleep"], "player_id": leader, "session": lease["session"]} if start["sleep"] else None
        data["group_changes"].pop(leader)
        return True
