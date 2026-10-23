"""Synthetic recipe plans, never live queues or proof of whole-catalogue access."""

import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from homestarter import stations

SPEC = {"name": "Example station", "seeds": ["Example"], "artist_gap": 2, "track_gap_days": 1}


def track(key, artist=None, **extra):
    return {
        "item_id": key,
        "media_type": "track",
        "name": "Example " + key,
        "provider": "fixture_catalogue",
        "uri": "fixture_catalogue://track/" + key,
        "artists": [{"item_id": artist or "artist-" + key, "name": "Example artist"}],
        "metadata": {"explicit": False},
        "provider_mappings": [{"provider_instance": "fixture_catalogue", "provider_domain": "fixture", "item_id": key, "available": True}],
        **extra,
    }


def gateway(rows):
    return {"provider": "fixture_catalogue", "domain": "fixture", "coverage": "provider", "search": AsyncMock(return_value=rows)}


async def test_recipe_restart_regenerates_fresh_queue_and_preserves_upstream_identity():
    rows = [track(str(i)) for i in range(20)]
    # Same titles are distinct; an identical upstream ID is one candidate.
    for row in rows:
        row["name"] = "Same title"
    source = gateway([*rows, deepcopy(rows[0])])
    first = await stations.plan(SPEC, source, [], [], {}, 1, 100)
    history = [{"key": r["key"], "artists": r["artists"], "at": 100} for r in first["items"]]
    saved = json.loads(json.dumps(stations.recipe(SPEC)))
    second = await stations.plan(saved, source, history, [], {}, 2, 101)
    assert len(first["items"]) == len(second["items"]) == 5
    assert not {r["key"] for r in first["items"]} & {r["key"] for r in second["items"]}
    assert "items" not in saved and "queue" not in saved
    assert source["search"].await_count == 2
    repeated = await stations.plan(saved, gateway(list(reversed(rows))), history, [], {}, 2, 101)
    assert [r["key"] for r in second["items"]] == [r["key"] for r in repeated["items"]]


async def test_repeat_windows_artist_gap_and_sparse_exhaustion_never_relax():
    source = gateway([track("one", "same"), track("two", "same")])
    result = await stations.plan(SPEC, source, [], [], {}, 1, 100)
    assert result["state"] == "partial" and len(result["items"]) == 1
    selected = result["items"][0]
    history = [{"key": selected["key"], "artists": selected["artists"], "at": 100}]
    exhausted = await stations.plan(SPEC, source, history, [], {}, 2, 101)
    assert exhausted["state"] == "exhausted" and not exhausted["items"]
    # Track exclusion expires; the artist gap still counts subsequent selections.
    history += [{"key": "other-" + str(i), "artists": ["other-artist-" + str(i)], "at": 102 + i} for i in range(3)]
    later = await stations.plan(SPEC, source, history, [], {}, 3, 100 + 86401, count=1)
    assert later["items"]


@pytest.mark.parametrize("scope", ["session", "station", "profile"])
async def test_more_less_never_are_scoped_and_persist_without_silent_unblock(scope):
    row = track("preferred")
    selected = stations.identity(row, "fixture_catalogue")
    profile = {}
    stations.steer(profile, "one", "run", selected, "more", scope)
    feedback = stations.feedback_state(profile, "one", "run")
    result = await stations.plan(SPEC, gateway([row, track("other")]), [], feedback, {}, 1, 100, count=1)
    assert result["items"][0]["key"] == selected["key"]
    for _ in range(3):
        stations.steer(profile, "one", "run", selected, "less", scope)
    result = await stations.plan(SPEC, gateway([row, track("other")]), [], stations.feedback_state(profile, "one", "run"), {}, 1, 100, count=1)
    assert result["items"][0]["key"] != selected["key"]
    stations.steer(profile, "one", "run", selected, "never", scope)
    stations.steer(profile, "one", "run", selected, "more", scope)
    restored = json.loads(json.dumps(profile))
    result = await stations.plan(SPEC, gateway([row]), [], stations.feedback_state(restored, "one", "run"), {}, 2, 100, explicit=selected["key"])
    assert result["state"] == "exhausted"
    assert bool(stations.feedback_state(restored, "other", "other-run")) == (scope == "profile")
    if scope == "session":
        assert not stations.feedback_state(restored, "one", "new-run")
    if scope == "station":
        assert stations.feedback_state(restored, "one", "new-run")


async def test_context_is_weighting_and_explicit_request_wins_without_policy_bypass():
    calm = track("calm", metadata={"genres": ["ambient"], "explicit": False})
    upbeat = track("upbeat", metadata={"genres": ["upbeat"], "explicit": False})
    source = gateway([calm, upbeat])
    morning = await stations.plan(SPEC, source, [], [], {"hour": 7, "weekday": 0}, 1, 100, count=1)
    night = await stations.plan(SPEC, source, [], [], {"hour": 22, "weekday": 0}, 1, 100, count=1)
    assert morning["items"][0]["item_id"] == "upbeat" and night["items"][0]["item_id"] == "calm"
    chosen = await stations.plan(SPEC, source, [], [], {"hour": 7, "weekday": 0}, 1, 100, count=1, explicit="fixture:calm")
    assert chosen["items"][0]["item_id"] == "calm"
    assert stations.context_score(calm, {}, False) == 0
    unsafe = track("unsafe", metadata={"explicit": None})
    result = await stations.plan(SPEC, gateway([unsafe]), [], [], {}, 1, 100, explicit="fixture:unsafe", restricted=True)
    assert not result["items"]


async def test_catalogue_failures_and_unreserved_spotify_never_fall_back_or_select_other_identity():
    source = gateway([track("one")])
    source["domain"] = "spotify"
    with pytest.raises(ValueError, match="pinned account"):
        await stations.plan(SPEC, source, [], [], {}, 1, 100)
    source["reserved"] = True  # A caller-supplied boolean is not the real allocator.
    with pytest.raises(ValueError, match="pinned account"):
        await stations.plan(SPEC, source, [], [], {}, 1, 100)
    source["search"].assert_not_awaited()
    source["domain"] = "fixture"
    source["search"].side_effect = RuntimeError("Synthetic private provider failure")
    result = await stations.plan(SPEC, source, [], [], {}, 1, 100)
    assert result["state"] == "provider_unavailable" and not result["items"]
    assert "private provider failure" not in str(result)
    other = track("other")
    other["provider_mappings"][0]["provider_instance"] = "renae-personal"
    result = await stations.plan(SPEC, gateway([other]), [], [], {}, 1, 100)
    assert not result["items"]


async def test_explicit_seed_genre_and_era_outweigh_default_context():
    calm = track("calm", year=1995, metadata={"genres": ["ambient"], "explicit": False})
    other = track("upbeat", year=2020, metadata={"genres": ["upbeat"], "explicit": False})
    result = await stations.plan({**SPEC, "genres": ["ambient"], "era": 1990}, gateway([calm, other]), [], [], {"hour": 7, "weekday": 0}, 1, 100, count=1)
    assert result["items"][0]["item_id"] == "calm"


def test_recipe_validation_does_not_accept_payloads_credentials_or_invent_defaults():
    for value in ({"name": "Blank"}, {**SPEC, "seeds": ["https://fixture.invalid/credential"]}, {**SPEC, "playback": True}, {**SPEC, "artist_gap": -1}):
        with pytest.raises(ValueError):
            stations.recipe(value)
