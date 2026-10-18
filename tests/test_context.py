"""Synthetic chronology, explicit household knowledge and native publication boundaries."""

import copy
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import context as c
from homestarter import context_runtime as runtime
from homestarter import readiness as r
from homestarter.core import CoreError
from homestarter.household import HouseholdStore
from homestarter.inventory import collect_inventory
from homestarter.server import create_app
from homestarter.surfaces import classify, generate

ZONE = "Australia/Sydney"
NOW = datetime(2026, 6, 8, 7, 0, tzinfo=ZoneInfo(ZONE))


def event(title="Example commitment", start=None, minutes=60):
    start = start or NOW + timedelta(hours=2)
    return {"summary": title, "start": {"dateTime": start.isoformat()}, "end": {"dateTime": (start + timedelta(minutes=minutes)).isoformat()}}


def build(raw, now=NOW, settings=None, people=None):
    events, invalid = c.parse_events(raw, "example-source-identity", ZONE)
    assert invalid == 0
    return c.build(events, now, ZONE, settings or c.empty(), people or {})


@pytest.mark.parametrize("days,bucket", [(0, "near"), (1, "ahead"), (7, "ahead"), (20, "ahead"), (22, None)])
def test_temporal_horizon(days, bucket):
    result = build([event(start=NOW + timedelta(days=days, hours=1))])
    assert ("Example commitment" in result.get(bucket, "")) if bucket else "Example commitment" not in str(result)


def test_ongoing_and_elapsed_schedule_are_distinct_from_done():
    result = build([event("Ongoing", NOW - timedelta(minutes=20)), event("Elapsed", NOW - timedelta(hours=2))])
    assert "### Now · Ongoing" in result["near"] and "Elapsed" not in str(result)
    assert "done" not in str(result).lower()


def test_all_day_end_is_exclusive_and_local_day_is_not_utc_day():
    raw = {"summary": "Example all day", "start": {"date": "2026-06-08"}, "end": {"date": "2026-06-09"}}
    assert "All day" in build([raw])["near"]
    assert "Example all day" not in str(build([raw], NOW.replace(day=9, hour=0)))
    midnight = datetime(2026, 6, 8, 23, 30, tzinfo=UTC)
    assert "Example commitment" in build([event(start=midnight)], NOW.replace(hour=23))["ahead"]


@pytest.mark.parametrize("raw", [None, {}, "calendar"])
def test_bad_calendar_envelope_fails(raw):
    with pytest.raises(ValueError):
        c.parse_events(raw, "source", ZONE)


@pytest.mark.parametrize(
    "broken", [{}, None, {"summary": "x"}, {"summary": "x", "start": {}, "end": {}}, event(start=NOW.replace(tzinfo=None)), event(minutes=-1)]
)
def test_malformed_events_do_not_become_context(broken):
    parsed, invalid = c.parse_events([broken], "source", ZONE)
    assert not parsed and invalid == 1


def test_dst_all_day_interval_uses_local_calendar_dates():
    raw = {"summary": "Example DST day", "start": {"date": "2026-10-04"}, "end": {"date": "2026-10-05"}}
    events, invalid = c.parse_events([raw], "source", ZONE)
    assert invalid == 0
    assert events[0]["end"].astimezone(UTC) - events[0]["start"].astimezone(UTC) == timedelta(hours=23)


@pytest.mark.parametrize("hour,phase", [(6, "morning"), (11, "daytime"), (17, "afternoon"), (22, "night"), (2, "night")])
def test_time_context_never_infers_occupancy(hour, phase):
    result = build([], NOW.replace(hour=hour))
    assert result["phase"] == phase and "empty" not in str(result)


def test_busy_morning_and_quiet_periods_use_same_horizon_with_different_density():
    future = [event(f"Future {d}", NOW + timedelta(days=d)) for d in range(1, 20)]
    busy = build([event(f"Today {n}", NOW + timedelta(hours=n)) for n in range(1, 5)] + future)
    quiet = build(future)
    evening = build(future, NOW.replace(hour=21))
    assert busy["today_count"] == 4 and busy["ahead_count"] == 2
    assert quiet["ahead_count"] == evening["ahead_count"] == 14
    assert "No more scheduled today" in evening["near"]
    assert build(future, NOW.replace(day=7))["ahead_count"] == 14  # Weekend is chronology, not guessed school.


@pytest.mark.parametrize(
    "rounding,travel,margin,routine,expected",
    [
        (5, 17, 0, None, "08:40"),
        (5, 12, 0, None, "08:45"),
        (10, 12, 0, None, "08:40"),
        (5, 20, 5, None, "08:35"),
        (5, 7, 0, "08:10", "08:10"),
        (10, None, 0, "08:13", "08:10"),
        (5, None, 0, None, None),
        (5, 10, 0, "10:00", None),
    ],
)
def test_departure_is_explicit_conservative_and_respects_earlier_routine(rounding, travel, margin, routine, expected):
    choice = {"travel_minutes": travel, "buffer_minutes": margin, "round_minutes": rounding, "routine_time": routine}
    result = c.departure(NOW.replace(hour=9), choice)
    assert (result.strftime("%H:%M") if result else None) == expected


def test_departure_rounds_seconds_and_previous_day_earlier():
    start = NOW.replace(hour=0, minute=3, second=40)
    result = c.departure(start, {"travel_minutes": 7, "buffer_minutes": 0, "round_minutes": 5, "routine_time": None})
    assert result.day == start.day - 1 and result.strftime("%H:%M:%S") == "23:55:00"


def rule():
    return {"id": "example_rule", "text": "Bring the required kit", "people": ["alex"], "start": "2026-06-01", "end": "2026-06-30", "weekdays": [0]}


@pytest.mark.parametrize(
    "changed,expected",
    [({}, True), ({"start": "2026-06-09"}, False), ({"end": "2026-06-07"}, False), ({"weekdays": [1]}, False), ({"people": ["unknown"]}, False)],
)
def test_rule_date_weekday_and_explicit_person_applicability(changed, expected):
    settings = {"rules": [{**rule(), **changed}], "events": {}}
    assert ("required kit" in build([], settings=settings, people={"alex": "Alex"})["near"]) is expected
    assert "required kit" not in build([], NOW.replace(hour=12), settings, {"alex": "Alex"})["near"]


def test_links_use_source_identity_and_exact_occurrence_not_names():
    raw = event("Same title")
    a, _ = c.parse_events([raw], "first-identity", ZONE)
    b, _ = c.parse_events([raw], "changed-identity", ZONE)
    settings = {"rules": [], "events": {a[0]["key"]: {"people": ["alex"], "travel_minutes": 12, "buffer_minutes": 0, "round_minutes": 5, "routine_time": None}}}
    assert "Alex" in c.build(a, NOW, ZONE, settings, {"alex": "Alex"})["near"]
    assert "Alex" not in c.build(b, NOW, ZONE, settings, {"alex": "Alex"})["near"]
    assert "Alex" not in c.build(a, NOW, ZONE, settings, {})["near"]


def test_untrusted_titles_cannot_inject_links_or_html():
    result = build([event("<img src=x> [Open](https://example.com) **fake**")])
    assert "<img" not in result["near"] and "[Open](" not in result["near"] and "**fake**" not in result["near"]


def test_readiness_migration_is_lazy_and_preserves_choices_and_future_state(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.load()
    old = r.empty(house["epoch"])
    del old["context"]
    old["version"] = 1
    old["choices"] = {"music": {"intent": "later"}}
    store.write(store.readiness_path, old)
    loaded = r.load(store, house)
    assert loaded["version"] == 2 and loaded["choices"] == old["choices"] and loaded["context"] == c.empty()
    assert store.read(store.readiness_path, {}) == old
    store.write(store.readiness_path, {**loaded, "version": 99})
    with pytest.raises(ValueError):
        r.load(store, house)


async def configured(make_env):
    env = await make_env("ready")
    source = "calendar.example_context"
    env.mock.entity_registry.append({"entity_id": source, "platform": "local_calendar", "name": "Example calendar", "device_id": None})
    env.mock.activity_states[source] = {"entity_id": source, "state": "off", "attributes": {}}
    env.mock.calendar_events[source] = [event(start=datetime.now(UTC) + timedelta(hours=2))]
    store = HouseholdStore(env.settings.data_dir)
    house = store.load()
    house["surfaces"] = [{"id": "example_wall", "name": "Example wall", "profile": "wall", "person_id": None, "area_id": None, "audience": "everyone"}]
    house = store.save(house)
    inv = await collect_inventory(env.core)
    saved = r.empty(house["epoch"])
    saved["choices"]["calendars"] = {"intent": "wanted", "sources": [source], "screens": ["example_wall"], "answers": {}, "permissions": {}}
    saved["verified"]["calendars"] = {"at": datetime.now(UTC).isoformat(), "signature": r.selection_signature(saved["choices"]["calendars"], inv)}
    store.write(store.readiness_path, saved)
    return env, store, house, saved, source


@pytest.mark.parametrize("failure", ["expired", "identity", "unavailable", "no_source", "malformed", "excluded"])
async def test_unverified_or_missing_calendar_never_reuses_event_payload(make_env, failure):
    env, store, house, saved, source = await configured(make_env)
    assert "Example commitment" in (await runtime.inspect(env.core, store, house["surfaces"][0]))["near"] + (await runtime.inspect(env.core, store))["ahead"]
    if failure == "expired":
        saved["verified"]["calendars"]["at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    elif failure == "identity":
        env.mock.entity_registry[-1]["id"] = "replacement_identity"
    elif failure == "unavailable":
        env.mock.activity_states[source]["state"] = "unavailable"
    elif failure == "no_source":
        saved["choices"].clear()
    elif failure == "malformed":
        env.mock.calendar_events[source] = [{}]
    else:
        house["preferences"] = {"surface:example_wall": {"pin": [], "hide": [source], "order": []}}
        house = store.save(house)
    store.write(store.readiness_path, saved)
    view = await runtime.inspect(env.core, store, house["surfaces"][0])
    assert "Example commitment" not in view["near"] + view["ahead"] and view["issues"]


async def test_context_admin_save_reload_preserves_proofs_and_rejects_stale_writes(make_env):
    env, store, house, saved, _ = await configured(make_env)
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/context")).status == 403
        view = await (await client.get("/api/context", headers=headers)).json()
        settings = {"rules": [{**rule(), "people": []}], "events": {}}
        body = {"revision": view["revision"], "epoch": view["epoch"], "settings": settings}
        response = await client.post("/api/context", headers=headers, json=body)
        assert response.status == 200
        assert (await (await client.get("/api/context", headers=headers)).json())["settings"] == settings
        assert (await client.post("/api/context", headers=headers, json=body)).status == 409
    assert r.load(store, house)["verified"] == saved["verified"]
    assert store.load() == house and not store.this_house_path.exists()
    assert not any("/states/sensor.home_starter_context_" in path for _, path in env.mock.calls)


async def test_wall_sessions_require_admin_current_epoch_and_remain_ephemeral(make_env):
    env, store, house, _, _ = await configured(make_env)
    before = store.read(store.readiness_path, {})
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        path = "/api/wall/example_wall/session"
        body = {"epoch": house["epoch"], "session": {"kind": "recipe", "title": "Dinner", "body": "Roast vegetables", "seconds": 30}}
        assert (await client.post(path, json=body)).status == 403
        assert (await client.post(path, headers=headers, json={**body, "epoch": house["epoch"] + 1})).status == 409
        reply = await client.post(path, headers=headers, json=body)
        assert reply.status == 200
        assert (await reply.json())["display_session"]["title"] == "Dinner"
        assert (await (await client.get("/api/wall/example_wall", headers=headers)).json())["display_session"]
        assert (await client.post(path, headers=headers, json={"epoch": house["epoch"], "session": None})).status == 200
        assert not (await (await client.get("/api/wall/example_wall", headers=headers)).json())["display_session"]
    assert store.read(store.readiness_path, {}) == before
    assert not any("Roast vegetables" in p.read_text() for p in store.path.parent.glob("*.json"))


async def test_session_memory_expires_even_without_a_published_wall(make_env):
    env, store, house, _, _ = await configured(make_env)
    now = datetime.now(UTC)
    for key, epoch, expires in (
        ("example_wall", house["epoch"], now - timedelta(seconds=1)),
        ("example_wall", house["epoch"] + 1, now + timedelta(seconds=60)),
        ("removed_wall", house["epoch"], now + timedelta(seconds=60)),
    ):
        sessions = {key: {"epoch": epoch, "content": {"expires_at": expires.isoformat(), "body": "Temporary answer"}}}
        await runtime.update(env.core, store, sessions)
        assert not sessions


async def test_wall_updates_only_after_explicit_publication_and_stops_on_external_edit(make_env):
    env, store, house, _, _ = await configured(make_env)
    await runtime.update(env.core, store)
    entity = c.entity_id("example_wall")
    assert entity not in env.mock.activity_states
    inv = await collect_inventory(env.core)
    generated = generate(house, house["surfaces"][0], classify(inv, await env.core.states(), {}), inv["areas"])
    path = generated["url_path"]
    env.mock.dashboard_configs[path] = generated["config"]
    store.write(store.publication_path, {path: {"fingerprint": generated["fingerprint"], "context": 1, "context_epoch": house["epoch"]}})
    await runtime.update(env.core, store)
    assert "Example commitment" in str(env.mock.activity_states[entity])
    previous = copy.deepcopy(env.mock.activity_states[entity])
    env.mock.dashboard_configs[path]["title"] = "Edited outside Home Starter"
    await runtime.update(env.core, store)
    assert env.mock.activity_states[entity] == previous
    with pytest.raises(ValueError):
        await env.core.context_state("light.example", {})
    env.mock.dashboard_configs[path] = generated["config"]
    env.mock.activity_states[entity]["attributes"]["home_starter_context"] = {"surface": "someone_else"}
    with pytest.raises(CoreError):
        await runtime.update(env.core, store)


@pytest.mark.parametrize("hours,expected", [(-2, "elapsed"), (-0.5, "now"), (2, "later_today"), (26, "tomorrow"), (50, "next_few_days"), (170, "coming_weeks")])
def test_explicit_proximity_categories(hours, expected):
    events, _ = c.parse_events([event(start=NOW + timedelta(hours=hours))], "source", ZONE)
    assert c.proximity(events[0], NOW) == expected


def test_fall_back_fold_is_compared_by_real_instant():
    before = datetime(2026, 4, 5, 2, 40, tzinfo=ZoneInfo(ZONE), fold=0)
    later = datetime(2026, 4, 5, 2, 20, tzinfo=ZoneInfo(ZONE), fold=1)
    events, _ = c.parse_events([event(start=later)], "source", ZONE)
    assert c.proximity(events[0], before) == "later_today"
    choice = {"travel_minutes": 20, "buffer_minutes": 0, "round_minutes": 5, "routine_time": None}
    assert c.departure(later, choice).astimezone(UTC) == later.astimezone(UTC) - timedelta(minutes=20)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v.update(extra="unrecognised"),
        lambda v: v["rules"].append({**rule(), "end": "2026-05-01"}),
        lambda v: v["rules"].append({**rule(), "people": [{}]}),
        lambda v: v["rules"].append({**rule(), "weekdays": [True]}),
        lambda v: v["events"].update({"not-a-current-event": {}}),
    ],
)
def test_corrupt_context_choices_fail_closed(mutate):
    value = c.empty()
    mutate(value)
    with pytest.raises(ValueError):
        c.validate(value)


async def test_context_save_invalidates_preview_and_publication_enables_owned_sink(make_env):
    env, store, house, _, _ = await configured(make_env)
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        preview = await (await client.get("/api/surfaces/example_wall/preview", headers=headers)).json()
        assert "context_preview" in preview
        assert c.entity_id("example_wall") not in env.mock.activity_states
        view = await (await client.get("/api/context", headers=headers)).json()
        body = {"revision": view["revision"], "epoch": view["epoch"], "settings": {"rules": [{**rule(), "people": []}], "events": {}}}
        assert (await client.post("/api/context", json=body, headers=headers)).status == 200
        publish = "/api/surfaces/example_wall/publish"
        assert (await client.post(publish, headers=headers, json={"preview_token": preview["preview_token"], "confirm": True})).status == 409
        preview = await (await client.get("/api/surfaces/example_wall/preview", headers=headers)).json()
        response = await client.post(publish, headers=headers, json={"preview_token": preview["preview_token"], "confirm": True})
        assert response.status == 200
        result = await response.json()
        assert result["context"] == 1 and result["context_epoch"] == house["epoch"]
        assert c.entity_id("example_wall") in env.mock.activity_states
    # Event contents are not copied into private readiness persistence.
    assert "Example commitment" not in store.readiness_path.read_text()
    assert store.load() == house


async def test_reset_requires_fresh_explicit_wall_publication(make_env):
    env, store, house, _, _ = await configured(make_env)
    inv = await collect_inventory(env.core)
    generated = generate(house, house["surfaces"][0], classify(inv, await env.core.states(), {}), inv["areas"])
    path = generated["url_path"]
    env.mock.dashboard_configs[path] = generated["config"]
    store.write(store.publication_path, {path: {"fingerprint": generated["fingerprint"], "context": 1, "context_epoch": house["epoch"]}})
    await runtime.update(env.core, store)
    entity = c.entity_id("example_wall")
    previous = copy.deepcopy(env.mock.activity_states[entity])
    fresh = store.reset(house["revision"])
    fresh["surfaces"] = house["surfaces"]
    store.save(fresh)
    await runtime.update(env.core, store)
    assert env.mock.activity_states[entity] == previous


async def test_concurrent_opt_out_does_not_publish_previous_read(make_env, monkeypatch):
    env, store, house, _, _ = await configured(make_env)
    inv = await collect_inventory(env.core)
    generated = generate(house, house["surfaces"][0], classify(inv, await env.core.states(), {}), inv["areas"])
    path = generated["url_path"]
    env.mock.dashboard_configs[path] = generated["config"]
    store.write(store.publication_path, {path: {"fingerprint": generated["fingerprint"], "context": 1, "context_epoch": house["epoch"]}})
    inspect = runtime.inspect

    async def changed(*args, **kwargs):
        result = await inspect(*args, **kwargs)
        saved = r.load(store, store.load())
        saved["revision"] += 1
        saved["choices"]["calendars"]["intent"] = "not_wanted"
        store.write(store.readiness_path, saved)
        return result

    monkeypatch.setattr(runtime, "inspect", changed)
    await runtime.update(env.core, store)
    assert c.entity_id("example_wall") not in env.mock.activity_states


async def test_temporary_calendar_read_failure_does_not_retain_old_rows(make_env, monkeypatch):
    env, store, _, _, _ = await configured(make_env)
    await runtime.inspect(env.core, store)
    original = env.core.rest_get

    async def failed(path):
        if path.startswith("/calendars/"):
            raise CoreError("unreachable", "Synthetic read failure")
        return await original(path)

    monkeypatch.setattr(env.core, "rest_get", failed)
    view = await runtime.inspect(env.core, store)
    assert not view["events"] and "temporarily unavailable" in view["near"]
    assert "Example commitment" not in str(view)


async def test_focused_person_context_uses_explicit_native_link_and_never_clones_house(make_env, monkeypatch):
    env, store, house, saved, source = await configured(make_env)
    inv = await collect_inventory(env.core)
    states = await env.core.states()
    house["people"] = [{"id": p, "name": "Example " + p, "audience": "everyone"} for p in ("example_a", "example_b")]
    saved["members"] = {p: {"kind": "child", "rooms": [], "devices": [], "presence": ["person." + p], "access": "no"} for p in ("example_a", "example_b")}
    states += [{"entity_id": "person." + p, "state": "home", "attributes": {"id": "native_" + p}} for p in ("example_a", "example_b")]
    native = [{"id": "native_" + p, "name": "Example " + p, "confirmed": True, "role": "child"} for p in ("example_a", "example_b")]
    parsed, _ = c.parse_events(env.mock.calendar_events[source], r.selection_signature({"sources": [source]}, inv), ZONE)
    saved["context"]["events"] = {
        parsed[0]["key"]: {"people": ["native_example_a"], "travel_minutes": 10, "buffer_minutes": 0, "round_minutes": 5, "routine_time": None}
    }
    policy = r.policy_for(saved, house, inv, states)
    policy.update(presence=["person.example_a", "person.example_b"], presence_screens=["example_wall"])
    monkeypatch.setattr(r, "policy_for", lambda *args: policy)
    inputs = (house, saved, inv, states, ZONE, native)
    shared = await runtime.inspect(env.core, store, house["surfaces"][0], inputs=inputs)
    first = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_a", inputs=inputs)
    second = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_b", inputs=inputs)
    assert shared["briefing"] and first["briefing"] and not second["briefing"]
    assert "Leave by" in first["briefing"][0]["detail"]
    house["preferences"]["example_a"] = {"pin": [], "order": [], "hide": [source]}
    hidden = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_a", inputs=inputs)
    assert not hidden["briefing"]
    saved["members"]["example_a"]["presence"] = []
    missing = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_a", inputs=inputs)
    assert not missing["briefing"] and "Personal context not linked" in missing["issues"]
    assert c.entity_id("example_wall", "example_a") != c.entity_id("example_wall", "example_b") != c.entity_id("example_wall")


def test_touch_briefing_is_bounded_and_prioritizes_actionable_departure():
    raw = [event("Example later " + str(n), NOW + timedelta(hours=n + 3)) for n in range(12)] + [event("Example departure", NOW + timedelta(minutes=30))]
    events, _ = c.parse_events(raw, "fixture-source", ZONE)
    target = next(e for e in events if e["title"] == "Example departure")
    settings = {
        "rules": [],
        "events": {target["key"]: {"people": ["example"], "travel_minutes": 10, "buffer_minutes": 0, "round_minutes": 5, "routine_time": None}},
    }
    result = c.build(events, NOW, ZONE, settings, {"example": "Example person"})
    assert len(result["briefing"]) == 7 and result["briefing"][0]["title"] == "Example departure"
    assert result["briefing"][0]["detail"] == "Leave by 07:20"


async def test_scoped_publication_updates_person_projections_but_refuses_foreign_owner(make_env):
    env, store, house, _, _ = await configured(make_env)
    house["people"] = [{"id": "example_child", "name": "Example child", "audience": "everyone"}]
    house = store.save(house)
    inv = await collect_inventory(env.core)
    generated = generate(house, house["surfaces"][0], classify(inv, await env.core.states(), {}), inv["areas"])
    path = generated["url_path"]
    env.mock.dashboard_configs[path] = generated["config"]
    store.write(store.publication_path, {path: {"fingerprint": generated["fingerprint"], "context": 2, "context_epoch": house["epoch"]}})
    await runtime.update(env.core, store)
    shared = env.mock.activity_states[c.entity_id("example_wall")]
    personal_id = c.entity_id("example_wall", "example_child")
    personal = env.mock.activity_states[personal_id]
    assert shared["attributes"]["briefing"]
    assert personal["attributes"]["briefing"] == []  # No verified native Person link.
    assert personal["attributes"]["home_starter_context"]["person_id"] == "example_child"
    personal["attributes"]["home_starter_context"]["person_id"] = "another_person"
    previous = copy.deepcopy(personal)
    with pytest.raises(CoreError, match="already owned"):
        await runtime.update(env.core, store)
    assert env.mock.activity_states[personal_id] == previous


async def test_bins_do_not_displace_an_immediate_household_commitment(make_env, monkeypatch):
    env, store, house, _, source = await configured(make_env)
    now = datetime.now(UTC)
    env.mock.calendar_events[source] = [event("Immediate commitment", now - timedelta(minutes=5))]
    monkeypatch.setattr(runtime.waste, "load", lambda *args: {"confirmed": None})
    monkeypatch.setattr(
        runtime.waste, "view", lambda *args: {"configured": True, "screens": ["example_wall"], "summary": "Bins tonight", "attention": "attention"}
    )
    view = await runtime.inspect(env.core, store, house["surfaces"][0], now=now)
    assert [row["title"] for row in view["briefing"]][:2] == ["Immediate commitment", "Bins tonight"]


async def test_multiple_calendars_merge_overlap_and_map_only_explicit_person(make_env, monkeypatch):
    from homestarter import household_services

    env, store, house, saved, source = await configured(make_env)
    second = "calendar.example_school"
    env.mock.entity_registry.append({"entity_id": second, "platform": "local_calendar", "name": "Example school", "device_id": None})
    env.mock.activity_states[second] = {"entity_id": second, "state": "off", "attributes": {}}
    env.mock.calendar_events[second] = [*copy.deepcopy(env.mock.calendar_events[source]), event("School activity", datetime.now(UTC) + timedelta(hours=4))]
    house["people"] = [{"id": "example_a", "name": "Example child", "audience": "everyone"}]
    house = store.save(house)
    saved["choices"]["calendars"]["sources"].append(second)
    saved["members"] = {"example_a": {"kind": "child", "rooms": [], "devices": [], "presence": ["person.example_a"], "access": "no"}}
    inv = await collect_inventory(env.core)
    saved["verified"]["calendars"]["signature"] = r.selection_signature(saved["choices"]["calendars"], inv)
    store.write(store.readiness_path, saved)
    services = household_services.empty(house["epoch"])
    services["calendars"] = [{"entity_id": second, "category": "school", "people": ["example_a"]}]
    household_services.save(store, house, services)
    states = await env.core.states()
    states.append({"entity_id": "person.example_a", "state": "home", "attributes": {"id": "native_example_a"}})
    native = [{"id": "native_example_a", "name": "Example child", "confirmed": True, "role": "child"}]
    policy = r.policy_for(saved, house, inv, states)
    policy.update(presence=["person.example_a"], presence_screens=["example_wall"])
    monkeypatch.setattr(r, "policy_for", lambda *args: policy)
    inputs = (house, saved, inv, states, ZONE, native)
    shared = await runtime.inspect(env.core, store, house["surfaces"][0], inputs=inputs)
    personal = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_a", inputs=inputs)
    assert [e["title"] for e in shared["events"]] == ["Example commitment", "School activity"]
    assert [e["title"] for e in personal["events"]] == ["Example commitment", "School activity"]
    services = household_services.load(store, house)
    services["calendars"][0]["people"] = []
    household_services.save(store, house, services)
    assert not (await runtime.inspect(env.core, store, house["surfaces"][0], person_id="example_a", inputs=inputs))["events"]


@pytest.mark.parametrize("mode", ["show", "context", "ignore", "review", "failure", "excluded", "expired"])
async def test_native_school_path_obeys_shared_consent_identity_scope_and_failure(make_env, monkeypatch, mode):
    from homestarter import calendar_access, household_services

    env, store, house, saved, source = await configured(make_env)
    house["people"] = [{"id": "child", "name": "Fictional pupil", "audience": "everyone"}]
    house = store.save(house)
    services = household_services.empty(house["epoch"])
    services["person_links"] = {"child": "native_child"}
    services["calendars"] = [{"entity_id": source, "category": "timetable", "people": ["child"]}]
    household_services.save(store, house, services)
    choices = calendar_access.load(store, house)
    calendar_access.save(store, house, await env.core.states(), {**choices, "calendars": {source: mode if mode in calendar_access.MODES else "show"}})
    env.mock.calendar_events[source] = [event("Fictional class", NOW.replace(hour=9))]
    if mode == "failure":
        env.mock.calendar_events[source] = None
    if mode == "excluded":
        house["preferences"] = {"surface:example_wall": {"pin": [], "hide": [source], "order": []}}
        house = store.save(house)
    if mode == "expired":
        saved["verified"]["calendars"]["at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    inv = await collect_inventory(env.core)
    policy = r.policy_for(saved, house, inv, await env.core.states(), store)
    monkeypatch.setattr(r, "policy_for", lambda *args: policy)
    saved["verified"]["calendars"]["at"] = (NOW - timedelta(days=2) if mode == "expired" else NOW).isoformat()
    inputs = (house, saved, inv, await env.core.states(), ZONE, [{"id": "native_child", "name": "Fictional pupil", "role": "child", "confirmed": True}])
    result = await runtime.inspect(env.core, store, house["surfaces"][0], now=NOW, inputs=inputs)
    child = result["wall"]["school"]["children"][0]
    assert bool(child["periods"]) == (mode == "show")
    assert "Fictional class" not in str(result["wall"]["timeline"])
    assert "Fictional class" not in str(result["events"])
    personal = await runtime.inspect(env.core, store, house["surfaces"][0], person_id="child", now=NOW, inputs=inputs)
    assert personal["wall"]["school"] is None
    assert not any("Fictional class" in p.read_text() for p in store.path.parent.glob("*.json"))
