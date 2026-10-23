"""Household participation; MA owns queue mechanics and buffered-item protection."""

import secrets
import time

from . import catalogue, household_music, listening_books, radio_metadata
from .music_runtime import MusicRuntimeError, digest

BUSY = {"playing", "paused", "buffering"}
CHANGED = "This listening session changed. Refresh, then join it again or choose another speaker."


def title(value, *, radio=False):
    if radio:
        return radio_metadata.text(value) or "Radio"
    return value[:240] if isinstance(value, str) and value and "://" not in value and not any(ord(c) < 32 for c in value) else "Queued audio"


def queueable(item, providers):
    sources = set(item.get("sources", [])) | household_music.item_sources(item)
    eligible = {p["id"] for p in providers if p.get("domain") not in {"spotify", *household_music.PROGRESS_DOMAINS} and household_music.connected(p)}
    forbidden = {p["id"] for p in providers if p.get("domain") in {"spotify", *household_music.PROGRESS_DOMAINS}}
    return (
        item.get("kind") == "track"
        and bool(sources & eligible)
        and not sources & (forbidden | {"spotify"})
        and not any(str(source).startswith("spotify--") for source in sources)
        and not listening_books.needs_route(item, providers)
    )


def track_uri(value, item, providers):
    """Resolve only a previously offered, available non-personal source instance."""
    allowed = {
        p["id"]
        for p in providers
        if p.get("domain") not in {"spotify", *household_music.PROGRESS_DOMAINS} and household_music.connected(p) and p["id"] in item.get("sources", [])
    }
    mappings = [
        (m.get("provider_instance"), m.get("item_id"))
        for m in value.get("provider_mappings") or []
        if m.get("provider_instance") in allowed and m.get("available", True)
    ]
    if value.get("provider") in allowed:
        mappings.append((value["provider"], value.get("item_id")))
    mappings = sorted(
        {(provider, key) for provider, key in mappings if isinstance(key, str) and key and len(key) <= 2048 and not any(ord(c) < 32 for c in key)}
    )
    if value.get("media_type") != "track" or not mappings:
        raise ValueError("This item's supported source changed. Refresh your choices before adding it.")
    provider, key = mappings[0]
    return f"{provider}://track/{key}"


class QueueSessions:
    def __init__(self, listening):
        self.listening = listening

    async def inspect(self, endpoint, connection, data, player):
        runtime = self.listening.runtime
        pid = player["player_id"]
        lease = data["leases"].get(pid)
        if not lease or not lease.get("session"):
            return None
        await self.listening.sample(endpoint, connection, data, pid, lease)
        if data["leases"].get(pid) is not lease:
            return None
        queue = await runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
        rows = await runtime.command(endpoint, connection, "player_queues/items", queue_id=pid, limit=500)
        current = ((queue or {}).get("current_item") or {}).get("queue_item_id")
        if not isinstance(rows, list) or len(rows) >= 500 or not rows or any(not isinstance(r, dict) or not r.get("queue_item_id") for r in rows):
            raise MusicRuntimeError("This queue cannot be checked safely. Choose another speaker.")
        ids = [r["queue_item_id"] for r in rows]
        if len(ids) != len(set(ids)):
            raise MusicRuntimeError("This queue cannot be checked safely. Refresh or choose another speaker.")
        if current != lease.get("queue_item_id") or current not in ids or not queue.get("active") or queue.get("state") not in BUSY:
            raise MusicRuntimeError(CHANGED)
        boundary = None
        index, buffered = queue.get("current_index"), queue.get("index_in_buffer")
        if type(index) is int and 0 <= index < len(ids) and ids[index] == current and "index_in_buffer" in queue:
            if buffered is None or type(buffered) is int and index <= buffered < len(ids):
                boundary = max(index, buffered if buffered is not None else index)
        revision = digest(
            [connection["generation"], lease.get("session"), lease["scope"], current, ids, queue["state"], boundary, queue.get("shuffle_enabled")]
        )
        return {
            "lease": lease,
            "revision": revision,
            "ids": ids,
            "current": current,
            "rows": rows,
            "state": queue["state"],
            "boundary": boundary,
            "shuffle": queue.get("shuffle_enabled"),
        }

    @staticmethod
    def edit_issue(checked, providers):
        if checked["boundary"] is None or checked["shuffle"] is not False or checked["state"] not in {"playing", "paused"}:
            return "Queue editing needs a stable, unshuffled queue with a verified playback buffer."
        for row in checked["rows"]:
            media = row.get("media_item")
            if not isinstance(media, dict) or not queueable({**media, "kind": media.get("media_type")}, providers):
                return "Queue editing is unavailable until every item has a supported music source."
        return None

    @staticmethod
    def entry(checked, identifier):
        return digest([checked["revision"], identifier])[:24]

    @staticmethod
    def issue(player, lease, version):
        if "play_media" not in player.get("features", []) or version != "2.10.7":
            return "Queue changes are not supported for this speaker or Music Assistant version. Choose another speaker."
        if lease.get("kind") != "track" or lease.get("native_session") or lease.get("progress_route"):
            return "Queue changes for this source are not supported yet. Join listening or choose another speaker."
        return None

    async def view(self, endpoint, connection, data, house, players, scope):
        people = {"person:" + p["id"]: p["name"] for p in house["people"]}
        profile = data["profiles"].get(scope, {})
        result = []
        version = endpoint.get("version") if isinstance(endpoint, dict) else None
        providers = (await self.listening.runtime.snapshot()).get("providers", [])
        for player in players:
            pid = player["player_id"]
            public = {"player_id": pid, "owner": None, "owned": False, "joined": False, "can_join": False, "can_add": False}
            if player["available"] and player["single"]:
                try:
                    checked = await self.inspect(endpoint, connection, data, player)
                    if checked:
                        lease = checked["lease"]
                        owned = lease["scope"] == scope
                        joined = profile.get("joined") == {"player_id": pid, "session": lease.get("session")}
                        issue = self.issue(player, lease, version)
                        edit_issue = issue or self.edit_issue(checked, providers)
                        public.update(
                            owner=people.get(lease["scope"], "House"),
                            owned=owned,
                            joined=joined,
                            can_join=not owned and not joined,
                            can_add=(owned or joined) and issue is None,
                            can_next=(owned or joined) and edit_issue is None,
                            can_edit=owned and edit_issue is None,
                            can_takeover=not owned and edit_issue is None and not lease.get("item", {}).get("catalogue_access"),
                            source_scoped=bool(lease.get("item", {}).get("catalogue_access")),
                            takeover_issue="Profile-scoped queues keep their native user context. Join listening or choose another speaker."
                            if not owned and lease.get("item", {}).get("catalogue_access")
                            else None,
                            edit_issue=edit_issue,
                            issue=issue,
                            revision=checked["revision"],
                            queue=[
                                {
                                    "title": title(
                                        lease.get("item", {}).get("title")
                                        if lease.get("kind") == "radio" and r["queue_item_id"] == checked["current"]
                                        else r.get("name"),
                                        radio=lease.get("kind") == "radio",
                                    ),
                                    "current": r["queue_item_id"] == checked["current"],
                                    "entry": self.entry(checked, r["queue_item_id"]),
                                    "remove": owned and edit_issue is None and i > checked["boundary"],
                                    "up": owned and edit_issue is None and i > checked["boundary"] + 1,
                                    "down": owned and edit_issue is None and checked["boundary"] < i < len(checked["rows"]) - 1,
                                }
                                for i, r in enumerate(checked["rows"])
                            ],
                        )
                    elif player.get("state") in BUSY:
                        public["issue"] = "Playback is outside this household session. Choose another speaker."
                except (MusicRuntimeError, ValueError):
                    public["issue"] = "This listening session could not be checked. Refresh or choose another speaker."
            result.append(public)
        return result

    async def action(self, endpoint, connection, data, profile, scope, player, body, item=None, *, user=None, surface=None):
        action = body["action"]
        if action == "queue_leave":
            profile.pop("joined", None)
            return
        if action == "queue_takeover_cancel":
            profile.pop("takeover", None)
            return
        checked = await self.inspect(endpoint, connection, data, player)
        if not checked or body.get("session") != checked["revision"]:
            raise ValueError(CHANGED)
        lease = checked["lease"]
        membership = {"player_id": player["player_id"], "session": lease.get("session")}
        if action == "queue_join":
            # Participation grants no stop, replacement, timer or progress rights.
            if lease["scope"] != scope:
                profile["joined"] = membership
            return
        version = endpoint.get("version") if isinstance(endpoint, dict) else None
        providers = (await self.listening.runtime.snapshot()).get("providers", [])
        if action in {"queue_takeover_prepare", "queue_takeover"}:
            if lease.get("item", {}).get("catalogue_access"):
                raise ValueError("Taking over this profile-scoped queue is unavailable. Join or choose another speaker.")
            if lease["scope"] == scope:
                raise ValueError("This queue already belongs to this profile.")
            if issue := self.issue(player, lease, version) or self.edit_issue(checked, providers):
                raise ValueError(issue)
            if action == "queue_takeover_prepare":
                profile["takeover"] = {
                    "player_id": player["player_id"],
                    "revision": checked["revision"],
                    "confirmation": secrets.token_hex(16),
                    "expires": time.time() + 30,
                }
                return
            confirmation = profile.get("takeover") or {}
            if (
                confirmation.get("player_id") != player["player_id"]
                or confirmation.get("revision") != checked["revision"]
                or confirmation.get("confirmation") != body.get("confirmation")
                or not confirmation.get("confirmation")
                or confirmation.get("expires", 0) < time.time()
            ):
                raise ValueError("Review the current owner and queue, then confirm takeover again.")
            old = data["profiles"].get(lease["scope"], {})
            timer = old.get("sleep") or {}
            if timer.get("player_id") == player["player_id"] and timer.get("session") == lease["session"]:
                old.pop("sleep", None)
            lease.update(scope=scope, session=secrets.token_hex(12), user=user, surface=surface)
            profile.pop("takeover", None)
            profile.pop("joined", None)
            # Ownership of finite non-personal music only; no playback command,
            # native user change, copied history or cross-person progress write.
            return
        if lease["scope"] != scope and profile.get("joined") != membership:
            raise ValueError("Join this listening session before adding music, or choose another speaker.")
        if issue := self.issue(player, lease, version):
            raise ValueError(issue)
        if action in {"queue_remove", "queue_move", "queue_next"}:
            if issue := self.edit_issue(checked, providers):
                raise ValueError(issue)
            if action != "queue_next":
                if lease["scope"] != scope:
                    raise ValueError("Only the queue owner can reorder or remove items. Join to add music or choose another speaker.")
                return await self.edit(endpoint, connection, data, player, body, checked)
        if not queueable(item, providers):
            raise ValueError("This item cannot be added safely yet. Choose a supported music source or another speaker.")
        native = await self.listening.runtime.command(endpoint, connection, "music/item_by_uri", uri=item["uri"])
        if not isinstance(native, dict):
            raise ValueError("This item's supported source changed. Refresh your choices before adding it.")
        uri = track_uri(native, item, providers)
        user_args = {}
        if lease.get("item", {}).get("catalogue_access"):
            owner = await self.listening.record_access(endpoint, connection, lease["item"], lease["scope"], providers)
            contributor = await catalogue.policy(
                self.listening.runtime,
                endpoint,
                connection,
                self.listening.store.load(),
                scope.removeprefix("person:") if scope.startswith("person:") else None,
                providers,
            )
            if uri.split("://", 1)[0] not in set(owner["sources"]) & set(contributor["sources"]):
                raise PermissionError("This source is not assigned to both profiles. Choose another speaker.")
            user_args = {"user": {"provider": "builtin", "user_id": owner["user_id"], "required": True}}
        elif item.get("catalogue_access"):
            raise ValueError("This queue's native profile context is unverified. Start on another speaker.")
        fresh = await self.inspect(endpoint, connection, data, player)
        if not fresh or fresh["revision"] != checked["revision"]:
            raise ValueError(CHANGED)
        # Runtime.lock serializes household callers. MA ADD never replaces the
        # queue or starts playback; external native writers are checked read-back,
        # not claimed to be locked by this service.
        await self.listening.runtime.control(
            endpoint,
            connection,
            "player_queues/play_media",
            queue_id=player["player_id"],
            media=uri,
            option="next" if action == "queue_next" else "add",
            **user_args,
        )
        after = await self.inspect(endpoint, connection, data, player)
        insertion = checked["boundary"] + 1 if action == "queue_next" else len(checked["ids"])
        if (
            not after
            or after["current"] != checked["current"]
            or after["ids"][:insertion] + after["ids"][insertion + 1 :] != checked["ids"]
            or len(after["ids"]) != len(checked["ids"]) + 1
        ):
            raise MusicRuntimeError("The queue changed while adding. Refresh to inspect it before trying again; nothing was automatically retried.")
        lease["queue_items"] = after["ids"]

    async def edit(self, endpoint, connection, data, player, body, checked):
        index = next((i for i, key in enumerate(checked["ids"]) if self.entry(checked, key) == body.get("entry")), None)
        if index is None or index <= checked["boundary"]:
            raise ValueError("That item is current, already buffered or changed. Refresh the queue.")
        expected = checked["ids"].copy()
        identifier = expected.pop(index)
        if body["action"] == "queue_move":
            shift = body.get("value")
            if type(shift) is not int or shift not in {-1, 1} or not checked["boundary"] < index + shift < len(checked["ids"]):
                raise ValueError("Move an upcoming item one place within the editable queue.")
            expected.insert(index + shift, identifier)
            command, args = "player_queues/move_item", {"queue_item_id": identifier, "pos_shift": shift}
        else:
            command, args = "player_queues/delete_item", {"item_id_or_index": identifier}
        fresh = await self.inspect(endpoint, connection, data, player)
        if not fresh or fresh["revision"] != checked["revision"]:
            raise ValueError(CHANGED)
        await self.listening.runtime.control(endpoint, connection, command, queue_id=player["player_id"], **args)
        after = await self.inspect(endpoint, connection, data, player)
        if not after or after["ids"] != expected or after["current"] != checked["current"]:
            raise MusicRuntimeError("The queue edit was not confirmed. Refresh before trying again; nothing was automatically retried.")
        checked["lease"]["queue_items"] = after["ids"]
