"""Authenticated, read-only MA discovery and speaker-scoped playback evidence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp

from .household import HouseholdStore
from .music import find_installed
from .settings import Secret
from .supervisor import SupervisorError

READ_COMMANDS = {
    "homestarter/compatibility_status",
    "music/recommendations/items",
    "music/artists/artist_tracks",
    "music/albums/album_tracks",
    "music/playlists/playlist_tracks",
    "homestarter/transfer_status",
    "homestarter/transfer_snapshot",
    *("music/" + kind + "/library_items" for kind in ("playlists", "podcasts", "audiobooks", "albums", "artists", "tracks", "radios")),
    "music/podcasts/podcast_episodes",
    "player_queues/items",
    "providers",
    "auth/users",
    "config/providers",
    "players/all",
    "player_queues/all",
    "players/get",
    "player_queues/get_active_queue",
    "music/browse",
    "music/search",
    "music/item_by_uri",
    "music/sound_effects",
    "homestarter/account_status",
    "homestarter/media_status",
    "homestarter/queue_context",
}
CONTROL_COMMANDS = {
    "players/cmd/set_members",
    "players/cmd/group_volume",
    "homestarter/transfer",
    "player_queues/move_item",
    "player_queues/delete_item",
    "player_queues/play_media",
    "player_queues/play",
    "player_queues/pause",
    "player_queues/stop",
    "player_queues/next",
    "player_queues/previous",
    "player_queues/repeat",
    "player_queues/seek",
    "players/cmd/volume_set",
    "homestarter/play",
    "homestarter/media_play",
    "homestarter/keep_going",
    "homestarter/media_prepare",
    "homestarter/radio_upsert",
    "homestarter/library_cleanup",
}
TIMEOUT = aiohttp.ClientTimeout(total=6)


class MusicRuntimeError(Exception):
    """Only fixed, public-safe messages may cross this boundary."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def private_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


class MusicRuntime:
    def __init__(self, supervisor, session, data_dir, port=8095):
        self.supervisor, self.session, self.port = supervisor, session, port
        self.store = HouseholdStore(data_dir)
        self.connection_path = Path(data_dir) / "music-connection.json"
        self.proof_path = Path(data_dir) / "music-playback.json"
        self.collection_path = Path(data_dir) / "music-collection-access.json"
        self.lock = asyncio.Lock()
        self.interval = 2.0
        self.samples = 7
        self.startup_samples = 10

    def collection_sharing(self):
        value = self.store.read(self.collection_path, None)
        if value is None:
            return False
        connection = self.connection()
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "epoch", "server", "shared"}
            or value.get("version") != 1
            or type(value.get("shared")) is not bool
        ):
            raise MusicRuntimeError("Collection sharing choices need administrator review.")
        if not connection or value["epoch"] != self.store.load()["epoch"] or value["server"] != digest([connection["server_id"], connection["app"]]):
            return False
        return value["shared"]

    async def set_collection_sharing(self, shared):
        if type(shared) is not bool:
            raise MusicRuntimeError("Confirm a supported native collection sharing choice.")
        async with self.lock:
            connection, endpoint = self.connection(), await self.endpoint()
            if not connection:
                raise MusicRuntimeError("Connect Music Assistant before sharing native collections.")
            if shared:
                await self.account_guard(endpoint, connection)
            private_write(
                self.collection_path,
                {"version": 1, "epoch": self.store.load()["epoch"], "server": digest([connection["server_id"], connection["app"]]), "shared": shared},
            )
        return await self.household(prepare=True)

    def connection(self):
        value = self.store.read(self.connection_path, None)
        if value is None:
            return None
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "server_id", "app", "generation", "token"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or any(not isinstance(value[k], str) or not value[k] for k in ("server_id", "app", "generation", "token"))
        ):
            raise MusicRuntimeError("Music connection data is unreadable. Reconnect; other settings are preserved.")
        return {**value, "token": Secret(value["token"])}

    def evidence(self):
        value = self.store.read(self.proof_path, {})
        if not isinstance(value, dict) or any(not isinstance(v, dict) for v in value.values()):
            raise MusicRuntimeError("Music playback evidence is unreadable. Saved service settings are preserved.")
        return value

    async def endpoint(self):
        installed = find_installed(await self.supervisor.installed_apps(), None)
        if not installed:
            raise MusicRuntimeError("Install or start Music Assistant first.")
        app = await self.supervisor.app_info(installed["slug"])
        host = app.get("ip_address") or app.get("hostname")
        port = app.get("ingress_port") if app.get("ingress") else self.port
        if app.get("state") != "started" or not isinstance(host, str) or not host or any(c in host for c in "/@?#\\\r\n"):
            raise MusicRuntimeError("Music Assistant is stopped or its address is unavailable.")
        if not str(port or self.port).isdigit() or not 1 <= int(port or self.port) <= 65535:
            raise MusicRuntimeError("Music Assistant address is unavailable.")
        address = f"http://{'[' + host + ']' if ':' in host else host}:{int(port or self.port)}"
        try:
            async with self.session.get(address + "/info", timeout=TIMEOUT, allow_redirects=False) as response:
                info = await response.json(content_type=None) if response.status == 200 else None
        except (aiohttp.ClientError, TimeoutError, ValueError, OSError):
            raise MusicRuntimeError("Music Assistant did not respond. Check it and retry.") from None
        if not isinstance(info, dict) or not isinstance(info.get("server_id"), str) or not info["server_id"]:
            raise MusicRuntimeError("Music Assistant server identity could not be checked.")
        endpoint = {
            "address": address,
            "server_id": info["server_id"],
            "app": installed["slug"],
            "version": info.get("server_version"),
            "schema_version": info.get("schema_version"),
        }
        if endpoint["version"] == "2.10.8":
            from .ma_control_contract import attestation

            try:
                connection = self.connection()
                if connection and all(connection[k] == endpoint[k] for k in ("server_id", "app")):
                    value = await asyncio.wait_for(self.command(endpoint, connection, "homestarter/compatibility_status"), 2)
                    endpoint["_native_review"] = attestation(value, endpoint)
            except (MusicRuntimeError, ValueError, KeyError, TimeoutError):
                pass  # Uninstalled/unsupported native capability leaves controls closed.
        return endpoint

    async def read_compatibility(self):
        """Administrative diagnostics only: no control, setup or checkpoint write."""
        from .ma_compatibility import assess_reads, checkpoint_bindings

        connection, endpoint = self.connection(), await self.endpoint()
        house = self.store.load()
        profiles = ["house", *[p["id"] for p in house["people"]]]
        key = digest(
            [house["epoch"], (connection or {}).get("server_id"), (connection or {}).get("app"), (connection or {}).get("generation"), sorted(profiles)]
        )
        try:
            checkpoint = self.store.read(self.connection_path.parent / "music-read-bindings.json", None)
            bindings = checkpoint_bindings(checkpoint, key, profiles)
            state = "verified" if bindings else "missing_or_changed"
        except (ValueError, OSError):
            bindings, state = None, "invalid"

        async def command(name, **args):
            return await self.command(endpoint, connection, name, **args)

        report = await assess_reads(command, endpoint, connection, bindings or {}, inspect_unbound=True)
        report["binding_checkpoint"] = state
        report["action"] = (
            "Read contracts checked. Native account enforcement and transfer still require separate verification."
            if state == "verified" and report["features"]["profile_filter_contract"]
            else "Verify existing native profile identities before permitting catalogue access; no users or filters were changed."
        )
        return report

    async def command(self, endpoint, connection, command, **args):
        if command not in READ_COMMANDS:
            raise ValueError("Music runtime only permits read commands.")
        timeout = aiohttp.ClientTimeout(total=30) if command in {"music/podcasts/podcast_episodes", "music/search"} else TIMEOUT
        return await self._request(endpoint, connection, command, request_timeout=timeout, **args)

    async def control(self, endpoint, connection, command, **args):
        if command not in CONTROL_COMMANDS:
            raise ValueError("Unsupported Music control.")
        timeout = aiohttp.ClientTimeout(total=120) if command.startswith("homestarter/") or command == "player_queues/play_media" else TIMEOUT
        result = await self._request(endpoint, connection, command, request_timeout=timeout, **args)
        if command in {"homestarter/play", "homestarter/media_play", "homestarter/keep_going"}:
            if isinstance(result, dict) and result.get("state") == "busy":
                raise MusicRuntimeError("Music accounts are busy. Wait for playback to finish or choose another source.")
            if not isinstance(result, dict) or result.get("state") != "requested":
                raise MusicRuntimeError("Spotify could not supply this selection or related music. Choose another source or retry.")
        return result

    async def account_guard(self, endpoint, connection):
        try:
            status = await self.command(endpoint, connection, "homestarter/account_status")
        except MusicRuntimeError:
            status = None
        if not isinstance(status, dict) or status.get("protocol") != 1 or status.get("isolated") is not True:
            raise MusicRuntimeError("Household Spotify account protection needs administrator attention. Other music sources remain available.")
        return status

    async def household(self, *, prepare=False):
        from .household_music import reconcile, user_status
        from .music_identity_auth import decorate, resume

        async with self.lock:
            names = tuple(dict.fromkeys([p["name"] for p in self.store.load()["people"]] + ["House"]))
            snapshot = await self.snapshot()
            if not snapshot["connected"]:
                return {"state": "ready_for_authentication", "summary": "Connect Music Assistant", "users": 0, "connected": 0, "pending": 4, "spotify": []}
            connection, endpoint = self.connection(), await self.endpoint()
            if prepare and resume(self.store, self.store.load(), snapshot["providers"]):
                snapshot["providers"] = decorate(self.store, self.store.load(), snapshot["providers"])

            async def command(name, **args):
                return await self._request(endpoint, connection, name, **args)

            sharing = self.collection_sharing()
            if prepare and sharing:
                from .household_music import providers_by_identity

                identities = {n: p["id"] for n, p in providers_by_identity(snapshot["providers"]).items()}
                await self._request(endpoint, connection, "homestarter/configure_accounts", identities=identities)
                await self.account_guard(endpoint, connection)
            result = (
                await reconcile(command, snapshot["providers"], names, share_collections=sharing)
                if prepare
                else user_status(await command("auth/users"), snapshot["providers"], names)
            )
            result["shared_collections"] = sharing
            result["route"] = snapshot["open_path"]
            try:
                if prepare and not sharing:
                    from .household_music import providers_by_identity

                    identities = {n: p["id"] for n, p in providers_by_identity(snapshot["providers"]).items()}
                    await self._request(endpoint, connection, "homestarter/configure_accounts", identities=identities)
                guard = await self.account_guard(endpoint, connection)
                result["allocator"] = {"state": "connected", "detail": "Household music account protection is active"}
                result["playback_checks"] = guard.get("playback_checks", [])
            except MusicRuntimeError as error:
                result["allocator"] = {"state": "connected_but_incomplete", "detail": str(error)}
            return result

    async def begin_identity_auth(self, name):
        from .music_identity_auth import begin

        async with self.lock:
            snapshot = await self.snapshot()
            if not snapshot["connected"]:
                raise MusicRuntimeError("Connect Music Assistant before adding a household music account.")
            begin(self.store, self.store.load(), snapshot["providers"], name)

    async def add_catalogue(self, domain, country="AU"):
        """Only zero-login household catalogue sources; never Spotify/OAuth credentials."""
        if domain not in {"abc_radio_network", "itunes_podcasts"} or not re.fullmatch(r"[A-Z]{2}", country):
            raise ValueError("Choose a supported household catalogue and country.")
        async with self.lock:
            connection, endpoint = self.connection(), await self.endpoint()
            if not connection:
                raise MusicRuntimeError("Connect Music Assistant first.")
            records = await self.command(endpoint, connection, "config/providers", provider_type="music", include_values=False)
            existing = next((r for r in records if r.get("domain") == domain), None)
            if existing is None:
                step = await self._request(
                    endpoint, connection, "config/providers/setup", request_timeout=aiohttp.ClientTimeout(total=120), provider_domain=domain
                )
                if step.get("type") != "finish":
                    raise MusicRuntimeError("This source needs its native Music Assistant setup flow. Existing providers are preserved.")
                instance = (step.get("result") or {}).get("instance_id")
            else:
                instance = existing["instance_id"]
            if domain == "itunes_podcasts" and instance:
                await self._request(
                    endpoint,
                    connection,
                    "config/providers/save",
                    request_timeout=aiohttp.ClientTimeout(total=120),
                    provider_domain=domain,
                    instance_id=instance,
                    values={"locale": country.lower(), "explicit": False},
                )
        return await self.snapshot()

    async def _request(self, endpoint, connection, command, *, request_timeout=TIMEOUT, **args):
        if any(endpoint[k] != connection[k] for k in ("server_id", "app")):
            raise MusicRuntimeError("Music Assistant identity changed. Reconnect before sending credentials.")
        try:
            async with self.session.post(
                endpoint["address"] + "/api",
                json={"message_id": "home-starter", "command": command, "args": args},
                headers={"Authorization": "Bearer " + connection["token"].reveal()},
                timeout=request_timeout,
                allow_redirects=False,
            ) as response:
                if response.status in (401, 403):
                    raise MusicRuntimeError("Music Assistant denied API access. Check the token and its permissions.")
                if response.status != 200:
                    raise MusicRuntimeError("Music Assistant could not complete this read. Check the service and retry.")
                result = await response.json(content_type=None)
                if isinstance(result, dict) and ("error_code" in result or "error" in result):
                    raise MusicRuntimeError("Music Assistant refused the operation. Check API permissions and retry; existing settings are preserved.")
                return result
        except (aiohttp.ClientError, TimeoutError, ValueError, OSError):
            raise MusicRuntimeError("Music Assistant API could not be read. Saved settings are preserved.") from None

    async def connect(self, token):
        async with self.lock:
            await self._connect(token)

    async def _connect(self, token):
        if not isinstance(token, str) or not 16 <= len(token) <= 4096 or any(ord(c) < 33 for c in token):
            raise ValueError("Enter a Music Assistant API token in this secure field; never a provider password.")
        endpoint = await self.endpoint()
        candidate = {"version": 1, "server_id": endpoint["server_id"], "app": endpoint["app"], "generation": secrets.token_hex(16), "token": Secret(token)}
        providers = await self.command(endpoint, candidate, "providers")
        players = await self.command(endpoint, candidate, "players/all")
        if not isinstance(providers, list) or not isinstance(players, list):
            raise MusicRuntimeError("Unsupported Music Assistant response. Existing connection is preserved.")
        private_write(self.connection_path, {**candidate, "token": token})

    async def wall_playback(self):
        """Read fresh, reduced queue metadata without blocking calendar readiness."""
        from .wall_media import now_playing

        connection = self.connection()
        if not connection:
            return []
        try:
            async with asyncio.timeout(5):
                endpoint = await self.endpoint()
                players = await self.command(endpoint, connection, "players/all")
                queues = await self.command(endpoint, connection, "player_queues/all")
                return now_playing(players, queues)
        except (MusicRuntimeError, SupervisorError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            return []

    async def snapshot(self):
        connection = self.connection()
        if not connection:
            return {
                "connected": False,
                "providers": [],
                "players": [],
                "configuration_known": False,
                "message": "Connect Music Assistant to inspect providers and verify playback.",
            }
        endpoint = await self.endpoint()
        loaded = await self.command(endpoint, connection, "providers")
        players = await self.command(endpoint, connection, "players/all")
        known = True
        try:
            configured = await self.command(endpoint, connection, "config/providers", provider_type="music", include_values=False)
        except MusicRuntimeError:
            configured, known = [], False
        if not isinstance(loaded, list) or not isinstance(players, list) or not isinstance(configured, list):
            raise MusicRuntimeError("Music Assistant returned an unsupported provider/player response.")
        loaded = {p["instance_id"]: p for p in loaded if isinstance(p, dict) and isinstance(p.get("instance_id"), str) and p.get("type") == "music"}
        records = {p["instance_id"]: p for p in configured if isinstance(p, dict) and isinstance(p.get("instance_id"), str) and p.get("type") == "music"}
        records.update({key: value for key, value in loaded.items() if key not in records})
        providers = [
            {
                "id": key,
                "name": p.get("name") or p.get("domain") or "Music source",
                "domain": p.get("domain"),
                "enabled": p.get("enabled", True) is True,
                "available": loaded.get(key, {}).get("available") is True,
                "requires_auth": any(
                    code in str(p.get("last_error") or "").casefold() for code in ("auth_required", "loginfailed", "login_failed", "invalid_credentials")
                ),
                "has_error": bool(p.get("last_error")),
                "status": "disabled" if p.get("enabled") is False else "connected" if loaded.get(key, {}).get("available") is True else "unavailable",
                "builtin": p.get("domain") == "builtin",
                "features": sorted(set(loaded.get(key, {}).get("supported_features") or []) & {"search", "similar_tracks", "library_tracks"}),
            }
            for key, p in records.items()
        ]
        from .music_identity_auth import decorate

        providers = decorate(self.store, self.store.load(), providers)
        safe_players = [
            {
                "id": p["player_id"],
                "name": p.get("name") or "Speaker",
                "provider": p.get("provider"),
                "can_group_with": [v for v in p.get("can_group_with", []) if isinstance(v, str)],
                "group_members": [v for v in p.get("group_members", []) if isinstance(v, str)],
                "synced_to": p.get("synced_to"),
                "available": p.get("available") is True,
                "single": p.get("type") == "player"
                and not p.get("synced_to")
                and not (set(p.get("group_members") or []) - {p["player_id"]})
                and not (set(p.get("static_group_members") or []) - {p["player_id"]}),
                "state": p.get("playback_state", p.get("state")),
                "features": sorted(
                    set(p.get("supported_features") or []) & {"pause", "next_previous", "seek", "volume_set", "volume_mute", "play_media", "set_members"}
                ),
            }
            for p in players
            if isinstance(p, dict) and isinstance(p.get("player_id"), str)
        ]
        result = {
            "connected": True,
            "providers": providers,
            "players": safe_players,
            "configuration_known": known,
            "open_path": "/app/" + endpoint["app"],
            "message": "Provider availability is separate from verified speaker playback.",
            "identity": digest([endpoint["server_id"], endpoint["app"], connection["generation"]]),
        }
        result["proof"] = self.valid_proof(result)
        pending = self.evidence().get("pending")
        if isinstance(pending, dict) and self.valid_record(pending, result, timedelta(minutes=10)):
            result["pending"] = {k: pending[k] for k in ("id", "provider_id", "player_id", "at")} | {
                "progress_verified": pending.get("progress_verified", True)
            }
        return result

    async def verified(self):
        try:
            snapshot = await self.snapshot()
            proof = snapshot.get("proof")
            if proof and any(p["id"] == proof["provider_id"] and p.get("domain") == "spotify" for p in snapshot["providers"]):
                guard = await self.account_guard(await self.endpoint(), self.connection())
                if any(row.get("state") != "connected" for row in guard.get("playback_checks", [])):
                    return None
            return proof
        except (MusicRuntimeError, SupervisorError, OSError, ValueError, KeyError, TypeError):
            return None

    def signature(self, snapshot, provider_id, player_id):
        provider = next((p for p in snapshot["providers"] if p["id"] == provider_id and p["available"] and p["enabled"] and not p["builtin"]), None)
        player = next((p for p in snapshot["players"] if p["id"] == player_id and p["available"] and p["single"]), None)
        if not provider or not player:
            raise MusicRuntimeError("Choose an available music source and a single, ungrouped speaker.")
        return digest(
            [
                snapshot["identity"],
                {k: provider[k] for k in ("id", "domain", "enabled")},
                {k: player[k] for k in ("id", "provider", "single")},
                self.store.load()["epoch"],
            ]
        )

    def valid_record(self, record, snapshot, maximum):
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(record["at"])
            return timedelta(0) <= age <= maximum and record["signature"] == self.signature(snapshot, record["provider_id"], record["player_id"])
        except (KeyError, ValueError, TypeError, MusicRuntimeError):
            return False

    def valid_proof(self, snapshot):
        record = self.evidence().get("verified", {})
        if record.get("heard") is True and self.valid_record(record, snapshot, timedelta(days=1)):
            return {k: record[k] for k in ("at", "provider_id", "player_id")} | {"progress_verified": record.get("progress_verified", True)}
        return None

    async def sample(self, endpoint, connection, provider_id, player_id):
        player = await self.command(endpoint, connection, "players/get", player_id=player_id)
        queue = await self.command(endpoint, connection, "player_queues/get_active_queue", player_id=player_id)
        if not isinstance(player, dict) or not isinstance(queue, dict):
            raise MusicRuntimeError("Start music from the selected source on this speaker in Music Assistant, then check again.")
        item = queue.get("current_item") or {}
        if not isinstance(item, dict):
            raise MusicRuntimeError("Music Assistant queue feedback is unsupported. Keep Music incomplete and retry after checking MA.")
        stream = item.get("streamdetails") or {}
        media = player.get("current_media") or {}
        if not isinstance(stream, dict) or not isinstance(media, dict):
            raise MusicRuntimeError("Music Assistant playback feedback is unsupported. Keep Music incomplete and retry after checking MA.")
        position, timestamp = player.get("elapsed_time"), player.get("elapsed_time_last_updated")
        checks = {
            "available single speaker": player.get("player_id") == player_id
            and player.get("available") is True
            and player.get("type") == "player"
            and not player.get("synced_to")
            and not (set(player.get("group_members") or []) - {player_id})
            and not (set(player.get("static_group_members") or []) - {player_id}),
            "speaker playing": player.get("playback_state", player.get("state")) == "playing",
            "active speaker queue": queue.get("queue_id") == player_id and queue.get("active") is True and queue.get("state") == "playing",
            "selected source": stream.get("provider") == provider_id and stream.get("stream_error") is not True,
            "matching queue item": isinstance(item.get("queue_item_id"), str) and media.get("queue_item_id") == item["queue_item_id"],
            "speaker queue source": player.get("active_source") == queue.get("queue_id"),
            "fresh raw position": number(position) and number(timestamp) and 0 <= time.time() - timestamp <= 20,
        }
        failed = [label for label, passed in checks.items() if not passed]
        if failed:
            raise MusicRuntimeError(
                "Playback check incomplete â€” missing: " + ", ".join(failed) + ". Keep the selected source playing on this speaker in MA, then retry."
            )
        return {"item": digest(item["queue_item_id"]), "position": position, "timestamp": timestamp}

    async def observe(self, provider_id, player_id, user):
        async with self.lock:
            snapshot = await self.snapshot()
            signature = self.signature(snapshot, provider_id, player_id)
            endpoint, connection = await self.endpoint(), self.connection()
            for attempt in range(self.startup_samples + 1):
                try:
                    first = await self.sample(endpoint, connection, provider_id, player_id)
                    break
                except MusicRuntimeError as error:
                    if attempt == self.startup_samples or not str(error).startswith("Playback check incomplete"):
                        raise
                    await asyncio.sleep(self.interval)
            found = False
            for _ in range(self.samples):
                await asyncio.sleep(self.interval)
                current = await self.sample(endpoint, connection, provider_id, player_id)
                if current["item"] != first["item"]:
                    raise MusicRuntimeError("The item changed during the check. Keep one item playing and retry.")
                if current["timestamp"] > first["timestamp"] and current["position"] - first["position"] >= 2:
                    found = True
                    break
            if signature != self.signature(await self.snapshot(), provider_id, player_id):
                raise MusicRuntimeError("Music sources or speaker membership changed. Check again.")
            value = self.evidence()
            value["pending"] = {
                "id": secrets.token_hex(16),
                "at": datetime.now(UTC).isoformat(),
                "signature": signature,
                "provider_id": provider_id,
                "player_id": player_id,
                "owner": digest(user),
                "progress_verified": found,
            }
            private_write(self.proof_path, value)
            return {
                "observed": True,
                "id": value["pending"]["id"],
                "detail": (
                    "Fresh device progress matched this provider and speaker."
                    if found
                    else "MA reported the selected source playing on this speaker, but automatic progress was not verified."
                )
                + " Confirm you heard it; a playing label alone does not complete Music.",
            }

    async def heard(self, identifier, user):
        async with self.lock:
            value = self.evidence()
            record = value.get("pending", {})
            if (
                record.get("id") != identifier
                or record.get("owner") != digest(user)
                or not self.valid_record(record, await self.snapshot(), timedelta(minutes=10))
            ):
                raise ValueError("The playback check expired or changed. Observe the chosen speaker again.")
            value["verified"] = {k: v for k, v in record.items() if k not in ("id", "owner")}
            value["verified"]["heard"] = True
            value.pop("pending", None)
            private_write(self.proof_path, value)

    async def decline(self, identifier, user):
        async with self.lock:
            value = self.evidence()
            record = value.get("pending", {})
            if record.get("id") != identifier or record.get("owner") != digest(user):
                raise ValueError("The playback check changed. Refresh and retry.")
            value.pop("pending", None)
            private_write(self.proof_path, value)
