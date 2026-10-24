"""MA 2.10.6 stream boundary adapter; install inside the MA process before serving.

This module is not imported by the Home Starter HTTP server. The small installer
copies it, household_music and spotify_leases beside a version-checked MA startup
hook. Account credentials remain exclusively in the existing MA provider objects.
"""

import asyncio
import inspect
import json
import logging
import weakref
from contextlib import aclosing
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

import aiohttp

from .household_music import IDENTITIES, NAMES, normalized, providers_by_identity
from .spotify_leases import AccountsBusy, SpotifyLeases, write_private_json

PROTOCOL = 1
SUPPORTED_MA = {"2.10.6", "2.10.7"}
_pin = ContextVar("home_starter_spotify_pin", default=None)
_resolving = ContextVar("home_starter_resolving_queue", default=None)
_request_failure = ContextVar("home_starter_music_request_failure", default=None)
_prepared = ContextVar("home_starter_prepared_allocation", default=None)
ISSUES = {None, "audio_key_unavailable", "playback_authorization", "playback_failed"}


class BackendDiagnostics(logging.Handler):
    """Classify in-memory backend signals; never copy an upstream log message."""

    def __init__(self, guard):
        super().__init__()
        self.guard = guard

    def emit(self, record):
        lease = _pin.get()
        if not lease:
            return
        message = record.getMessage().casefold()
        if "error audio key" in message or "audio key error" in message:
            self.guard.backend_errors[lease["provider"]] = "audio_key_unavailable"
        elif "invalid_credentials" in message:
            self.guard.backend_errors[lease["provider"]] = "playback_authorization"


class AccountGuard:
    def __init__(self, mass, *, review=None):
        self.mass = mass
        self.review = review
        self.error = None
        self.wrappers = {}
        self.soloist_runs = weakref.WeakKeyDictionary()
        self.soloist_class = self.soloist_handler = None
        self.identity_path = Path(mass.storage_path) / "home-starter-spotify-identities.json"
        self.identities = json.loads(self.identity_path.read_text()) if self.identity_path.exists() else {}
        if not isinstance(self.identities, dict) or any(n not in IDENTITIES or not isinstance(p, str) or not p for n, p in self.identities.items()):
            raise ValueError("Household Spotify identity mappings need administrator review.")
        if len(set(self.identities.values())) != len(self.identities):
            raise ValueError("A Spotify provider cannot serve two household identities.")
        self.engine = SpotifyLeases(Path(mass.storage_path) / "home-starter-spotify-leases.json", self.observe, self.grant_state, self.stop)
        self.check_path = Path(mass.storage_path) / "home-starter-spotify-checks.json"
        self.playback_checks = json.loads(self.check_path.read_text()) if self.check_path.exists() else {}
        if not isinstance(self.playback_checks, dict):
            raise ValueError("Household Spotify playback checks need administrator attention.")
        self.playback_checks = {k: {"state": v, "issue": None} if isinstance(v, str) else v for k, v in self.playback_checks.items()}
        if not isinstance(self.playback_checks, dict) or any(
            not isinstance(k, str)
            or not isinstance(v, dict)
            or set(v) != {"state", "issue"}
            or not isinstance(v["state"], str)
            or v["state"] not in {"connected", "connected_but_incomplete"}
            or v["issue"] is not None
            and not isinstance(v["issue"], str)
            or v["issue"] not in ISSUES
            for k, v in self.playback_checks.items()
        ):
            raise ValueError("Household Spotify playback checks need administrator attention.")
        self.backend_errors = {}
        self.log_handler = BackendDiagnostics(self)
        self.task = None

    def providers(self):
        names = {p: n for n, p in self.identities.items()}
        return [
            {
                "id": p.instance_id,
                "name": p.name,
                "domain": p.domain,
                "available": p.available,
                **({"household_identity": names[p.instance_id]} if p.instance_id in names else {}),
            }
            for p in self.mass.providers
        ]

    async def configure_accounts(self, identities: dict[str, str]) -> dict:
        available = {p.instance_id for p in self.mass.providers if p.domain == "spotify"}
        if any(n not in IDENTITIES or p not in available for n, p in identities.items()) or len(set(identities.values())) != len(identities):
            raise ValueError("Wait for Spotify accounts to load, then review the household mappings.")
        if any(n in self.identities and self.identities[n] != p for n, p in identities.items()):
            raise ValueError("Changing an existing Spotify identity requires administrator review.")
        merged = {**self.identities, **identities}
        if len(set(merged.values())) != len(merged):
            raise ValueError("A Spotify provider cannot serve two household identities.")
        if merged != self.identities:
            write_private_json(self.identity_path, merged)
            self.identities = merged
        return {"state": "connected"}

    def account_integrity(self):
        spotify = [p for p in self.mass.providers if p.domain == "spotify" and p.available]
        accounts = [(getattr(p, "_sp_user", None) or {}).get("id") for p in spotify]
        known = all(isinstance(a, str) and a for a in accounts)
        playback_matches = True
        for provider, account in zip(spotify, accounts, strict=True):
            try:
                backend = provider.get_setup_value("playback_backend") or "librespot"
                if backend == "librespot":
                    credential = json.loads(provider.get_setup_value("librespot_credentials") or "{}")
                    matches = credential.get("username") == account
                elif backend == "soloist":
                    matches = (
                        provider.get_setup_value("soloist_download_consent") is True
                        and bool(provider.get_setup_value("soloist_api_key"))
                        and self.soloist_account(provider) == account
                    )
                else:
                    matches = False
                playback_matches = playback_matches and matches and bool(account)
            except (ValueError, TypeError, AttributeError):
                playback_matches = False
        return known and playback_matches and len(accounts) == len(set(accounts)), len(set(accounts)) if known else 0

    @staticmethod
    def soloist_account(provider):
        from music_assistant.providers.spotify.helpers import soloist_session_account

        return soloist_session_account(provider.backend._data_dir)

    @staticmethod
    def spotify(item):
        media = item.media_item
        return bool(media and any(m.provider_domain == "spotify" for m in media.provider_mappings))

    def session(self, item):
        data = self.mass.player_queues.queue_data_or_none(item.queue_id)
        if not data or not data.session_id or not any(i.queue_item_id == item.queue_item_id for i in data.items):
            raise AccountsBusy("The speaker session changed. Choose the music again.")
        return data

    async def observe(self):
        result = {}
        for queue in self.mass.player_queues.all():
            data = self.mass.player_queues.queue_data_or_none(queue.queue_id)
            if not data:
                raise AccountsBusy("Music account activity could not be checked.")
            state = str(queue.state)
            if state not in {"playing", "paused", "idle"}:
                raise AccountsBusy("Music account activity could not be checked.")
            if getattr(queue, "active", True) is False:
                state = "idle"  # A replaced native source cannot retain an account reservation.
            item = queue.current_item
            details = item.streamdetails if item else None
            provider = details.provider if details else None
            if state != "idle" and item and self.spotify(item) and not provider:
                lease = next((r for r in self.engine.leases.values() if (r["queue"], r["session"]) == (queue.queue_id, data.session_id)), None)
                if lease:
                    provider, state = lease["provider"], "preparing"
                else:
                    # All source opens pass the guard installed before startup.
                    # A queue without details has not acquired a source yet.
                    state = "preparing"
            result[queue.queue_id] = {"session": data.session_id, "provider": provider, "state": state}
        return result

    async def grant_state(self):
        """Read real Spotify Connect activity. Errors and missing scopes deny overflow.

        The pinned MA backends fetch single tracks without advertising a Connect
        player. Consequently any playing Connect session belongs to the person;
        never infer that it is our overflow from a matching track or device name.
        """
        descriptor = providers_by_identity(self.providers()).get("Grant")
        provider = next((p for p in self.mass.providers if descriptor and p.instance_id == descriptor["id"]), None)
        if provider is None:
            return "unknown"
        if provider.get_setup_value("playback_backend") == "soloist":
            return "unknown"  # Its Connect device cannot yet be identified without trusting a spoofable name.
        try:
            auth = await provider._get_auth_info(use_global_session=False)
            async with self.mass.http_session.get(
                "https://api.spotify.com/v1/me/player",
                headers={"Authorization": "Bearer " + auth["access_token"]},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == 204:
                    return "idle"
                if response.status != 200:
                    return "unknown"
                value = await response.json()
                if type(value.get("is_playing")) is not bool:
                    return "unknown"
                return "personal" if value["is_playing"] else "idle"
        except Exception:
            return "unknown"

    async def stop(self, lease):
        data = self.mass.player_queues.queue_data_or_none(lease["queue"])
        if not data or data.session_id != lease["session"]:
            return False
        # MA's stop itself rechecks the session after awaiting device control.
        await self.mass.player_queues.stop(lease["queue"])
        data = self.mass.player_queues.queue_data_or_none(lease["queue"])
        return not data or data.session_id != lease["session"] or str(data.queue.state) == "idle"

    async def bind(self, item):
        if not self.account_integrity()[0]:
            raise AccountsBusy("Spotify account identities could not be verified. Review the connected accounts.")
        data = self.session(item)
        prepared = _prepared.get()
        if prepared and prepared["queue"] == item.queue_id:
            current = self.engine.leases.get(prepared["provider"], {})
            if current.get("queue") == item.queue_id and current.get("session") == data.session_id and current.get("token") == prepared["token"]:
                return dict(current)
            return await self.engine.adopt(prepared["token"], item.queue_id, data.session_id)
        nested = _pin.get()
        if nested:
            if (nested["queue"], nested["session"]) != (item.queue_id, data.session_id):
                raise AccountsBusy("The speaker session changed. Choose the music again.")
            return nested
        user = await self.mass.webserver.auth.get_user(data.userid) if data.userid else None
        name = next((n for n in NAMES if user and normalized(user.display_name or user.username) == normalized(n)), "House")
        marker = _resolving.set((item.queue_id, data.session_id))
        try:
            lease = await self.engine.reserve(self.providers(), item.queue_id, data.session_id, name)
        except AccountsBusy:
            if failure := _request_failure.get():
                failure["state"] = "busy"
            raise
        finally:
            _resolving.reset(marker)
        if self.session(item).session_id != lease["session"]:
            await self.engine.release(lease["token"])
            raise AccountsBusy("The speaker session changed. Choose the music again.")
        return lease

    def check_pin(self, item, lease):
        if self.session(item).session_id != lease["session"] or self.engine.leases.get(lease["provider"], {}).get("token") != lease["token"]:
            raise AccountsBusy("The music account reservation changed. Choose the music again.")
        if item.streamdetails and (
            item.streamdetails.provider != lease["provider"] or getattr(item.streamdetails, "queue_session_id", None) not in {None, lease["session"]}
        ):
            # Cached streamdetails/buffers must never bypass a new allocation.
            item.streamdetails = None

    async def soloist_acquire(self, original, backend, *args, **kwargs):
        """Settle only a recorded run whose native ownership was revoked.

        MA schedules stopped-session buffer cleanup in a background task. A
        replacement can reach Soloist before that task releases its single slot.
        URI/device-name equality cannot prove ownership; use the captured lease.
        """
        lease = _pin.get()
        run = backend._run
        owner = self.soloist_runs.get(run) if run else None
        if lease and backend.provider.instance_id != lease["provider"]:
            raise AccountsBusy("The Spotify playback account changed.")
        if lease and owner and (owner["token"], owner["session"]) != (lease["token"], lease["session"]):
            data = self.mass.player_queues.queue_data_or_none(owner["queue"])
            active = data and data.session_id == owner["session"] and getattr(data.queue, "active", True) and str(data.queue.state) in {"playing", "paused"}
            if not active:
                current = self.engine.leases.get(lease["provider"], {})
                if (current.get("token"), current.get("session")) != (lease["token"], lease["session"]):
                    raise AccountsBusy("The music account reservation changed.")
                await backend.discard_run(run)
        run = await original(backend, *args, **kwargs)
        if lease:
            self.soloist_runs[run] = dict(lease)
        return run

    def wrap_soloist(self):
        from music_assistant.providers.spotify.backends.soloist import SoloistBackend

        original = SoloistBackend._acquire_run
        if not {"self", "spotify_uri", "seek_position", "streamdetails", "continuation"} <= inspect.signature(original).parameters.keys():
            raise RuntimeError("Soloist source does not match the reviewed adapter.")

        @wraps(original)
        async def acquire(backend, *args, **kwargs):
            return await self.soloist_acquire(original, backend, *args, **kwargs)

        self.soloist_class, self.soloist_handler = SoloistBackend, acquire
        SoloistBackend._acquire_run = acquire

    def wrap(self):
        logging.getLogger("music_assistant").addHandler(self.log_handler)
        audio = self.mass.streams.audio
        original_details, original_buffer = audio.get_stream_details, audio.get_audio_buffer
        original_mappings, original_discover = audio._get_mapping_providers, audio._discover_alternative_provider_mappings
        original_stream = audio.get_media_stream

        @wraps(original_details)
        async def details(queue_item, *args, **kwargs):
            if not self.spotify(queue_item) and not _pin.get():
                return await original_details(queue_item, *args, **kwargs)
            lease = await self.bind(queue_item)
            self.check_pin(queue_item, lease)
            bound = inspect.signature(original_details).bind(queue_item, *args, **kwargs)
            excluded = set(bound.arguments.get("excluded_provider_instances") or ())
            excluded.update(p.instance_id for p in self.mass.providers if p.instance_id != lease["provider"])
            bound.arguments["excluded_provider_instances"] = excluded
            marker = _pin.set(lease)
            try:
                result = await original_details(*bound.args, **bound.kwargs)
                self.check_pin(queue_item, lease)
                if result.provider != lease["provider"]:
                    raise AccountsBusy("Music account isolation could not be confirmed.")
                return result
            finally:
                _pin.reset(marker)

        @wraps(original_buffer)
        async def buffer(queue_item, *args, **kwargs):
            if not self.spotify(queue_item) and not _pin.get():
                return await original_buffer(queue_item, *args, **kwargs)
            lease = await self.bind(queue_item)
            self.check_pin(queue_item, lease)
            bound = inspect.signature(original_buffer).bind(queue_item, *args, **kwargs)
            bound.arguments["allow_provider_match"] = False
            marker = _pin.set(lease)
            self.backend_errors.pop(lease["provider"], None)
            try:
                result = await original_buffer(*bound.args, **bound.kwargs)
                self.check_pin(queue_item, lease)
                if not queue_item.streamdetails or queue_item.streamdetails.provider != lease["provider"]:
                    raise AccountsBusy("Music account isolation could not be confirmed.")
                self.record_playback(lease["provider"], "connected")
                return result
            except AccountsBusy:
                raise
            except Exception:
                self.record_playback(lease["provider"], "connected_but_incomplete")
                raise
            finally:
                _pin.reset(marker)

        @wraps(original_mappings)
        def mappings(mapping):
            candidates = original_mappings(mapping)
            lease = _pin.get()
            return [p for p in candidates if p.instance_id == lease["provider"]] if lease else candidates

        @wraps(original_discover)
        async def discover(*args, **kwargs):
            return set() if _pin.get() else await original_discover(*args, **kwargs)

        @wraps(original_stream)
        async def stream(streamdetails, *args, **kwargs):
            spotify = {p["id"] for p in self.providers() if p["domain"] == "spotify"}
            inherited = _pin.get()
            initial = inherited if inherited and inherited["provider"] == streamdetails.provider else self.engine.leases.get(streamdetails.provider)
            protected = streamdetails.provider in spotify or streamdetails.provider in self.identities.values() or initial is not None
            token = initial["token"] if initial else None
            session = initial["session"] if initial else None

            def check():
                if not protected:
                    return
                lease = self.engine.leases.get(streamdetails.provider)
                data = self.mass.player_queues.queue_data_or_none(streamdetails.queue_id)
                if (
                    not lease
                    or lease["token"] != token
                    or lease["session"] != session
                    or not data
                    or (lease["queue"], lease["session"]) != (streamdetails.queue_id, data.session_id)
                ):
                    raise AccountsBusy("The music account reservation ended.")
                if streamdetails.queue_session_id != lease["session"]:
                    raise AccountsBusy("The speaker session changed.")

            check()
            async with aclosing(original_stream(streamdetails, *args, **kwargs)) as chunks:
                async for chunk in chunks:
                    check()  # An old/prebuffered task cannot emit after revocation.
                    yield chunk

        self.wrappers = {
            "get_stream_details": details,
            "get_audio_buffer": buffer,
            "get_media_stream": stream,
            "_get_mapping_providers": mappings,
            "_discover_alternative_provider_mappings": discover,
        }
        for name, handler in self.wrappers.items():
            setattr(audio, name, handler)

    def record_playback(self, provider, state):
        issue = self.backend_errors.get(provider, "playback_failed") if state != "connected" else None
        value = {"state": state, "issue": issue}
        if self.playback_checks.get(provider) != value:
            self.playback_checks[provider] = value
            write_private_json(self.check_path, self.playback_checks)

    async def status(self, verify: bool = False) -> dict:
        reviewed = self.mass.version in SUPPORTED_MA
        if self.review is not None:
            from .ma_release_review import ReviewedRelease

            reviewed = type(self.review) is ReviewedRelease and self.review.valid()
        healthy = reviewed and all(getattr(self.mass.streams.audio, n) is h for n, h in self.wrappers.items())
        if self.review is not None:
            healthy = healthy and self.soloist_class is not None and self.soloist_class._acquire_run is self.soloist_handler
        healthy = healthy and (self.soloist_class is None or self.soloist_class._acquire_run is self.soloist_handler)
        integrity, distinct = self.account_integrity()
        healthy = healthy and integrity and (self.task is None or not self.task.done())
        result = {
            "protocol": PROTOCOL,
            "isolated": healthy and not self.error,
            "state": "connected" if healthy and not self.error else "needs_attention",
            "distinct_accounts": distinct,
            "playback_checks": [
                {"name": name, **self.playback_checks[p["id"]]}
                for name, p in providers_by_identity(self.providers()).items()
                if p["id"] in self.playback_checks
            ],
        }
        if verify:
            result["grant_activity"] = await self.grant_state()
            result["playback_entitlements"] = [
                {"name": p.name, "premium": (getattr(p, "_sp_user", None) or {}).get("product") == "premium"}
                for p in self.mass.providers
                if p.domain == "spotify" and p.available
            ]
        return result

    async def play(self, queue_id: str, media: str, listener: str) -> dict:
        from music_assistant.controllers.webserver.helpers.auth_middleware import impersonated_user
        from music_assistant_models.enums import QueueOption

        if not (await self.status())["isolated"] or listener not in NAMES:
            raise AccountsBusy("Household music account protection needs administrator attention.")
        matches = [u for u in await self.mass.webserver.auth.list_users() if normalized(u.display_name or u.username) == normalized(listener)]
        if len(matches) != 1 or not matches[0].enabled:
            raise AccountsBusy("Configure the household Music Assistant user before playing.")
        marker = impersonated_user.set(matches[0])
        failure = {"state": "failed"}
        failure_marker = _request_failure.set(failure)
        try:
            await self.mass.player_queues.play_media(queue_id, media, option=QueueOption.REPLACE, start_from_beginning=True)
            return {"state": "requested"}
        except Exception:
            return {"state": failure["state"]}
        finally:
            _request_failure.reset(failure_marker)
            impersonated_user.reset(marker)

    async def recover(self):
        while True:
            try:
                if self.review is not None and self.soloist_class is None:
                    # Provider dependencies may load after the startup hook. Stay
                    # closed until the reviewed Soloist wrapper can be installed.
                    self.wrap_soloist()
                await self.engine.recover(self.providers())
                self.error = None
            except Exception:
                # No upstream exception text: a provider may include credentials.
                self.error = "Music account activity needs administrator attention."
            await asyncio.sleep(2)


def install(mass, *, review=None):
    """Called immediately after MA registers core API handlers, before web serving."""
    from music_assistant_models.auth import Scope

    if getattr(mass, "home_starter_account_guard", None):
        return mass.home_starter_account_guard
    audio = mass.streams.audio
    required = {
        "get_stream_details": {"queue_item", "excluded_provider_instances"},
        "get_audio_buffer": {"queue_item", "allow_provider_match"},
        "_get_mapping_providers": {"mapping"},
        "_discover_alternative_provider_mappings": {"queue_item", "busy_instances", "remaining"},
        "get_media_stream": {"streamdetails"},
    }
    reviewed = mass.version in SUPPORTED_MA
    if review is not None:
        from .ma_release_review import ReviewedRelease

        reviewed = type(review) is ReviewedRelease and review.valid()
    if not reviewed or any(not params <= inspect.signature(getattr(audio, n)).parameters.keys() for n, params in required.items()):
        raise RuntimeError("Home Starter account guard requires its verified Music Assistant version. Startup stopped safely.")
    guard = AccountGuard(mass, review=review)
    guard.wrap()
    guard.wrap_soloist()
    mass.register_api_command("homestarter/account_status", guard.status, required_scope=Scope.USERS_MANAGE)
    mass.register_api_command("homestarter/play", guard.play, required_scope=Scope.USERS_MANAGE)
    mass.register_api_command("homestarter/configure_accounts", guard.configure_accounts, required_scope=Scope.USERS_MANAGE)
    mass.home_starter_account_guard = guard
    guard.task = mass.create_task(guard.recover())
    from .ma_media import MediaAdapter

    guard.media = MediaAdapter(guard)
    guard.media.install()
    return guard
