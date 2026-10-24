"""Separate opt-in native finite-queue transfer candidate. Never auto-installed.

Existing administrator scope is required; no account, permission or token is made.
Native player locks cover ordinary playback actions, not every possible external
queue edit. This is not a cross-client transactional guarantee.
"""

import asyncio
import hashlib
import inspect
import json
from contextlib import AsyncExitStack
from pathlib import Path

PINS = {
    "controller.py": "627d157b054d47a4f881f1efdc47f503f7509faa2c53162c12b7a211631b0d4a",
    "queue_loader.py": "5e85bd26aa5d404472e0c20e5ab45c939b4b2bbdcf29cde473096374644d6690",
    "helpers.py": "98ca6e1235eb132ad643fd872695497ae3b5290a2e356c566c18c087be14d000",
    "state.py": "53d9da3ec76dfdc6ce57eee33ae64b5307dde405eb5347ebefa54644e4350a35",
    "../players/controller.py": "6915230db8aae227393be554d0ef36739b8806d1e043e94e4ddc8b5345571fd2",
}
PROTECTED = {"spotify", "audiobookshelf", "audible", "storytel"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class NativeTransfers:
    def __init__(self, mass, *, source_root=None, auth=None, review=None):
        self.mass = mass
        self.review = review
        self.root = source_root or Path(inspect.getsourcefile(type(mass.player_queues))).parent
        self.auth = auth
        self.native_transfer = mass.player_queues.transfer_queue
        self.player_lock = mass.players.get_group_and_player_lock
        self.source_origin_ok = (
            source_root is not None or Path(inspect.getsourcefile(self.native_transfer)).resolve() == (self.root / "controller.py").resolve()
        )

        self.requests = {}
        self.lock = asyncio.Lock()

    def context(self):
        if self.auth is None:
            from music_assistant.controllers.webserver.helpers import auth_middleware

            return auth_middleware
        return self.auth

    async def status(self):
        try:
            reviewed = False
            if self.review is not None:
                from .ma_release_review import ReviewedRelease

                reviewed = type(self.review) is ReviewedRelease and self.review.valid()
            pinned = (
                self.source_origin_ok
                and self.mass.player_queues.transfer_queue == self.native_transfer
                and self.mass.players.get_group_and_player_lock == self.player_lock
                and (
                    reviewed
                    if self.review is not None
                    else self.mass.version == "2.10.7" and all(hashlib.sha256((self.root / p).read_bytes()).hexdigest() == sha for p, sha in PINS.items())
                )
            )
        except (OSError, TypeError):
            pinned = False
        return {"protocol": 1, "version": self.mass.version, "pinned": pinned, "native_user_preserved": pinned, "spotify": False, "progress": False}

    async def snapshot(self, queue_id):
        if not (await self.status())["pinned"]:
            raise ValueError("Native transfer source needs compatibility review.")
        data = self.mass.player_queues.queue_data(queue_id)
        userid = data.userid
        user = await self.mass.webserver.auth.get_user(userid) if userid else None
        if data.userid != userid:
            raise ValueError("Queue owner changed during inspection.")
        player = self.mass.players.get_player(queue_id)
        if player is None or len(data.items) >= 500:
            raise ValueError("Queue is unavailable or too large to inspect safely.")
        p, q = player.state.to_dict(), data.queue.to_dict()
        q["current_item"] = {"queue_item_id": data.queue.current_item.queue_item_id} if data.queue.current_item else None
        reduced = {
            k: p.get(k)
            for k in (
                "player_id",
                "type",
                "available",
                "playback_state",
                "active_source",
                "active_group",
                "synced_to",
                "group_members",
                "static_group_members",
                "elapsed_time",
            )
        }
        queue = {
            k: q.get(k)
            for k in (
                "queue_id",
                "active",
                "state",
                "current_item",
                "current_index",
                "shuffle_enabled",
                "repeat_mode",
                "autoplay_enabled",
                "is_dynamic",
                "elapsed_time",
                "resume_pos",
            )
        }
        rows = []
        for item in data.items:
            media = item.media_item
            if media is None:
                raise ValueError("Queue metadata is unavailable.")
            value = media.to_dict()
            mappings = [{k: m.get(k) for k in ("provider_instance", "provider_domain")} for m in value.get("provider_mappings") or []]
            rows.append(
                {
                    "queue_item_id": item.queue_item_id,
                    "media_item": {
                        "media_type": value.get("media_type"),
                        "provider": value.get("provider"),
                        "uri": digest(value.get("uri")),
                        "provider_mappings": mappings,
                    },
                }
            )
        restrictions = [
            sorted(value) if isinstance(value, (set, list, tuple)) else value
            for k in ("user_id", "enabled", "provider_filter", "player_filter")
            for value in [getattr(user, k, None)]
        ]
        revision = digest(
            [
                userid,
                getattr(data, "session_id", None),
                restrictions,
                {k: v for k, v in reduced.items() if k != "elapsed_time"},
                {k: v for k, v in queue.items() if k not in {"elapsed_time", "resume_pos"}},
                rows,
            ]
        )
        return {"protocol": 1, "userid": userid, "revision": revision, "player": reduced, "queue": queue, "rows": rows}

    async def transfer(self, source_queue_id, target_queue_id, source_revision, target_revision, request_id, auto_play):
        if source_queue_id == target_queue_id or not isinstance(request_id, str) or len(request_id) != 32 or type(auto_play) is not bool:
            raise ValueError("Review a current transfer before confirming.")
        binding = digest([source_queue_id, target_queue_id, source_revision, target_revision, auto_play])
        async with self.lock, AsyncExitStack() as stack:
            if request_id in self.requests:
                if self.requests[request_id]["binding"] != binding:
                    raise ValueError("Transfer confirmation belongs to another move.")
                return {"state": self.requests[request_id]["state"]}
            for pid in sorted((source_queue_id, target_queue_id)):
                await stack.enter_async_context(self.mass.players.get_group_and_player_lock(pid))
            a, b = await self.snapshot(source_queue_id), await self.snapshot(target_queue_id)
            if a["revision"] != source_revision or b["revision"] != target_revision:
                raise ValueError("A queue or user permission changed; review again.")
            for value, pid in ((a, source_queue_id), (b, target_queue_id)):
                p = value["player"]
                if p["available"] is not True or p["type"] != "player" or p["active_group"] or p["synced_to"] or set(p["group_members"] or []) - {pid}:
                    raise ValueError("Only available single speakers can move audio.")
            if (
                b["rows"]
                or b["queue"]["current_item"]
                or b["queue"]["state"] != "idle"
                or b["player"]["playback_state"] != "idle"
                or b["player"]["active_source"] not in (None, target_queue_id)
            ):
                raise ValueError("Destination is occupied; nothing was moved.")
            if (
                a["queue"]["state"] not in {"playing", "paused"}
                or a["queue"]["state"] != a["player"]["playback_state"]
                or a["player"]["active_source"] != source_queue_id
                or a["queue"]["is_dynamic"] is not False
                or a["queue"]["autoplay_enabled"] is not False
            ):
                raise ValueError("Only stable finite queues can be moved.")
            if not a["userid"] or auto_play != (a["queue"]["state"] == "playing"):
                raise ValueError("Source user or playback state needs review.")
            for row in a["rows"]:
                media = row["media_item"]
                domains = {m["provider_domain"] for m in media["provider_mappings"]}
                provider = self.mass.get_provider(media["provider"])
                domains.add(getattr(provider, "domain", None))
                if domains & PROTECTED or media["media_type"] not in {"track", "radio", "sound_effect"}:
                    raise ValueError("Account and progress source transfers are not supported.")
            user = await self.mass.webserver.auth.get_user(a["userid"])
            if user is None or getattr(user, "enabled", True) is False:
                raise ValueError("The source user is unavailable.")
            # Re-read after the user lookup: authentication changes must invalidate confirmation.
            if (await self.snapshot(source_queue_id))["revision"] != source_revision or (await self.snapshot(target_queue_id))["revision"] != target_revision:
                raise ValueError("A queue changed before the move.")
            context = self.context()
            previous = context.get_current_user()
            target = self.mass.player_queues.queue_data(target_queue_id)
            old_user = target.userid
            try:
                context.set_current_user(user)
                self.mass.player_queues._check_player_permission(source_queue_id)
                self.mass.player_queues._check_player_permission(target_queue_id)
                self.requests[request_id] = {"binding": binding, "state": "uncertain"}
                target.userid = a["userid"]
                await self.mass.player_queues.transfer_queue(source_queue_id, target_queue_id, auto_play=auto_play)
                if target.userid != a["userid"]:
                    raise ValueError("Native transfer owner changed; inspect both queues.")
                self.requests[request_id]["state"] = "complete"
                return {"state": "complete"}
            except BaseException:
                if not target.items and target.queue.current_item is None and self.mass.players.get_player(target_queue_id).state.playback_state == "idle":
                    target.userid = old_user  # No target queue exists; never alter a partial accepted queue's owner.
                raise
            finally:
                context.set_current_user(previous)


async def install(mass):
    """Explicit operator entry only; no source, account or permission changes."""
    adapter = NativeTransfers(mass)
    if not (await adapter.status())["pinned"]:
        raise RuntimeError("Native transfer compatibility mismatch; no commands installed.")
    return register(mass, adapter)


def register(mass, adapter):
    from music_assistant_models.auth import Scope

    for name, handler in (("transfer_status", adapter.status), ("transfer_snapshot", adapter.snapshot), ("transfer", adapter.transfer)):
        mass.register_api_command("homestarter/" + name, handler, required_scope=Scope.USERS_MANAGE)
    return adapter
