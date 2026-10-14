"""Commission HA records without copying a registry or treating availability as placement."""

import copy
import json

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import this_house as house
from homestarter.core import CoreError
from homestarter.household import HouseholdStore
from homestarter.server import create_app


@pytest.fixture
async def env(make_env):
    env = await make_env("ready")
    env.store = HouseholdStore(env.settings.data_dir)
    return env


async def do(env, action, **body):
    return await house.act(env.core, env.store, action, {"confirm": True, "revision": house.load(env.store)["revision"], **body})


def writes(env):
    return [c for c in env.mock.ws_calls if c["type"].endswith(("/update", "/create", "/delete"))]


async def test_live_projection_is_not_a_people_or_location_database(env):
    env.mock.persons["storage"][0].update(user_id="private-account-id", picture="private-picture", device_trackers=["device_tracker.example_phone"])
    view = await house.inspect(env.core, env.store)
    assert view["complete"] and len(view["people"]) == 3
    assert view["people"][0]["trackers"] == ["device_tracker.example_phone"]
    assert not view["people"][0]["usable_tracker"]
    assert "user_id" not in json.dumps(view) and "private-picture" not in json.dumps(view)
    assert not env.store.this_house_path.exists() and not writes(env)
    assert all(d["entity_count"] > 0 for d in view["devices"])


async def test_person_confirmation_uses_live_id_and_reopens_after_native_edit(env):
    view = await house.inspect(env.core, env.store)
    person = view["people"][0]
    await do(env, "person", person_id=person["id"], expected=person["signature"], role="adult")
    assert (await house.inspect(env.core, env.store))["people"][0]["confirmed"]
    assert house.load(env.store)["people"][person["id"]] == {"role": "adult", "signature": person["signature"]}
    env.mock.persons["storage"][0]["name"] = "Example renamed adult"
    changed = (await house.inspect(env.core, env.store))["people"][0]
    assert changed["changed"] and not changed["confirmed"] and changed["role"] is None
    assert not writes(env)
    with pytest.raises(ValueError, match="person changed"):
        await do(env, "person", person_id=person["id"], expected=person["signature"], role="adult")


async def test_household_size_excludes_display_accounts_without_changing_ha_people(env):
    for p, role in zip((await house.inspect(env.core, env.store))["people"], ("adult", "child", "other"), strict=True):
        await do(env, "person", person_id=p["id"], expected=p["signature"], role=role)
    await do(env, "expectation", people=2, adults=1)
    view = await house.inspect(env.core, env.store)
    assert view["counts"]["expectation_matches"] and view["counts"]["people"] == 3
    assert view["counts"]["members"] == 2 and view["counts"]["adults"] == 1
    assert len(env.mock.persons["storage"]) == 3 and not writes(env)


async def test_placement_writes_one_field_then_verifies_preserving_ids_and_overrides(env):
    before = copy.deepcopy(env.mock.devices)
    view = await house.inspect(env.core, env.store)
    device = next(d for d in view["devices"] if d["id"] == "fixture_kitchen")
    await do(env, "placement", device_id=device["id"], expected=device["signature"], area_id="garage")
    written = writes(env)
    assert len(written) == 1 and {k: v for k, v in written[0].items() if k != "id"} == {
        "type": "config/device_registry/update",
        "device_id": "fixture_kitchen",
        "area_id": "garage",
    }
    expected = copy.deepcopy(before)
    next(d for d in expected if d["id"] == "fixture_kitchen")["area_id"] = "garage"
    assert env.mock.devices == expected
    saved = await house.inspect(env.core, env.store)
    assert next(d for d in saved["devices"] if d["id"] == device["id"])["confirmed"]
    assert not any(k in json.dumps(house.load(env.store)) for k in ("entity_id", "manufacturer", "latitude", "password"))
    next(d for d in env.mock.devices if d["id"] == device["id"])["area_id"] = "kitchen"
    assert next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == device["id"])["changed"]
    with pytest.raises(ValueError, match="changed"):
        await do(env, "placement", device_id=device["id"], expected=next(d for d in saved["devices"] if d["id"] == device["id"])["signature"], area_id="garage")
    assert len(writes(env)) == 1


async def test_confirm_existing_room_needs_no_ha_write_and_availability_is_not_confirmation(env):
    device = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == "fixture_kitchen")
    assert device["placed"] and not device["confirmed"]
    await do(env, "placement", device_id=device["id"], expected=device["signature"], area_id=device["area_id"])
    assert not writes(env)
    assert next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == device["id"])["confirmed"]


async def test_group_area_is_preserved_but_does_not_count_as_physical_placement(env):
    view = await house.inspect(env.core, env.store)
    area = next(a for a in view["areas"] if a["area_id"] == "kitchen")
    before = copy.deepcopy(env.mock.areas)
    await do(env, "area_intent", area_id=area["area_id"], kind="group", expected=area["signature"])
    fresh = await house.inspect(env.core, env.store)
    device = next(d for d in fresh["devices"] if d["id"] == "fixture_kitchen")
    assert device["needs_room"] and device["attention"] and not device["placed"]
    assert env.mock.areas == before and not writes(env)
    with pytest.raises(ValueError, match="existing room"):
        await do(env, "placement", device_id=device["id"], area_id="kitchen", expected=device["signature"])
    next(a for a in env.mock.areas if a["area_id"] == "kitchen")["name"] = "Renamed area"
    assert next(a for a in (await house.inspect(env.core, env.store))["areas"] if a["area_id"] == "kitchen")["kind"] is None


async def test_reset_preserves_physical_confirmations(env):
    await do(env, "expectation", people=5, adults=2)
    before = env.store.this_house_path.read_bytes()
    household = env.store.load()
    env.store.reset(household["revision"])
    assert env.store.this_house_path.read_bytes() == before


async def test_same_named_equipment_stays_separate_with_integration_provenance(env):
    env.mock.entries.append({"entry_id": "fixture_view", "domain": "fixture", "title": "Fixture", "state": "loaded"})
    next(d for d in env.mock.devices if d["id"] == "fixture_kitchen")["config_entries"] = ["fixture_view"]
    duplicate = copy.deepcopy(next(d for d in env.mock.devices if d["id"] == "fixture_kitchen"))
    duplicate["id"] = "fixture_second_view"
    env.mock.devices.append(duplicate)
    original_entity = next(e for e in env.mock.entity_registry if e.get("device_id") == "fixture_kitchen")
    env.mock.entity_registry.append({**original_entity, "entity_id": "light.fixture_second_view", "device_id": duplicate["id"]})
    view = await house.inspect(env.core, env.store)
    devices = [d for d in view["devices"] if d["id"] in {"fixture_kitchen", "fixture_second_view"}]
    assert len(devices) == 2 and all(d["attention"] for d in devices)
    assert all(any("share this name" in r for r in d["reasons"]) for d in devices)
    assert all(d["integrations"] for d in devices)
    assert not writes(env)


async def test_success_without_readback_does_not_persist_confirmation(env):
    view = await house.inspect(env.core, env.store)
    device = next(d for d in view["devices"] if d["id"] == "fixture_kitchen")
    original = env.mock._fake_ws_result

    def no_change(msg):
        if msg["type"] == "config/device_registry/update":
            return {}
        return original(msg)

    env.mock._fake_ws_result = no_change
    with pytest.raises(ValueError, match="not confirmed"):
        await do(env, "placement", device_id=device["id"], expected=device["signature"], area_id="garage")
    assert not env.store.this_house_path.exists()


async def test_native_floor_and_area_changes_keep_ids_and_unrelated_metadata(env):
    view = await house.inspect(env.core, env.store)
    await do(env, "floor", id=None, name="Example floor", level=None, expected=view["structure_signature"])
    view = await house.inspect(env.core, env.store)
    floor = view["floors"][0]
    kitchen = next(a for a in env.mock.areas if a["area_id"] == "kitchen")
    before = copy.deepcopy(kitchen)
    await do(env, "area", id="kitchen", name="Example kitchen", floor_id=floor["floor_id"], expected=view["structure_signature"])
    assert kitchen == {**before, "name": "Example kitchen", "floor_id": floor["floor_id"]}
    view = await house.inspect(env.core, env.store)
    await do(env, "structure", expected=view["structure_signature"])
    assert (await house.inspect(env.core, env.store))["structure_confirmed"]
    env.mock.areas[0]["name"] = "Example external change"
    assert not (await house.inspect(env.core, env.store))["structure_confirmed"]
    with pytest.raises(ValueError, match="changed"):
        await do(env, "area", id=None, name="Example room", floor_id=None, expected=view["structure_signature"])
    assert not any(c["type"].endswith("/delete") for c in writes(env))


async def test_duplicate_room_names_and_unknown_floors_are_rejected_before_write(env):
    view = await house.inspect(env.core, env.store)
    for name, floor in (("Kitchen", None), ("Example room", "missing")):
        with pytest.raises(ValueError):
            await do(env, "area", id=None, name=name, floor_id=floor, expected=view["structure_signature"])
    assert not writes(env)


async def test_physical_note_retained_on_return_but_not_ha_registry(env):
    device = (await house.inspect(env.core, env.store))["devices"][0]
    await do(env, "relationship", device_id=device["id"], expected=device["signature"], text="Feeds the existing shared speaker system")
    fresh_store = HouseholdStore(env.settings.data_dir)
    assert next(d for d in (await house.inspect(env.core, fresh_store))["devices"] if d["id"] == device["id"])["relationship"]
    assert not writes(env)


async def test_room_rename_reopens_placement_without_reassigning_the_device(env):
    device = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == "fixture_kitchen")
    await do(env, "placement", device_id=device["id"], expected=device["signature"], area_id=device["area_id"])
    next(a for a in env.mock.areas if a["area_id"] == device["area_id"])["name"] = "Example different room"
    changed = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == device["id"])
    assert changed["changed"] and not changed["confirmed"] and not writes(env)


async def test_shared_groups_and_explicit_portable_intent_do_not_need_fixed_rooms(env):
    raw = next(d for d in env.mock.devices if d["id"] == "fixture_kitchen")
    raw["area_id"] = None
    device = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == raw["id"])
    assert device["needs_room"]
    await do(env, "portable", device_id=device["id"], expected=device["signature"])
    device = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == raw["id"])
    assert device["portable"] and not device["needs_room"] and raw["area_id"] is None
    raw["model"] = "Google Cast Group"
    device = next(d for d in (await house.inspect(env.core, env.store))["devices"] if d["id"] == raw["id"])
    assert device["shared"] and not device["needs_room"] and not writes(env)


async def test_partial_person_read_keeps_saved_intent_and_blocks_writes(env):
    await do(env, "expectation", people=2, adults=1)
    original = env.mock._fake_ws_result

    def failed(msg):
        if msg["type"] == "person/list":
            raise KeyError("Unavailable fixture")
        return original(msg)

    env.mock._fake_ws_result = failed
    view = await house.inspect(env.core, env.store)
    assert not view["complete"] and view["people_error"]
    with pytest.raises(ValueError, match="completely"):
        await do(env, "expectation", people=3, adults=1)
    assert house.load(env.store)["expectation"] == {"people": 2, "adults": 1}


async def test_corrupt_confirmations_fail_closed_and_existing_setup_is_untouched(env):
    before = env.store.load()
    env.store.this_house_path.write_text('{"version":99}')
    with pytest.raises(ValueError, match="preserved"):
        await house.inspect(env.core, env.store)
    assert env.store.load() == before and not writes(env)


async def test_actions_require_admin_confirmation_revision_and_exact_fields(make_env):
    env = await make_env("ready")
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/house")).status == 403
        assert (await client.get("/api/house", headers={"X-Remote-User-Id": "non-admin"})).status == 403
        assert (await client.get("/api/house", headers=headers)).status == 200
        valid = {"confirm": True, "revision": 0, "people": 2, "adults": 1}
        for body in ({**valid, "confirm": False}, {**valid, "revision": True}, {**valid, "unknown": "forbidden"}, {**valid, "revision": 2}):
            assert (await client.post("/api/house/expectation", json=body, headers=headers)).status == 409
        assert (await client.post("/api/house/expectation", json=valid, headers=headers)).status == 200
        assert not any(c["type"].endswith(("/create", "/update")) for c in env.mock.ws_calls)
        assert (await client.post("/api/house/delete", json={**valid, "revision": 1}, headers=headers)).status == 409


async def test_api_connection_failure_reports_uncertain_write_without_exception_details(make_env, monkeypatch):
    env = await make_env("ready")
    async with TestClient(TestServer(create_app(env.settings))) as client:

        async def fail(*args):
            raise CoreError("api", "private fixture failure")

        monkeypatch.setattr(house, "inspect", fail)
        response = await client.get("/api/house", headers={"X-Remote-User-Id": env.mock.users[0]["id"]})
        assert response.status == 503 and "private fixture" not in await response.text()
