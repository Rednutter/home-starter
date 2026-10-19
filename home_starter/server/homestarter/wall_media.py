"""Public display metadata from active MA queues, never stream URLs or credentials."""


def now_playing(players, queues):
    if not isinstance(players, list) or not isinstance(queues, list):
        return []
    players = {p["player_id"]: p for p in players if isinstance(p, dict) and isinstance(p.get("player_id"), str)}
    result = []
    seen = set()
    for queue in sorted((q for q in queues if isinstance(q, dict)), key=lambda q: str(q.get("queue_id", ""))):
        key = queue.get("queue_id")
        if not isinstance(key, str) or key in seen or queue.get("active") is not True or queue.get("state") != "playing":
            continue
        owner = players.get(key, {})
        if owner.get("synced_to") or owner.get("active_source") not in (None, key):
            continue  # A member may retain an active-looking local queue.
        members = [
            p
            for p in players.values()
            if p.get("available") is True
            and p.get("playback_state", p.get("state")) == "playing"
            and (p.get("active_source") == key or p.get("synced_to") == key or p.get("player_id") == key)
        ]
        if not members:
            continue
        seen.add(key)
        item = queue.get("current_item")
        item = item if isinstance(item, dict) else {}
        media = item.get("media_item")
        media = media if isinstance(media, dict) else {}
        current = owner.get("current_media") or members[0].get("current_media") or {}
        current = current if isinstance(current, dict) else {}
        radio = media.get("media_type", current.get("media_type")) == "radio"
        # Radio transport metadata may be an advertising marker. Prefer the
        # station's catalogue identity; never display raw streamdetails.
        title = (media.get("name") or item.get("name")) if radio else (current.get("title") or media.get("name") or item.get("name"))
        artist = "" if radio else current.get("artist", "")
        room = owner.get("name") or queue.get("display_name") or "Music"
        result.append({"title": str(title or "Playing media")[:180], "artist": str(artist or "")[:180], "room": str(room)[:120]})
    return result
