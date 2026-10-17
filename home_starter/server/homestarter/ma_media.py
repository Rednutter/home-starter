"""Pinned MA adapter for catalogue discovery, continuation and local radio writes."""

import asyncio
import secrets
import time

from .media_discovery import Discovery, constraints
from .media_hygiene import cleanup, inspect_policy
from .spotify_leases import AccountsBusy


class MediaAdapter:
    def __init__(self, guard):
        from .ma_radio import RadioImporter

        self.guard, self.mass = guard, guard.mass
        self.radio = RadioImporter(self.mass)
        self.discovery = Discovery()
        self.sessions = {}  # Ephemeral playback state, not a permanent listening profile.
        self.continuation = {}
        self.lock = asyncio.Lock()
        self.policy_at = 0
        self.policy = []
        self.issue = None

    def install(self):
        from music_assistant_models.auth import Scope

        mass = self.mass
        self.radio.install()
        for name, method in {
            "media_status": self.status,
            "media_prepare": self.prepare,
            "media_play": self.play,
            "keep_going": self.keep_going,
            "radio_upsert": self.radio.upsert,
            "library_cleanup": self.cleanup,
            "queue_context": self.queue_context,
        }.items():
            mass.register_api_command("homestarter/" + name, method, required_scope=Scope.USERS_MANAGE)
        self.original_similar = mass.player_queues._get_similar_tracks
        mass.player_queues._get_similar_tracks = self.similar
        original_mode = mass.player_queues._autoplay.resolve_mode

        def mode(queue_id):
            from music_assistant.controllers.player_queues.autoplay import AutoplayMode

            data = mass.player_queues.queue_data_or_none(queue_id)
            if data and any(self.guard.spotify(i) for i in data.items):
                return AutoplayMode.SIMILAR
            return original_mode(queue_id)

        mass.player_queues._autoplay.resolve_mode = mode
        self.task = mass.create_task(self.monitor())

    async def status(self):
        now = time.time()
        self.discovery.prune()
        return {
            "protocol": 1,
            "issue": self.issue,
            "policy": self.policy,
            "autoplay": "similar",
            "sessions": [
                {
                    "queue": q,
                    "mode": s["options"]["mode"],
                    "provider": s["provider"],
                    "strategy": s["strategy"],
                    "seed": s["seed"],
                    "last_reseed": s["seeded_at"],
                    "played_seconds": s["played_seconds"],
                    "tracks": s["tracks"],
                    "exclusion_count": len(self.discovery.recent),
                    "continuation": self.continuation.get(q, "not_checked"),
                }
                for q, s in self.sessions.items()
                if now - s["checked_at"] < 60
            ],
            "radio_count": len(self.radio.records),
        }

    async def queue_context(self, queue_id: str):
        data = self.mass.player_queues.queue_data_or_none(queue_id)
        if not data or not data.queue.current_item:
            return {}
        session = self.sessions.get(queue_id, {})
        return {
            "session": data.session_id,
            "logical_session": session.get("logical_session") if session.get("session") == data.session_id else None,
            "item": data.queue.current_item.queue_item_id,
        }

    async def prepare(self):
        self.policy = await inspect_policy(self.mass, prepare=True)
        if (
            self.mass.config.get_raw_core_config_value("player_queues", "autoplay_mode") != "similar"
            or self.mass.config.get_raw_core_config_value("player_queues", "autoplay_enabled") is not True
        ):
            await self.mass.config.save_core_config("player_queues", {"autoplay_mode": "similar", "autoplay_enabled": True})
        for queue in self.mass.player_queues.all():
            if self.mass.config.get_raw_player_queue_config_value(queue.queue_id, "autoplay_mode") not in {None, "global", "similar"}:
                await self.mass.config.save_player_queue_config(queue.queue_id, {"autoplay_mode": "similar"})
        self.policy_at = time.monotonic()
        self.issue = None
        return await self.status()

    async def cleanup(self, apply: bool = False):
        async with self.lock:
            return await cleanup(self.mass, apply)

    async def play(
        self, queue_id: str, listener: str, options: dict, expected_session: str | None = None, expected_item: str | None = None, idle_only: bool = True
    ):
        from music_assistant_models.enums import MediaType

        from .ma_account_guard import _prepared

        options = constraints(options)
        async with self.lock:
            data = self.mass.player_queues.queue_data_or_none(queue_id)
            if not data or expected_session and data.session_id != expected_session:
                return {"state": "changed"}
            initial_session = data.session_id

            def unchanged():
                current = self.mass.player_queues.queue_data_or_none(queue_id)
                if current is not data or current.session_id != initial_session:
                    return False
                item = current.queue.current_item
                if not idle_only:
                    return bool(expected_item and item and item.queue_item_id == expected_item)
                player = self.mass.players.get_player(queue_id)
                return str(player.state.playback_state) == "idle" and str(current.queue.state) == "idle"

            if not unchanged():
                return {"state": "changed"}
            # The sole allocator selects and durably reserves BEFORE catalogue search.
            lease = next(
                (dict(r) for r in self.guard.engine.leases.values() if (r["queue"], r["session"], r["listener"]) == (queue_id, data.session_id, listener)), None
            )
            existing = lease is not None
            original = dict(lease) if existing else None
            if lease is None:
                lease = await self.guard.engine.reserve(self.guard.providers(), "discovery:" + queue_id, secrets.token_hex(12), listener)
            provider = self.mass.get_provider(lease["provider"])
            marker = None
            try:

                async def search(query, limit):
                    if not existing:
                        await self.guard.engine.renew_discovery(lease["token"])
                    result = await asyncio.wait_for(provider.search(query, [MediaType.TRACK], limit), timeout=8)
                    return [t.to_dict() for t in result.tracks]

                track, diagnostic = await self.discovery.choose(search, lease["provider"], options)
                # Native/other-user playback may have started while the search ran.
                if not unchanged():
                    return {"state": "changed"}
                if existing:
                    lease = await self.guard.engine.prepare_replacement(lease["token"], queue_id, data.session_id)
                marker = _prepared.set({**lease, "queue": queue_id})
                result = await self.guard.play(queue_id, track["uri"], listener)
                if result["state"] != "requested":
                    return result
                data = self.mass.player_queues.queue_data_or_none(queue_id)
                self.mass.player_queues.set_autoplay(queue_id, True)
                previous = self.sessions.get(queue_id, {})
                logical = previous.get("logical_session") if expected_session and previous.get("session") == expected_session else None
                self.sessions[queue_id] = {
                    "session": data.session_id,
                    "logical_session": logical or secrets.token_hex(12),
                    "provider": lease["provider"],
                    "listener": listener,
                    "options": options,
                    "seed": track["item_id"],
                    "strategy": diagnostic["strategy"],
                    "seeded_at": time.time(),
                    "checked_at": time.time(),
                    "played_seconds": 0,
                    "track_seconds": 0,
                    "tracks": 0,
                    "item": getattr(data.queue.current_item, "queue_item_id", None),
                }
                return {"state": "requested", "item": track, "strategy": diagnostic["strategy"]}
            except AccountsBusy:
                return {"state": "busy"}
            except Exception:
                return {"state": "discovery_unavailable"}
            finally:
                if marker is not None:
                    _prepared.reset(marker)
                active = self.guard.engine.leases.get(lease["provider"], {})
                if active.get("queue", "").startswith("discovery:"):
                    await self.guard.engine.abort_discovery(lease["token"], original)

    async def similar(self, queue_id, is_initial=False, seed_items=None):
        data = self.mass.player_queues.queue_data_or_none(queue_id)
        item = data.queue.current_item if data else None
        if not item or not self.guard.spotify(item):
            return await self.original_similar(queue_id, is_initial, seed_items)
        original_session = data.session_id
        try:
            lease = await self.guard.bind(item)
            provider = self.mass.get_provider(lease["provider"])
            media = item.media_item
            seed = next((m.item_id for m in media.provider_mappings if m.provider_instance == lease["provider"]), media.item_id)
            results = await provider.get_similar_tracks(seed, limit=25)
            if self.mass.player_queues.queue_data_or_none(queue_id) is not data or data.session_id != original_session:
                return []
            occupied = {i.media_item.item_id for i in data.items if i.media_item}
            options = self.sessions.get(queue_id, {}).get("options", {})
            self.discovery.prune()
            tracks = [t for t in results if t.item_id not in occupied and self.discovery.playable(t.to_dict(), lease["provider"], options)]
            self.continuation[queue_id] = "connected" if tracks else "unavailable"
            return ([media] if is_initial else []) + tracks
        except Exception:
            self.continuation[queue_id] = "unavailable"
            return []  # No library or other-provider fallback.

    async def keep_going(self, queue_id: str, expected_item: str):
        data = self.mass.player_queues.queue_data_or_none(queue_id)
        if not data or not data.queue.current_item or data.queue.current_item.queue_item_id != expected_item:
            return {"state": "changed"}
        if not self.guard.spotify(data.queue.current_item):
            return {"state": "unsupported"}
        if not await self.similar(queue_id):
            return {"state": "continuation_unavailable"}
        if data.queue.current_item.queue_item_id != expected_item:
            return {"state": "changed"}
        self.mass.player_queues.set_autoplay(queue_id, True)
        return {"state": "requested"}

    async def tick(self):
        now = time.time()
        for queue_id, session in list(self.sessions.items()):
            data = self.mass.player_queues.queue_data_or_none(queue_id)
            if not data or data.session_id != session["session"] or not data.queue.active or str(data.queue.state) == "idle":
                self.sessions.pop(queue_id, None)
                continue
            delta = max(0, min(10, now - session["checked_at"]))
            session["checked_at"] = now
            if str(data.queue.state) != "playing":
                continue
            session["played_seconds"] += delta
            session["track_seconds"] += delta
            item = data.queue.current_item
            boundary = bool(item and item.queue_item_id != session["item"])
            if boundary:
                if session["track_seconds"] >= 30:
                    session["tracks"] += 1
                session.update(item=item.queue_item_id, track_seconds=0)
                if item.media_item:
                    self.discovery.remember(item.media_item.to_dict())
            options = session["options"]
            if session["tracks"] >= options["reseed_tracks"] or session["played_seconds"] >= options["reseed_minutes"] * 60:
                # Reseed at a track boundary, never interrupt the middle of a song.
                if boundary:
                    result = await self.play(queue_id, session["listener"], options, session["session"], item.queue_item_id, False)
                    if result["state"] != "requested":
                        self.sessions.pop(queue_id, None)
                        self.mass.player_queues.set_autoplay(queue_id, False)

    async def monitor(self):
        while True:
            try:
                await self.tick()
                if time.monotonic() - self.policy_at >= 300:
                    await self.prepare()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.issue = "Household media recovery needs attention. Retry media setup."
            await asyncio.sleep(5)
