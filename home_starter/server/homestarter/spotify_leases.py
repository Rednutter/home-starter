"""Single-authority Spotify reservations. Run beside MA's stream resolver.

Observations must describe *all* native queues, not only Home Starter's players.
The observer must raise on incomplete inventory. No account credentials live here.
"""

import asyncio
import json
import math
import os
import secrets
import time
from pathlib import Path

from .household_music import NAMES, OVERFLOW, choose_provider, providers_by_identity


class AccountsBusy(ValueError):
    """A caller may offer an explicit takeover; never silently steal a session."""


def write_private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class SpotifyLeases:
    """One instance per MA server; all observations and reservations are serialized.

    observe() returns {queue: {session, provider, state}} using fresh native state.
    grant_state() returns idle/personal/owned/unknown; 'owned' requires proof that
    Spotify playback belongs to this authority's current Grant overflow session.
    stop(lease) must compare queue AND session immediately before stopping.
    """

    def __init__(self, path, observe, grant_state, stop, *, clock=time.time, pending_timeout=30):
        self.path = Path(path)
        self.observe, self.grant_state, self.stop = observe, grant_state, stop
        self.clock, self.pending_timeout = clock, pending_timeout
        self.lock = asyncio.Lock()
        self.leases = self._load()

    def _load(self):
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if value.get("version") != 1 or set(value) != {"version", "leases"} or not isinstance(value["leases"], dict):
                raise ValueError
            for provider, row in value["leases"].items():
                if (
                    set(row) != {"provider", "queue", "session", "listener", "token", "created", "confirmed"}
                    or row["provider"] != provider
                    or any(not isinstance(row[k], str) or not row[k] for k in ("provider", "queue", "session", "listener", "token"))
                    or row["listener"] not in NAMES
                    or type(row["created"]) not in (int, float)
                    or not math.isfinite(row["created"])
                    or type(row["confirmed"]) is not bool
                ):
                    raise ValueError
            return value["leases"]
        except (ValueError, TypeError, AttributeError, KeyError):
            raise ValueError("Music account reservations need administrator attention. Playback was not allocated.") from None

    def _save(self):
        write_private_json(self.path, {"version": 1, "leases": self.leases})

    async def _refresh(self):
        observed = await self.observe()
        if not isinstance(observed, dict) or any(
            not isinstance(row, dict) or not {"session", "provider", "state"} <= row.keys() or row["state"] not in {"preparing", "playing", "paused", "idle"}
            for row in observed.values()
        ):
            raise AccountsBusy("Music account activity could not be checked. Try again shortly.")
        for provider, lease in list(self.leases.items()):
            row = observed.get(lease["queue"])
            same = row and row["session"] == lease["session"]
            if same and row["provider"] == provider and row["state"] in {"playing", "paused"}:
                lease["confirmed"] = True
            elif (
                not lease["confirmed"]
                and (not row or same and (row["state"] == "idle" or row["state"] == "preparing" and row["provider"] in {None, provider}))
                and 0 <= self.clock() - lease["created"] <= self.pending_timeout
            ):
                continue
            else:
                # Replaced queues, ended sessions, clock rollback and abandoned
                # starts heal without stopping whatever now owns the speaker.
                del self.leases[provider]
        return observed

    @staticmethod
    def _occupied(observed):
        return {row["provider"] for row in observed.values() if row["provider"] and row["state"] in {"playing", "paused", "preparing"}}

    async def reserve(self, providers, queue, session, listener):
        if listener not in NAMES or not all(isinstance(v, str) and v for v in (queue, session)):
            raise ValueError("Choose a configured household listener and active speaker session.")
        async with self.lock:
            observed = await self._refresh()
            identities = providers_by_identity(providers)
            grant = identities.get("Grant", {}).get("id")
            state = "unknown"
            if listener == "Grant" or any(p == grant and r["listener"] != "Grant" for p, r in self.leases.items()):
                state = await self.grant_state()
            overflow = self.leases.get(grant)
            if overflow and overflow["listener"] != "Grant" and (listener == "Grant" or state not in {"idle", "owned"}):
                await self._preempt(overflow, observed)
                observed = await self._refresh()
            for lease in self.leases.values():
                if (lease["queue"], lease["session"], lease["listener"]) == (queue, session, listener):
                    self._save()
                    return dict(lease)
            occupied = self._occupied(observed) | self.leases.keys()
            personal = listener if listener in {"Grant", "Renae"} else None
            # Only query personal Spotify when the two shared accounts are full.
            shared = [identities.get(n, {}).get("id") for n in OVERFLOW[:2]]
            if not personal and all(p in occupied or p is None for p in shared):
                state = await self.grant_state()
            try:
                selected = choose_provider(providers, occupied, personal=personal, grant_free=state == "idle")
            except ValueError:
                self._save()
                raise AccountsBusy("Music accounts are busy. Wait, choose another source, or ask to take over.") from None
            lease = {
                "provider": selected,
                "queue": queue,
                "session": session,
                "listener": listener,
                "token": secrets.token_hex(16),
                "created": self.clock(),
                "confirmed": False,
            }
            self.leases[selected] = lease
            self._save()  # Durable before handing the pin to a stream resolver.
            return dict(lease)

    async def _preempt(self, lease, observed):
        row = observed.get(lease["queue"])
        if row and row["session"] == lease["session"] and row["provider"] == lease["provider"] and row["state"] != "idle":
            if await self.stop(dict(lease)) is not True:
                raise AccountsBusy("Personal music has priority. Shared overflow could not be released safely.")
            checked = await self.observe()
            row = checked.get(lease["queue"])
            if row and row["session"] == lease["session"] and row["provider"] == lease["provider"] and row["state"] != "idle":
                raise AccountsBusy("Personal music has priority. Waiting for shared overflow to stop.")
        self.leases.pop(lease["provider"], None)
        self._save()

    async def recover(self, providers):
        """Periodic recovery, including personal Spotify starting outside MA."""
        async with self.lock:
            observed = await self._refresh()
            grant = providers_by_identity(providers).get("Grant", {}).get("id")
            overflow = self.leases.get(grant)
            if overflow and overflow["listener"] != "Grant" and await self.grant_state() not in {"idle", "owned"}:
                await self._preempt(overflow, observed)
            self._save()

    async def release(self, token):
        async with self.lock:
            for provider, lease in list(self.leases.items()):
                if secrets.compare_digest(lease["token"], token):
                    del self.leases[provider]
                    self._save()
                    return True
            return False

    async def adopt(self, token, queue, session):
        """Move a live discovery reservation onto its new native queue atomically."""
        async with self.lock:
            lease = next((r for r in self.leases.values() if secrets.compare_digest(r["token"], token)), None)
            if (
                not lease
                or lease["confirmed"]
                or not lease["queue"].startswith("discovery:")
                or not 0 <= self.clock() - lease["created"] <= self.pending_timeout
            ):
                raise AccountsBusy("The discovery reservation expired. Try again.")
            lease.update(queue=queue, session=session, created=self.clock())
            self._save()
            return dict(lease)

    async def prepare_replacement(self, token, queue, session):
        async with self.lock:
            lease = next((r for r in self.leases.values() if secrets.compare_digest(r["token"], token)), None)
            if not lease or (lease["queue"], lease["session"]) != (queue, session):
                raise AccountsBusy("The music session changed. Try again.")
            lease.update(queue="discovery:" + queue, confirmed=False, created=self.clock())
            self._save()
            return dict(lease)

    async def renew_discovery(self, token):
        async with self.lock:
            lease = next((r for r in self.leases.values() if secrets.compare_digest(r["token"], token)), None)
            if (
                not lease
                or lease["confirmed"]
                or not lease["queue"].startswith("discovery:")
                or not 0 <= self.clock() - lease["created"] <= self.pending_timeout
            ):
                raise AccountsBusy("The discovery reservation expired. Try again.")
            lease["created"] = self.clock()
            self._save()

    async def abort_discovery(self, token, original=None):
        async with self.lock:
            lease = next((r for r in self.leases.values() if secrets.compare_digest(r["token"], token)), None)
            if not lease or not lease["queue"].startswith("discovery:"):
                return
            if original:
                observed = (await self.observe()).get(original["queue"], {})
                if (observed.get("session"), observed.get("provider")) == (original["session"], original["provider"]):
                    self.leases[lease["provider"]] = original
                    self._save()
                    return
            self.leases.pop(lease["provider"], None)
            self._save()
