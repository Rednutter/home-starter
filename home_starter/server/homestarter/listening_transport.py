"""Shared household transport; listening ownership and provider identity stay put."""

import asyncio

from . import listening_groups
from .listening_sessions import title
from .listening_transfer import pending as transfer_pending
from .music_runtime import MusicRuntimeError, digest

ACTIONS = {"play", "pause", "stop", "volume", "next", "previous"}
CHANGED = "Playback changed. Refresh this room before controlling it."
UNKNOWN = "The last control was not confirmed. Check current playback; it will not be retried automatically."


async def observe(listening, endpoint, connection, data, house, player):
    if not isinstance(endpoint, dict) or endpoint.get("version") != "2.10.7":
        raise ValueError("Shared controls need the reviewed Music Assistant version.")
    if not player.get("available") or not player.get("single"):
        raise ValueError("This speaker is unavailable or its group membership changed.")
    pid = player["player_id"]
    if listening_groups.pending(data, pid):
        raise ValueError(listening_groups.UNKNOWN)
    if pid in data.get("groups", {}) and not await listening.groups.verified(endpoint, connection, data, pid):
        raise ValueError("A group member is unavailable or changed. Check its speakers before controlling it.")
    if transfer_pending(data, pid):
        raise ValueError("A playback transfer is awaiting verification. Check that handoff first.")
    lease = data["leases"].get(pid)
    scopes = {"house", *("person:" + p["id"] for p in house["people"])}
    if not lease or not lease.get("session") or lease.get("scope") not in scopes or lease["scope"] not in data["profiles"]:
        raise ValueError("Playback is outside a verified household session. Choose another room.")
    await listening.sample(endpoint, connection, data, pid, lease)
    if data["leases"].get(pid) is not lease:
        raise ValueError(CHANGED)
    raw = await listening.runtime.command(endpoint, connection, "players/get", player_id=pid)
    queue = await listening.runtime.command(endpoint, connection, "player_queues/get_active_queue", player_id=pid)
    current = (queue or {}).get("current_item") or {}
    state = raw.get("playback_state", raw.get("state"))
    if (
        raw.get("available") is False
        or raw.get("type") not in (None, "player")
        or raw.get("player_id") not in (None, pid)
        or raw.get("synced_to")
        or set(raw.get("group_members") or []) - {pid}
        and not listening_groups.bound(data, pid, raw)
        or set(raw.get("static_group_members") or []) - {pid}
        or raw.get("active_source") != pid
        or not queue
        or queue.get("queue_id") != pid
        or not queue.get("active")
        or current.get("queue_item_id") != lease.get("queue_item_id")
        or (raw.get("current_media") or {}).get("queue_item_id") != lease.get("queue_item_id")
        or lease.get("generation") != connection["generation"]
        or state not in {"playing", "paused", "buffering"}
        and not lease.get("idle_pause_ack")
    ):
        raise ValueError(CHANGED)
    revision = digest(
        [
            connection["server_id"],
            connection["app"],
            connection["generation"],
            pid,
            lease["scope"],
            lease["session"],
            lease.get("native_session"),
            lease.get("logical_session"),
            lease.get("progress_route"),
            lease.get("queue_item_id"),
            state,
            queue.get("state"),
            raw.get("volume_level"),
            sorted(raw.get("group_members", [])),
        ]
    )
    pending = lease.get("transport_uncertain")
    if pending:
        target_met = pending["action"] == "volume" and raw.get("volume_level") == pending.get("value")
        if pending["before"] == revision and not target_met:
            raise ValueError(UNKNOWN)
        # A read reconciles a changed observed state; it never replays a command.
        lease.pop("transport_uncertain", None)
    features = set(player.get("features", []))
    actions = ["stop"]
    if state == "paused" or lease.get("idle_pause_ack"):
        actions.append("play")
    elif "pause" in features:
        actions.append("pause")
    if "volume_set" in features:
        actions.append("volume")
    if "next_previous" in features and lease.get("kind") not in {"audiobook", "podcast_episode", "radio"}:
        actions.extend(("next", "previous"))
    owner = next((p["name"] for p in house["people"] if lease["scope"] == "person:" + p["id"]), "House")
    playing = lease.get("item", {}).get("title") if lease.get("kind") == "radio" else current.get("name") or lease.get("item", {}).get("title")
    return {"player_id": pid, "revision": revision, "actions": actions, "owner": owner, "title": title(playing, radio=lease.get("kind") == "radio")}, lease


async def view(listening, endpoint, connection, data, house, players):
    result = []
    for player in players:
        try:
            public, _ = await observe(listening, endpoint, connection, data, house, player)
        except (MusicRuntimeError, PermissionError, ValueError):
            public = {"player_id": player["player_id"], "actions": [], "issue": "Shared controls need a current, verified household session."}
            lease = data["leases"].get(player["player_id"])
            if lease and lease.get("transport_uncertain"):
                public["issue"] = UNKNOWN
        result.append(public)
    return result


async def action(listening, endpoint, connection, data, house, player, body, user, surface, person):
    checked, lease = await observe(listening, endpoint, connection, data, house, player)
    if body.get("session") != checked["revision"]:
        raise ValueError(CHANGED)
    name, pid = body["action"], player["player_id"]
    if name not in checked["actions"]:
        raise ValueError("This control is unavailable for the current source or speaker.")
    value = body.get("value")
    if name == "volume" and (type(value) not in (int, float) or not 0 <= value <= 100):
        raise ValueError("Choose a speaker volume from 0 to 100.")
    if name in {"play", "next", "previous"} and lease.get("native_session") and not lease.get("progress_route"):
        # Resuming/advancing Spotify may request another stream. Reuse the
        # existing pin/enforcement check; never allocate for the acting profile.
        await listening.runtime.account_guard(endpoint, connection)
    fresh_house, fresh_surface, saved, _ = await listening.authorize(user, surface, person)
    fresh_connection = listening.runtime.connection()
    if not fresh_connection or fresh_house != house or any(fresh_connection.get(k) != connection[k] for k in ("server_id", "app", "generation")):
        raise ValueError(CHANGED)
    players, _ = await listening.players(fresh_house, fresh_surface, saved, person, await listening.runtime.snapshot())
    fresh_player = next((p for p in players if p["player_id"] == pid and p["entity_id"] == player["entity_id"]), None)
    if fresh_player is None:
        raise ValueError("This speaker is no longer permitted for this profile.")
    fresh, same_lease = await observe(listening, endpoint, connection, data, house, fresh_player)
    if fresh["revision"] != checked["revision"] or same_lease is not lease or name not in fresh["actions"]:
        raise ValueError(CHANGED)
    try:
        if name == "volume":
            command = "players/cmd/group_volume" if pid in data.get("groups", {}) else "players/cmd/volume_set"
            await listening.runtime.control(endpoint, connection, command, player_id=pid, volume_level=round(value))
        elif name == "pause" or name == "stop" and lease.get("kind") in {"audiobook", "podcast_episode"}:
            await listening.pause_owned(endpoint, connection, data, pid, lease)
            if name == "stop":
                if data["leases"].get(pid) is not lease:
                    raise MusicRuntimeError(CHANGED)
                await listening.runtime.control(endpoint, connection, "player_queues/stop", queue_id=pid)
        else:
            await listening.runtime.control(endpoint, connection, "player_queues/" + name, queue_id=pid)
        if name in {"play", "stop", "next", "previous"}:
            lease.pop("idle_pause_ack", None)
    except (MusicRuntimeError, TimeoutError, OSError, asyncio.CancelledError):
        lease["transport_uncertain"] = {"before": checked["revision"], "action": name, "value": round(value) if name == "volume" else None}
        raise
