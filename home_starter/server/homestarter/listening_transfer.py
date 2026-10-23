"""Deliberate finite-queue handoff using MA mechanics, with durable reconciliation.

Native transfer does not copy userid or guarded account leases. Those sources are
unavailable here. A separately reviewed pinned bridge must preserve native userid around MA transfer.
Native clients do not participate in the service lock: checks
are optimistic, not an atomic cross-client compare-and-swap guarantee.
"""

import secrets
import time
from copy import deepcopy

from . import household_music
from .music_runtime import MusicRuntimeError, digest, number

UNKNOWN = (
    "The move is not confirmed. Check both speakers, then check the move again. It will not be replayed automatically. Any sleep timer waits for verification."
)
CHANGED = "A speaker or queue changed. Review the move again."


def pending(data, pid):
    return any(pid in (r["source"], r["target"]) for r in data.get("handoffs", {}).values())


def identities(rows):
    return [
        (r.get("queue_item_id"), media.get("uri"), media.get("provider"))
        for r in rows
        for media in [r.get("media_item") if isinstance(r.get("media_item"), dict) else {}]
    ]


def fingerprint(value):
    p, q = value["player"], value["queue"]
    return digest(
        [
            value["userid"],
            value["native_revision"],
            p.get("available"),
            p.get("playback_state"),
            p.get("active_source"),
            p.get("synced_to"),
            p.get("active_group"),
            p.get("group_members"),
            q.get("state"),
            q.get("active"),
            q.get("current_index"),
            (q.get("current_item") or {}).get("queue_item_id"),
            q.get("shuffle_enabled"),
            q.get("repeat_mode"),
            q.get("autoplay_enabled"),
            q.get("is_dynamic"),
            identities(value["rows"]),
        ]
    )


class Transfers:
    def __init__(self, listening):
        self.listening = listening

    async def capability(self):
        try:
            value = await self.listening.runtime.command(
                await self.listening.runtime.endpoint(), self.listening.runtime.connection(), "homestarter/transfer_status"
            )
            if (
                isinstance(value, dict)
                and value.get("protocol") == 1
                and value.get("version") == "2.10.7"
                and value.get("pinned") is True
                and value.get("native_user_preserved") is True
            ):
                return None
        except (MusicRuntimeError, ValueError, KeyError, TypeError):
            pass
        return "Moving audio is not available yet. Keep listening here or choose another source."

    @staticmethod
    def issue(endpoint, lease, players):
        if not isinstance(endpoint, dict) or endpoint.get("version") != "2.10.7":
            return "Moving audio needs a reviewed Music Assistant version."
        if not lease or lease.get("kind") not in {"track", "radio", "sound_effect"}:
            return "Moving audiobooks and podcasts is unavailable until native progress ownership can be preserved."
        if lease.get("native_session") or lease.get("progress_route") or lease.get("item", {}).get("catalogue_access"):
            return "Moving this account-scoped session is not supported yet. Its account and progress will stay untouched."
        if any(not p.get("single") or not p.get("available") or "play_media" not in p.get("features", []) for p in players):
            return "Choose two available, supported single speakers. Groups cannot be moved here."
        return None

    async def read(self, endpoint, connection, pid):
        if not isinstance(endpoint, dict) or endpoint.get("version") != "2.10.7":
            raise MusicRuntimeError("Moving audio needs a reviewed Music Assistant version.")
        value = await self.listening.runtime.command(endpoint, connection, "homestarter/transfer_snapshot", queue_id=pid)
        if not isinstance(value, dict) or value.get("protocol") != 1 or "userid" not in value or not isinstance(value.get("revision"), str):
            raise MusicRuntimeError("Moving audio needs a verified native queue-owner connection.")
        p, q, rows = value.get("player"), value.get("queue"), value.get("rows")
        if not isinstance(p, dict) or not isinstance(q, dict) or not isinstance(rows, list) or len(rows) >= 500 or any(not isinstance(r, dict) for r in rows):
            raise MusicRuntimeError("This queue cannot be checked safely. Choose another speaker.")
        return {"player": p, "queue": q, "rows": rows, "userid": value["userid"], "native_revision": value["revision"]}

    @staticmethod
    def single(value, pid):
        p, q = value["player"], value["queue"]
        return (
            p.get("available") is True
            and q.get("queue_id") == pid
            and p.get("type") == "player"
            and not p.get("synced_to")
            and not p.get("active_group")
            and not (set(p.get("group_members") or []) - {pid})
            and not (set(p.get("static_group_members") or []) - {pid})
        )

    @staticmethod
    def empty(value, pid):
        p, q = value["player"], value["queue"]
        return (
            p.get("playback_state") == "idle"
            and p.get("active_source") in (None, pid)
            and q.get("state") == "idle"
            and not q.get("current_item")
            and not value["rows"]
        )

    async def check(self, endpoint, connection, data, scope, source, target, providers):
        sid, tid = source["player_id"], target["player_id"]
        lease = data["leases"].get(sid)
        if sid == tid or not lease or lease.get("scope") != scope or not lease.get("session"):
            raise PermissionError("Only this session's owner can move it to another speaker.")
        if pending(data, sid) or pending(data, tid):
            raise ValueError(UNKNOWN)
        if issue := await self.capability() or self.issue(endpoint, lease, [source, target]):
            raise ValueError(issue)
        if tid in data["leases"]:
            raise ValueError("That speaker belongs to a listening session. Join it or choose an empty speaker.")
        await self.listening.sample(endpoint, connection, data, sid, lease)
        if data["leases"].get(sid) is not lease:
            raise ValueError(CHANGED)
        a, b = await self.read(endpoint, connection, sid), await self.read(endpoint, connection, tid)
        if not self.single(a, sid) or not self.single(b, tid):
            raise ValueError("A speaker disconnected or joined a group. Choose two available single speakers.")
        if not self.empty(b, tid):
            raise ValueError("That speaker is playing or has a saved queue. Choose an empty speaker.")
        q, p = a["queue"], a["player"]
        if not isinstance(a["userid"], str) or not a["userid"]:
            raise ValueError("This session has no verified native owner. Choose supported audio before moving it.")
        if q.get("state") not in {"playing", "paused"} or q["state"] != p.get("playback_state") or p.get("active_source") != sid or q.get("active") is not True:
            raise ValueError("Wait for this queue to settle before moving it.")
        if q.get("is_dynamic") is not False or q.get("autoplay_enabled") is not False:
            raise ValueError("Evolving stations cannot be moved until their native source ownership is supported.")
        ids = [r.get("queue_item_id") for r in a["rows"]]
        if (
            not ids
            or any(not isinstance(i, str) or not i for i in ids)
            or len(set(ids)) != len(ids)
            or (q.get("current_item") or {}).get("queue_item_id") != lease.get("queue_item_id")
        ):
            raise ValueError(CHANGED)
        forbidden = {"spotify", *household_music.PROGRESS_DOMAINS}
        safe = {p["id"] for p in providers if p.get("domain") not in forbidden and household_music.connected(p)}
        bad = forbidden | {p["id"] for p in providers if p.get("domain") in forbidden}
        if household_music.item_sources(lease.get("item", {})) & bad:
            raise ValueError("This account-scoped source cannot be moved safely yet.")
        for row in a["rows"]:
            media = row.get("media_item")
            if not isinstance(media, dict):
                raise ValueError("This queue has unavailable item metadata. Refresh before moving it.")
            sources = household_music.item_sources(media)
            if media.get("media_type") not in {"track", "radio", "sound_effect"} or not sources & safe or sources & bad:
                raise ValueError("This queue includes an account or progress source that cannot be moved safely yet.")
        if lease["kind"] == "track" and not number(q.get("resume_pos") if q["state"] == "paused" else p.get("elapsed_time")):
            raise ValueError("The current position is unavailable. Wait before moving this track.")
        return lease, a, b

    def commit(self, data, record):
        sid, tid, lease = record["source"], record["target"], deepcopy(record["lease"])
        if data["leases"].get(sid, {}).get("session") != lease["session"] or tid in data["leases"]:
            return False
        if record["state"] == "paused":
            lease["transfer_staged"] = {"items": record["items"], "current": lease["queue_item_id"], "userid": record["userid"]}
        lease["queue_items"] = [r[0] for r in record["items"]]
        data["leases"].pop(sid)
        data["leases"][tid] = lease
        profile = data["profiles"][record["scope"]]
        timer = profile.get("sleep") or {}
        if timer.get("player_id") == sid and timer.get("session") == lease["session"]:
            timer["player_id"] = tid
        profile["destination"] = record["target_entity"]
        profile["transfer_notice"] = "Queue moved. The listening owner and any sleep deadline stayed the same."
        return True

    async def reconcile(self, endpoint, connection, data, scope, players):
        if not data.get("handoffs") or await self.capability():
            return
        permitted = {p["player_id"] for p in players}
        for key, record in list(data.get("handoffs", {}).items()):
            if record["scope"] != scope or not {record["source"], record["target"]} <= permitted:
                continue
            if record["generation"] != connection["generation"]:
                continue  # A reconnect is not evidence that an old command did not execute.
            try:
                a = await self.read(endpoint, connection, record["source"])
                b = await self.read(endpoint, connection, record["target"])
            except (MusicRuntimeError, ValueError):
                continue
            q, p = b["queue"], b["player"]
            expected_state = "idle" if record["state"] == "paused" else "playing"
            complete = (
                self.single(a, record["source"])
                and self.single(b, record["target"])
                and self.empty(a, record["source"])
                and identities(b["rows"]) == [tuple(v) for v in record["items"]]
                and (q.get("current_item") or {}).get("queue_item_id") == record["lease"]["queue_item_id"]
                and q.get("state") == expected_state
                and p.get("playback_state") == expected_state
                and (expected_state == "idle" or p.get("active_source") == record["target"])
                and b["userid"] == record["userid"]
                and q.get("autoplay_enabled") is False
                and q.get("is_dynamic") is False
                and (
                    record.get("position") is None
                    or number(position := q.get("resume_pos") if record["state"] == "paused" else p.get("elapsed_time"))
                    and record["position"] - 2 <= position <= record["position"] + (0 if record["state"] == "paused" else time.time() - record["created"]) + 5
                )
                and q.get("shuffle_enabled") == record["shuffle"]
                and q.get("repeat_mode") == record["repeat"]
            )
            if complete and self.commit(data, record):
                data["handoffs"].pop(key)
            elif record.get("acknowledged") and fingerprint(a) == record["source_revision"] and self.empty(b, record["target"]):
                data["profiles"][scope]["transfer_notice"] = "The move did not complete. Audio remains on the original speaker. Review before trying again."
                data["handoffs"].pop(key)
        self.listening.save(data)

    async def staged(self, endpoint, connection, data, pid, lease):
        try:
            value = await self.read(endpoint, connection, pid)
            proof = lease["transfer_staged"]
            valid = (
                self.single(value, pid)
                and value["player"].get("playback_state") == "idle"
                and value["player"].get("active_source") in (None, pid)
                and value["queue"].get("state") == "idle"
                and identities(value["rows"]) == [tuple(v) for v in proof["items"]]
                and (value["queue"].get("current_item") or {}).get("queue_item_id") == proof["current"]
                and value["userid"] == proof["userid"]
            )
        except (MusicRuntimeError, ValueError, KeyError, TypeError):
            valid = False
        if not valid:
            data["leases"].pop(pid, None)
        return False  # Ownership proof, never fabricated listening progress.

    async def action(self, endpoint, connection, data, profile, scope, players, providers, body):
        action = body["action"]
        if action == "transfer_cancel":
            profile.pop("transfer_plan", None)
            return
        if action == "transfer_recheck":
            await self.reconcile(endpoint, connection, data, scope, players)
            return
        plan = profile.get("transfer_plan") or {}
        target_entity = body.get("target") if action == "transfer_prepare" else plan.get("target_entity")
        source = next((p for p in players if p["entity_id"] == body.get("player")), None)
        target = next((p for p in players if p["entity_id"] == target_entity), None)
        if not source or not target:
            raise ValueError("Choose two permitted speakers for this move.")
        lease, a, b = await self.check(endpoint, connection, data, scope, source, target, providers)
        revision = digest([connection["generation"], lease["scope"], lease["session"], fingerprint(a), fingerprint(b)])
        if action == "transfer_prepare":
            profile["transfer_plan"] = {
                "source_entity": source["entity_id"],
                "source_name": source["name"],
                "target_entity": target_entity,
                "target_name": target["name"],
                "revision": revision,
                "confirmation": secrets.token_hex(16),
                "expires": time.time() + 30,
            }
            return
        if (
            action != "transfer_confirm"
            or plan.get("source_entity") != source["entity_id"]
            or plan.get("revision") != revision
            or plan.get("expires", 0) < time.time()
            or not plan.get("confirmation")
            or body.get("confirmation") != plan["confirmation"]
        ):
            raise ValueError(CHANGED)
        profile.pop("transfer_plan", None)
        record = {
            "scope": scope,
            "generation": connection["generation"],
            "source": source["player_id"],
            "target": target["player_id"],
            "target_entity": target["entity_id"],
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
        data.setdefault("handoffs", {})[plan["confirmation"]] = record
        self.listening.save(data)  # Durable intent precedes the one native command.
        try:
            await self.listening.runtime.control(
                endpoint,
                connection,
                "homestarter/transfer",
                source_queue_id=record["source"],
                target_queue_id=record["target"],
                auto_play=record["state"] == "playing",
                source_revision=a["native_revision"],
                target_revision=b["native_revision"],
                request_id=plan["confirmation"],
            )
            record["acknowledged"] = True
            self.listening.save(data)
        except (MusicRuntimeError, TimeoutError, OSError):
            pass  # May already have executed: inspect, never resend or roll back.
        await self.reconcile(endpoint, connection, data, scope, players)
        if pending(data, record["source"]):
            profile["transfer_notice"] = UNKNOWN

    async def model(self, endpoint, data, profile, scope, players, *, source_pid=None):
        record = next((r for r in data.get("handoffs", {}).values() if r["scope"] == scope), None)
        source = next(
            (p for p in players if data["leases"].get(p["player_id"], {}).get("scope") == scope and (source_pid is None or p["player_id"] == source_pid)), None
        )
        lease = data["leases"].get(source["player_id"], {}) if source else None
        issue = (await self.capability() or self.issue(endpoint, lease, [source])) if source else None
        return {
            "source_entity": source["entity_id"] if source else None,
            "source_name": source["name"] if source else None,
            "issue": issue,
            "pending": bool(record),
            "notice": UNKNOWN if record else profile.get("transfer_notice"),
            "targets": [
                {"entity_id": p["entity_id"], "name": p["name"]}
                for p in players
                if source and p["player_id"] != source["player_id"] and p.get("available") and p.get("single") and "play_media" in p.get("features", [])
            ]
            if not issue and not record
            else [],
            "plan": {k: v for k, v in profile.get("transfer_plan", {}).items() if k != "revision"}
            if profile.get("transfer_plan", {}).get("expires", 0) > time.time()
            else None,
        }
