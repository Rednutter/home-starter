"""Reviewed finite-queue group moves. No native bridge or enforcement changes.

Each native mutation has durable intent. Reconciliation never advances phases or
replays commands. Native clients remain outside this service's optimistic lock.
"""

import asyncio
import secrets
import time
from copy import deepcopy

from .listening_groups import lease_identity, members
from .listening_transfer import CHANGED, fingerprint, identities
from .music_runtime import MusicRuntimeError, digest

ACTIONS = {"group_transfer_prepare", "group_transfer_confirm", "group_transfer_cancel", "group_transfer_recheck"}
UNKNOWN = "The group move is not confirmed. Check its current state; no move or grouping command will be retried automatically."


class GroupTransfers:
    def __init__(self, listening):
        self.listening = listening

    async def authority(self, user, surface, person, house, connection):
        current, screen, saved, _ = await self.listening.authorize(user, surface, person)
        if current != house or self.listening.runtime.connection() != connection:
            raise PermissionError("The household connection changed. Review the move again.")
        players, child = await self.listening.players(current, screen, saved, person, await self.listening.runtime.snapshot())
        if child:
            raise PermissionError("A parent must move a session between speaker groups.")
        return players

    async def owner_access(self, endpoint, connection, userid, involved):
        users = await self.listening.runtime.command(endpoint, connection, "auth/users")
        user = next((u for u in users if isinstance(u, dict) and u.get("user_id") == userid), None) if isinstance(users, list) else None
        allowed = user.get("player_filter") if user else None
        if (
            not user
            or user.get("enabled") is not True
            or not isinstance(allowed, list)
            or any(not isinstance(pid, str) for pid in allowed)
            or allowed
            and not set(involved) <= set(allowed)
        ):
            raise PermissionError("The listening owner's native speaker permissions do not cover this move. No permissions will be expanded.")

    async def destinations(self, endpoint, connection, players, desired, target):
        permitted = {p["player_id"]: p for p in players if p["available"]}
        if target not in desired or not 1 <= len(desired) <= 12 or not set(desired) <= permitted.keys():
            raise ValueError("Choose available permitted destination speakers and keep their leader selected.")
        values = {}
        for pid in desired:
            value = await self.listening.transfers.read(endpoint, connection, pid)
            if not self.listening.transfers.single(value, pid) or not self.listening.transfers.empty(value, pid):
                raise ValueError(
                    "A destination is occupied or has a saved queue. This native move cannot replace it safely, even with confirmation; choose empty speakers."
                )
            raw = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            if len(desired) > 1 and (set(desired) - {pid} - set(raw.get("can_group_with", []))):
                raise ValueError("These destination speakers do not advertise compatible native synchronisation.")
            if pid == target and len(desired) > 1 and "set_members" not in raw.get("supported_features", []):
                raise ValueError("The destination leader cannot manage synchronised members.")
            values[pid] = value
        return values

    async def review(self, endpoint, connection, data, scope, players, source, target, desired, providers):
        sid, tid = source["player_id"], target["player_id"]
        group = data.get("groups", {}).get(sid)
        if not group or set(group["members"]) & set(desired):
            raise ValueError("Choose a separate empty destination; overlapping or existing native groups are unsupported.")
        involved = set(group["members"]) | set(desired)
        if not involved <= {p["player_id"] for p in players if p["available"]}:
            raise ValueError("A source or destination member is unavailable.")
        if any(involved & set(r["involved"]) for r in data.get("group_changes", {}).values()):
            raise ValueError("Finish the speaker membership review before moving its queue.")
        if any(key != sid and involved & set(r["involved"]) for key, r in data.get("group_handoffs", {}).items()):
            raise ValueError("A selected speaker is part of another pending move.")
        lease, a, _ = await self.listening.transfers.check(endpoint, connection, data, scope, source, target, providers, source_group=group)
        await self.owner_access(endpoint, connection, a["userid"], involved)
        if a["queue"].get("state") != "playing":
            raise ValueError("Paused grouped moves are not supported by this household flow yet. Keep this queue paused or resume it before reviewing a move.")
        if "set_members" not in source.get("features", []):
            raise ValueError("The source leader cannot release its synchronised members.")
        b = await self.destinations(endpoint, connection, players, desired, tid)
        return {
            "before": digest([lease_identity(lease), fingerprint(a), {pid: fingerprint(value) for pid, value in b.items()}]),
            "source_group": deepcopy(group),
            "source": sid,
            "target": tid,
            "source_entity": source["entity_id"],
            "target_entity": target["entity_id"],
            "desired": sorted(desired),
            "involved": sorted(involved),
            "lease": deepcopy(lease),
            "source_value": a,
        }

    async def detached(self, endpoint, connection, record):
        for pid in record["source_group"]["members"]:
            raw = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            if not isinstance(raw, dict) or raw.get("available") is False or raw.get("synced_to") or raw.get("active_group") or members(raw, pid) != {pid}:
                raise MusicRuntimeError(UNKNOWN)
            if pid != record["source"] and raw.get("playback_state", raw.get("state")) != "idle":
                raise MusicRuntimeError("A former group member is still active. The queue move was not requested.")

    async def finish(self, endpoint, connection, data, record, players):
        # Reads only. Never continue from an uncertain dissolve/transfer into a new mutation.
        if (
            record.get("generation") != connection["generation"]
            or not record.get("forming_started")
            or not set(record["involved"]) <= {p["player_id"] for p in players if p["available"]}
        ):
            return False
        sid, tid = record["source"], record["target"]
        lease = data["leases"].get(tid)
        if not lease or lease_identity(lease) != lease_identity(record["lease"]) or sid in data["leases"]:
            return False
        a, b = await self.listening.transfers.read(endpoint, connection, sid), await self.listening.transfers.read(endpoint, connection, tid)
        moved = record["native"]
        await self.owner_access(endpoint, connection, moved["userid"], record["involved"])
        expected = "idle" if moved["state"] == "paused" else "playing"
        q, raw = b["queue"], b["player"]
        position = q.get("resume_pos") if moved["state"] == "paused" else raw.get("elapsed_time")
        from .music_runtime import number

        if (
            not self.listening.transfers.single(a, sid)
            or not self.listening.transfers.empty(a, sid)
            or identities(b["rows"]) != [tuple(v) for v in moved["items"]]
            or b["userid"] != moved["userid"]
            or q.get("state") != expected
            or raw.get("playback_state") != expected
            or q.get("shuffle_enabled") != moved["shuffle"]
            or q.get("repeat_mode") != moved["repeat"]
            or q.get("is_dynamic") is not False
            or q.get("autoplay_enabled") is not False
            or (q.get("current_item") or {}).get("queue_item_id") != lease["queue_item_id"]
            or (
                moved["position"] is not None
                and (not number(position) or not moved["position"] - 2 <= position <= moved["position"] + time.time() - moved["created"] + 5)
            )
        ):
            return False
        for pid in record["involved"]:
            value = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
            if not isinstance(value, dict) or value.get("available") is False:
                return False
            if pid == tid:
                if value.get("synced_to") or members(value, pid) != set(record["desired"]):
                    return False
            elif pid in record["desired"]:
                if value.get("synced_to") != tid and value.get("active_group") != tid:
                    return False
            elif (
                value.get("synced_to") or value.get("active_group") or members(value, pid) != {pid} or value.get("playback_state", value.get("state")) != "idle"
            ):
                return False
        if len(record["desired"]) > 1:
            data.setdefault("groups", {})[tid] = {
                "members": record["desired"],
                "owner": lease["scope"],
                "session": lease["session"],
                "generation": connection["generation"],
            }
        data["group_handoffs"].pop(sid)
        return True

    async def action(self, endpoint, connection, data, house, players, person, body, user, surface):
        from .listening import profile_key

        scope = profile_key(person)
        action = body["action"]
        moves = data.setdefault("group_handoffs", {})
        source = next((p for p in players if p["entity_id"] == body.get("player")), None)
        if not source:
            raise ValueError("Choose a permitted source leader.")
        sid = source["player_id"]
        previous = moves.get(sid)
        if previous and previous["scope"] != scope:
            raise PermissionError("Only the listening owner can confirm this move.")
        if action == "group_transfer_recheck":
            await self.listening.transfers.reconcile(endpoint, connection, data, scope, players)
            if not previous or not await self.finish(endpoint, connection, data, previous, players):
                raise ValueError(UNKNOWN)
            return
        if previous and previous["phase"] != "prepared":
            raise ValueError(UNKNOWN)
        if action == "group_transfer_cancel":
            moves.pop(sid, None)
            return
        players = await self.authority(user, surface, person, house, connection)
        providers = (await self.listening.runtime.snapshot()).get("providers", [])
        target_entity = body.get("target") if action == "group_transfer_prepare" else (previous or {}).get("target_entity")
        target = next((p for p in players if p["entity_id"] == target_entity), None)
        by_entity = {p["entity_id"]: p["player_id"] for p in players}
        selection = (body.get("settings") or {}).get("members") if action == "group_transfer_prepare" else None
        if action == "group_transfer_prepare":
            if not isinstance(selection, list) or any(not isinstance(v, str) or v not in by_entity for v in selection) or len(selection) != len(set(selection)):
                raise ValueError("Choose unique permitted destination speakers.")
            desired = sorted(by_entity[v] for v in selection)
        else:
            desired = (previous or {}).get("desired", [])
        if not target:
            raise ValueError("Choose the destination leader.")
        reviewed = await self.review(endpoint, connection, data, scope, players, source, target, desired, providers)
        if action == "group_transfer_prepare":
            moves[sid] = {
                **reviewed,
                "scope": scope,
                "generation": connection["generation"],
                "confirmation": secrets.token_hex(16),
                "expires": time.time() + 120,
                "phase": "prepared",
            }
            return
        if (
            action != "group_transfer_confirm"
            or not previous
            or previous["confirmation"] != body.get("confirmation")
            or previous["expires"] < time.time()
            or previous["before"] != reviewed["before"]
        ):
            raise ValueError(CHANGED)
        record = previous
        record["phase"] = "dissolving"
        self.listening.save(data)
        try:
            await self.listening.runtime.control(
                endpoint,
                connection,
                "players/cmd/set_members",
                target_player=sid,
                player_ids_to_add=[],
                player_ids_to_remove=[p for p in record["source_group"]["members"] if p != sid],
            )
            await self.detached(endpoint, connection, record)
            data["groups"].pop(sid)
            self.listening.save(data)
            players = await self.authority(user, surface, person, house, connection)
            source = next(p for p in players if p["player_id"] == sid)
            target = next(p for p in players if p["player_id"] == record["target"])
            await self.destinations(endpoint, connection, players, record["desired"], record["target"])
            lease, a, b = await self.listening.transfers.check(endpoint, connection, data, scope, source, target, providers, ignore_pending=True)
            await self.owner_access(endpoint, connection, a["userid"], record["involved"])
            old = record["source_value"]
            if (
                identities(a["rows"]) != identities(old["rows"])
                or a["userid"] != old["userid"]
                or any(
                    a["queue"].get(k) != old["queue"].get(k)
                    for k in ("state", "current_index", "shuffle_enabled", "repeat_mode", "autoplay_enabled", "is_dynamic")
                )
                or lease_identity(lease) != lease_identity(record["lease"])
            ):
                raise MusicRuntimeError(CHANGED)
            native = {
                "scope": scope,
                "generation": connection["generation"],
                "source": sid,
                "target": record["target"],
                "target_entity": record["target_entity"],
                "lease": deepcopy(lease),
                "source_revision": fingerprint(a),
                "userid": a["userid"],
                "items": identities(a["rows"]),
                "state": a["queue"]["state"],
                "shuffle": a["queue"].get("shuffle_enabled"),
                "repeat": a["queue"].get("repeat_mode"),
                "created": time.time(),
                "position": (a["queue"].get("resume_pos") if a["queue"]["state"] == "paused" else a["player"].get("elapsed_time"))
                if lease["kind"] == "track"
                else None,
            }
            record.update(phase="transferring", native=native)
            data.setdefault("handoffs", {})[record["confirmation"]] = native
            self.listening.save(data)
            await self.listening.runtime.control(
                endpoint,
                connection,
                "homestarter/transfer",
                source_queue_id=sid,
                target_queue_id=record["target"],
                auto_play=native["state"] == "playing",
                source_revision=a["native_revision"],
                target_revision=b["native_revision"],
                request_id=record["confirmation"],
            )
            native["acknowledged"] = True
            await self.listening.transfers.reconcile(endpoint, connection, data, scope, players)
            if record["confirmation"] in data["handoffs"]:
                raise MusicRuntimeError(UNKNOWN)
            players = await self.authority(user, surface, person, house, connection)
            await self.owner_access(endpoint, connection, native["userid"], record["involved"])
            # The leader is now occupied by exactly the verified transferred queue.
            for pid in record["desired"]:
                if pid == record["target"]:
                    continue
                value = await self.listening.transfers.read(endpoint, connection, pid)
                if not self.listening.transfers.single(value, pid) or not self.listening.transfers.empty(value, pid):
                    raise MusicRuntimeError("A destination member became occupied. No group join was requested.")
            if not set(record["involved"]) <= {p["player_id"] for p in players if p["available"]}:
                raise MusicRuntimeError("A group member disconnected before the destination could form.")
            for pid in record["desired"]:
                raw = await self.listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
                if len(record["desired"]) > 1 and set(record["desired"]) - {pid} - set(raw.get("can_group_with", [])):
                    raise MusicRuntimeError("Destination synchronisation capabilities changed. No group join was requested.")
            target_now = await self.listening.transfers.read(endpoint, connection, record["target"])
            if (
                target_now["userid"] != native["userid"]
                or identities(target_now["rows"]) != [tuple(v) for v in native["items"]]
                or (target_now["queue"].get("current_item") or {}).get("queue_item_id") != lease["queue_item_id"]
            ):
                raise MusicRuntimeError("The destination queue changed before grouping.")
            record.update(phase="forming", forming_started=True)
            self.listening.save(data)
            if len(record["desired"]) > 1:
                await self.listening.runtime.control(
                    endpoint,
                    connection,
                    "players/cmd/set_members",
                    target_player=record["target"],
                    player_ids_to_add=[p for p in record["desired"] if p != record["target"]],
                    player_ids_to_remove=[],
                )
            if not await self.finish(endpoint, connection, data, record, players):
                raise MusicRuntimeError(UNKNOWN)
        except (MusicRuntimeError, ValueError, PermissionError, TimeoutError, OSError, asyncio.CancelledError):
            if sid in moves:
                record["phase"] = "uncertain"
            raise
        finally:
            self.listening.save(data)

    async def model(self, endpoint, connection, data, scope, players):
        names = {p["player_id"]: p["name"] for p in players}
        move = next((r for r in data.get("group_handoffs", {}).values() if r["scope"] == scope and set(r["involved"]) <= names.keys()), None)
        sources = [p for p in players if p.get("managed_group") and data["leases"].get(p["player_id"], {}).get("scope") == scope]
        if not sources and not move:
            return {"source": None, "issue": None, "pending": None, "targets": []}
        issue = await self.listening.transfers.capability()
        if sources and not issue:
            issue = self.listening.transfers.issue(endpoint, data["leases"].get(sources[0]["player_id"]), [{**sources[0], "single": True}])
        return {
            "source": sources[0]["entity_id"] if sources else (move or {}).get("source_entity"),
            "issue": issue,
            "pending": (
                {
                    "phase": move["phase"],
                    "confirmation": move["confirmation"] if move["phase"] == "prepared" else None,
                    "names": [names[p] for p in move["desired"]],
                }
                if move
                else None
            ),
            "targets": [
                {"entity_id": p["entity_id"], "name": p["name"]}
                for p in players
                if p["available"]
                and p.get("single")
                and not p.get("managed_group")
                and all(p["player_id"] not in data["groups"][s["player_id"]]["members"] for s in sources)
            ]
            if sources and not issue
            else [],
        }
