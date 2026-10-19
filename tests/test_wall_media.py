from homestarter.wall_media import now_playing


def player(key, source, **extra):
    return {"player_id": key, "name": key, "available": True, "playback_state": "playing", "active_source": source, **extra}


def queue(key, **extra):
    return {"queue_id": key, "active": True, "state": "playing", "current_item": {"media_item": {"name": "Example station", "media_type": "radio"}}, **extra}


def test_group_is_shown_once_with_station_identity_and_no_transport_payload():
    players = [
        player("family", "family", name="Family", current_media={"title": "Asset Link internal marker"}),
        player("kitchen", "family"),
        player("bedroom", "family"),
    ]
    q = queue("family")
    q["current_item"]["streamdetails"] = {"url": "https://example.invalid/private-delivery", "token": "synthetic-secret"}
    assert now_playing(players, [q, queue("family"), queue("kitchen")]) == [{"title": "Example station", "artist": "", "room": "Family"}]


def test_independent_queues_with_the_same_item_remain_distinct():
    assert len(now_playing([player("a", "a"), player("b", "b")], [queue("a"), queue("b")])) == 2


def test_only_active_playing_and_available_native_playback_is_shown():
    for changed in ({"active": False}, {"state": "paused"}, {"state": "idle"}):
        assert now_playing([player("a", "a")], [queue("a", **changed)]) == []
    assert now_playing([player("a", "a", available=False)], [queue("a")]) == []
    assert now_playing([], [queue("a")]) == []
    assert now_playing(None, []) == []


def test_tracks_show_live_metadata_without_exposing_account_or_stream_ids():
    ps = [player("a", "a", current_media={"title": "Live title", "artist": "Artist", "uri": "spotify://private"})]
    q = queue("a", current_item={"media_item": {"name": "Library title", "media_type": "track"}})
    assert now_playing(ps, [q]) == [{"title": "Live title", "artist": "Artist", "room": "a"}]
