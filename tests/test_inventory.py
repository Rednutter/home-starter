"""Registry relationships, conservative findings and bounded verified writes."""

import copy

import pytest
from aiohttp.test_utils import TestClient, TestServer
from conftest import core_fixture
from homestarter.core import CoreError
from homestarter.inventory import COMMANDS, assign_area, build_inventory, collect_inventory
from homestarter.server import create_app


def sources():
    values = {
        "devices": core_fixture("device_registry_list.json"),
        "entities": core_fixture("inventory_entity_registry_list.json"),
        "areas": core_fixture("area_registry_list.json"),
        "floors": core_fixture("floor_registry_list.json"),
        "states": core_fixture("api_states.json"),
        "integrations": core_fixture("config_entries_get.json"),
        "repairs": core_fixture("repairs_list_issues.json"),
    }
    return {k: {"status": "ok", "data": v} for k, v in values.items()}


def test_inventory_relationships_and_yaml_entities():
    inv = build_inventory(sources())
    kitchen = next(d for d in inv["devices"] if d["id"] == "fixture_kitchen")
    assert kitchen["entities"][0]["entity_id"] == "sensor.kitchen_temperature"
    assert kitchen["id"] in next(a for a in inv["areas"] if a["area_id"] == "kitchen")["device_ids"]
    assert inv["unattached_entities"]
    assert inv["complete"]


def test_unassigned_reasons_and_confidence():
    inv = build_inventory(sources())
    f = next(f for f in inv["findings"] if f["category"] == "needs_room")
    assert f["confidence"] == "Confirmed" and f["reasons"]
    assert f["suggestion"]["name"] == "Garage"
    assert f["suggestion"]["confidence"] == "Plausible"
    assert f["suggestion"]["reasons"]


def test_entity_room_evidence_and_conflicts():
    s = sources()
    entity = s["entities"]["data"][0]
    entity.update(device_id="fixture_garage", area_id="garage")
    second = copy.deepcopy(entity)
    second["entity_id"] = "sensor.second"
    s["entities"]["data"].append(second)
    f = next(f for f in build_inventory(s)["findings"] if f["category"] == "needs_room")
    assert f["suggestion"]["confidence"] == "High confidence"
    second["area_id"] = "kitchen"
    assert next(f for f in build_inventory(s)["findings"] if f["category"] == "needs_room")["suggestion"] is None


def test_disabled_entities_not_offline():
    s = sources()
    for e in s["entities"]["data"]:
        e["disabled_by"] = "user"
    inv = build_inventory(s)
    assert all(d["unavailable_count"] == 0 for d in inv["devices"])
    assert not any(f["category"] == "offline" for f in inv["findings"])


def test_unavailable_is_not_retired():
    inv = build_inventory(sources())
    assert any(f["category"] == "attention" for f in inv["findings"])
    assert not any(f["category"] == "offline" for f in inv["findings"])
    assert any("does not establish retired" in " ".join(f["reasons"]) for f in inv["findings"])


def test_same_names_not_duplicate():
    s = sources()
    a, b = s["devices"]["data"]
    b.update(name=a["name"], model=a["model"], manufacturer=a["manufacturer"], area_id=a["area_id"])
    assert not any(f["category"] == "duplicate" for f in build_inventory(s)["findings"])


def test_already_fine_requires_loaded_owner_and_observed_entities():
    s = sources()
    s["integrations"]["data"].append({"entry_id": "fixture_entry", "domain": "fixture_inventory", "state": "loaded", "source": "user"})
    inv = build_inventory(s)
    assert next(d for d in inv["devices"] if d["id"] == "fixture_kitchen")["status"] == "fine"
    s["integrations"]["data"][-1]["state"] = "not_loaded"
    assert next(d for d in build_inventory(s)["devices"] if d["id"] == "fixture_kitchen")["status"] == "unknown"


def test_linked_mac_and_child_namespaces():
    s = sources()
    a, b = s["devices"]["data"]
    a["connections"] = [["mac", "AA:BB:CC:DD:EE:FF"]]
    b["connections"] = [["mac", "aabbccddeeff"]]
    inv = build_inventory(s)
    assert b["id"] in inv["devices"][0]["linked_ids"]
    assert next(f for f in inv["findings"] if f["category"] == "duplicate")["confidence"] == "Plausible"
    b["parent_device_id"] = a["id"]
    sibling = copy.deepcopy(b)
    sibling["id"] = "child_sibling"
    s["devices"]["data"].append(sibling)
    inv = build_inventory(s)
    assert not any(f["category"] == "duplicate" for f in inv["findings"])
    assert sibling["id"] in inv["devices"][1]["sibling_ids"]
    assert b["id"] in inv["devices"][0]["children_ids"]


@pytest.mark.parametrize("missing", ["devices", "areas", "entities", "states", "integrations"])
def test_partial_read_never_claims_fine(missing):
    s = sources()
    s[missing] = {"status": "unavailable", "error": {"message": "not readable"}}
    inv = build_inventory(s)
    assert not inv["complete"]
    assert inv["counts"]["fine"] == 0
    assert inv["sources"][missing]["status"] == "unavailable"
    if missing == "areas":
        assert not any(f["category"] == "needs_room" for f in inv["findings"])


async def test_read_commands_only(make_env):
    env = await make_env("ready")
    inv = await collect_inventory(env.core)
    assert inv["counts"]["devices"] == 2
    assert {c["type"] for c in env.mock.ws_calls} == set(COMMANDS.values())


async def test_old_ha_without_floors_is_partial_but_useful(make_env):
    env = await make_env()
    original = env.mock._fake_ws_result

    def result(msg):
        if msg["type"] == COMMANDS["floors"]:
            raise KeyError("unknown_command")
        return original(msg)

    env.mock._fake_ws_result = result
    inv = await collect_inventory(env.core)
    assert inv["sources"]["floors"]["status"] == "unavailable"
    assert len(inv["devices"]) == 2


async def test_malformed_registry_is_isolated(make_env):
    env = await make_env()
    original = env.mock._fake_ws_result

    def result(msg):
        if msg["type"] == COMMANDS["devices"]:
            return {"unexpected": "shape"}
        return original(msg)

    env.mock._fake_ws_result = result
    inv = await collect_inventory(env.core)
    assert not inv["complete"]
    assert inv["sources"]["devices"]["status"] == "unavailable"
    assert inv["counts"]["areas"] == 5


def test_real_core_device_contract():
    s = sources()
    s["devices"]["data"] = core_fixture("captured_device_registry_list.json")
    s["floors"]["data"] = core_fixture("captured_floor_registry_list.json")
    inv = build_inventory(s)
    assert len(inv["devices"]) >= 4
    assert any(d["name"] == "Kitchen temperature" and d["area_id"] == "kitchen" for d in inv["devices"])
    parent = next(d for d in inv["devices"] if d["name"] == "Kitchen temperature")
    children = [d for d in inv["devices"] if d["parent_device_id"] == parent["id"]]
    assert len(children) == 2
    assert set(parent["children_ids"]) == {d["id"] for d in children}
    assert children[1]["id"] in children[0]["sibling_ids"]


async def test_assignment_fresh_read_verified_exact_field(make_env):
    env = await make_env()
    result = await assign_area(env.core, "fixture_kitchen", "garage", "kitchen")
    assert result["verified"]
    assert [c for c in env.mock.ws_calls if c["type"].endswith("/update")][0].keys() == {"id", "type", "device_id", "area_id"}
    assert env.mock.ws_calls[-1]["type"] == COMMANDS["devices"]
    assert (await assign_area(env.core, "fixture_kitchen", "kitchen", "garage"))["verified"]


@pytest.mark.parametrize(
    ("device", "area", "expected"), [("missing", "garage", None), ("fixture_kitchen", "missing", "kitchen"), ("fixture_kitchen", "garage", None)]
)
async def test_stale_or_missing_precondition_never_writes(make_env, device, area, expected):
    env = await make_env()
    assert not (await assign_area(env.core, device, area, expected))["verified"]
    assert not any(c["type"].endswith("/update") for c in env.mock.ws_calls)


async def test_success_response_without_changed_state_not_verified(make_env):
    env = await make_env()
    original = env.mock._fake_ws_result

    def result(msg):
        if msg["type"] == "config/device_registry/update":
            return env.mock.devices[0]
        return original(msg)

    env.mock._fake_ws_result = result
    assert not (await assign_area(env.core, "fixture_kitchen", "garage", "kitchen"))["verified"]


@pytest.fixture
async def inventory_client(make_env):
    env = await make_env("ready")
    async with TestClient(TestServer(create_app(env.settings))) as client:
        yield client, env


async def test_endpoint_inventory_and_existing_music(inventory_client):
    client, _ = inventory_client
    assert (await client.get("/api/inventory")).status == 200
    assert (await (await client.get("/api/music")).json())["verified"]


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"confirm": True},
        {"device_id": "fixture_kitchen", "area_id": "garage", "expected_area_id": "kitchen", "confirm": True, "name_by_user": "oops"},
    ],
)
async def test_write_request_validation(inventory_client, body):
    client, env = inventory_client
    resp = await client.post("/api/inventory/area", json=body, headers={"X-Remote-User-Id": env.mock.users[0]["id"]})
    assert resp.status in (400, 415)
    assert not any(c["type"].endswith("/update") for c in env.mock.ws_calls)


async def test_admin_write_and_error_handling(inventory_client):
    client, env = inventory_client
    body = {"device_id": "fixture_kitchen", "area_id": "garage", "expected_area_id": "kitchen", "confirm": True}
    assert (await client.post("/api/inventory/area", json=body)).status == 403
    assert (await client.post("/api/inventory/area", json=body, headers={"X-Remote-User-Id": "non-admin"})).status == 403
    assert (await client.post("/api/inventory/area", json=body, headers={"X-Remote-User-Id": env.mock.users[0]["id"]})).status == 200


async def test_failed_write_does_not_claim_success(inventory_client, monkeypatch):
    client, env = inventory_client

    async def fail(*args):
        raise CoreError("api", "not supported")

    monkeypatch.setattr("homestarter.server.assign_area", fail)
    resp = await client.post(
        "/api/inventory/area",
        json={"device_id": "fixture_kitchen", "area_id": "garage", "expected_area_id": "kitchen", "confirm": True},
        headers={"X-Remote-User-Id": env.mock.users[0]["id"]},
    )
    assert resp.status == 409
    assert (await resp.json())["verified"] is False
