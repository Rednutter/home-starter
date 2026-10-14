"""Repeat launch, migration, reconciliation and explicit reset contracts; synthetic data only."""

from dataclasses import replace

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter.core import CoreError
from homestarter.household import HouseholdStore, empty_household
from homestarter.reconcile import acknowledge, observe
from homestarter.server import K_STATE, create_app
from homestarter.surfaces import classify, generate, publish
from test_surfaces import RULE, DashboardCore, household, inventory, items


def test_migration_is_repeat_safe_preserves_choices_and_detects_lost_settings(tmp_path):
    store = HouseholdStore(str(tmp_path))
    old = household()
    old["version"] = 1
    old.pop("configured")
    old.pop("epoch")
    old["preferences"] = {"alex": {"pin": ["light.kitchen"], "hide": ["lock.front"], "order": ["room:kitchen"]}}
    old["activities"] = [RULE]
    store.write(store.path, old)
    migrated = store.load()
    assert migrated["version"] == 2 and migrated["configured"] and migrated["epoch"] == 0
    assert all(migrated[k] == old[k] for k in old if k != "version")
    contents = store.path.read_bytes()
    assert HouseholdStore(str(tmp_path)).load() == migrated and store.path.read_bytes() == contents
    assert store.save(migrated) == migrated and store.path.read_bytes() == contents
    store.path.unlink()
    with pytest.raises(ValueError, match="missing"):
        store.load()


def test_future_or_corrupt_schema_never_becomes_first_run(tmp_path):
    store = HouseholdStore(str(tmp_path))
    value = {**empty_household(), "version": 999}
    store.write(store.path, value)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="Unsupported"):
        store.load()
    assert store.path.read_bytes() == before


def test_reset_is_explicit_and_retains_publication_ownership_and_activity_history(tmp_path):
    store = HouseholdStore(str(tmp_path))
    saved = store.save(household())
    ledger, activity = {"home-starter-phone": {"fingerprint": "fixture"}}, {"washer": {"runs_today": 1}}
    store.write(store.publication_path, ledger)
    store.write(store.activity_path, activity)
    assert store.load()["configured"]
    reset = store.reset(saved["revision"])
    assert not reset["configured"] and reset["epoch"] == 1
    assert store.read(store.publication_path, {}) == ledger and store.read(store.activity_path, {}) == activity
    assert store.read(store.reset_path, {})["household"] == saved
    with pytest.raises(ValueError, match="changed"):
        store.reset(saved["revision"])


def test_inventory_diff_persists_without_rebuilding_household_and_uses_registry_identity(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.save(household())
    inv, states = inventory()
    inv["unattached_entities"][0]["registry_id"] = "fixture-registry-identity"
    inv["complete"] = True
    initial = observe(store, house, inv, classify(inv, states, {}))
    contents = store.observation_path.read_bytes()
    assert not initial["pending"]
    assert observe(store, house, inv, classify(inv, states, {}))["revision"] == initial["revision"]
    assert contents == store.observation_path.read_bytes()
    inv["unattached_entities"][0].update(entity_id="light.renamed", name="Example renamed light")
    states[0]["entity_id"] = "light.renamed"
    changed = observe(store, house, inv, classify(inv, states, {}))
    event = changed["pending"]["entity:fixture-registry-identity"]
    assert event["category"] == "renamed" and event["before"]["entity_id"] == "light.kitchen"
    assert store.load() == house
    assert observe(store, house, inv, classify(inv, states, {}))["pending"] == changed["pending"]
    inv["unattached_entities"][0]["state"] = "unavailable"
    states[0]["state"] = "unavailable"
    changed = observe(store, house, inv, classify(inv, states, {}))
    assert changed["pending"]["entity:fixture-registry-identity"]["category"] == "renamed"
    assert changed["pending"]["entity:fixture-registry-identity"]["before"]["entity_id"] == "light.kitchen"
    acknowledge(store, house, changed["revision"])
    assert not observe(store, house, inv, classify(inv, states, {}))["pending"]
    before = store.observation_path.read_bytes()
    partial = observe(store, house, {**inv, "complete": False}, [])
    assert not partial["complete"] and before == store.observation_path.read_bytes()


def test_new_missing_capability_changes_are_reviewed_without_mutating_choices(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.save(household())
    inv, states = inventory()
    inv["complete"] = True
    observe(store, house, inv, classify(inv, states, {}))
    added = {"entity_id": "light.new", "name": "Example light", "state": "off", "observed": True}
    inv["unattached_entities"].append(added)
    states.append({"entity_id": "light.new", "state": "off", "attributes": {}})
    changed = observe(store, house, inv, classify(inv, states, {}))
    assert changed["pending"]["entity:light.new"]["category"] == "new"
    with pytest.raises(ValueError, match="changed"):
        acknowledge(store, house, changed["revision"] - 1)
    climate = next(s for s in states if s["entity_id"] == "climate.kitchen")
    climate["attributes"]["supported_features"] = 9
    inv["unattached_entities"] = [e for e in inv["unattached_entities"] if e["entity_id"] != "light.bedroom"]
    changed = observe(store, house, inv, classify(inv, states, {}))
    assert changed["pending"]["entity:climate.kitchen"]["category"] == "capability"
    assert changed["pending"]["entity:light.bedroom"]["category"] == "missing"
    assert store.load() == house


def test_large_inventory_review_does_not_silently_drop_changes(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.save(household())
    inv, states = inventory()
    inv["complete"] = True
    observe(store, house, inv, classify(inv, states, {}))
    for index in range(300):
        entity_id = f"light.example_{index}"
        inv["unattached_entities"].append({"entity_id": entity_id, "name": f"Example light {index}", "state": "off", "observed": True})
        states.append({"entity_id": entity_id, "state": "off", "attributes": {}})
    changed = observe(store, house, inv, classify(inv, states, {}))
    assert len(changed["pending"]) == 300
    assert len(observe(store, house, inv, classify(inv, states, {}))["pending"]) == 300


async def test_repeated_publication_is_a_verified_noop_without_duplicate_or_save():
    core = DashboardCore()
    house = household()
    config = generate(house, house["surfaces"][0], items(), inventory()[0]["areas"])
    result = await publish(core, config, None, {})
    records = {result["url_path"]: result}
    for _ in range(3):
        start = len(core.calls)
        assert await publish(core, config, result["fingerprint"], records) == result
        assert not any(kind in ("lovelace/config/save", "lovelace/dashboards/create") for kind, _ in core.calls[start:])
    assert len(core.dashboards) == 1


async def test_first_second_launch_restart_and_explicit_reset_api(make_env, tmp_path):
    env = await make_env("ready")
    settings = replace(env.settings, data_dir=str(tmp_path))
    headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}

    async def client():
        result = TestClient(TestServer(create_app(settings, env.session)))
        await result.start_server()
        return result

    first = await client()
    try:
        initial = await (await first.get("/api/installation", headers=headers)).json()
        assert initial["first_run"] and not (tmp_path / "household.json").exists()
        body = {"confirm": True, "revision": initial["revision"]}
        assert (await first.post("/api/installation/complete", json=body, headers=headers)).status == 409
        # Historical saved installations migrate into maintenance; new installs
        # use commissioning review/Go (covered by test_commissioning).
        HouseholdStore(str(tmp_path)).save(HouseholdStore(str(tmp_path)).load())
        assert not (await (await first.get("/api/installation", headers=headers)).json())["first_run"]
    finally:
        await first.close()
    store = HouseholdStore(str(tmp_path))
    house = household()
    house["revision"] = store.load()["revision"]
    house["activities"] = [RULE]
    house["preferences"] = {"alex": {"pin": ["light.kitchen"], "hide": [], "order": ["room:kitchen"]}}
    saved = store.save(house)
    second = await client()
    try:
        for _ in range(3):
            status = await (await second.get("/api/installation", headers=headers)).json()
            assert not status["first_run"] and status["counts"] == {"people": 1, "screens": 1, "activities": 1}
            assert store.load() == saved
        assert not any(method == "POST" and ("install" in path or "repositories" in path) for method, path in env.mock.calls)
        bad = {"confirm": True, "revision": saved["revision"], "acknowledgement": "wrong"}
        assert (await second.post("/api/installation/reset", json=bad, headers=headers)).status == 409
        assert store.load() == saved
        good = {**bad, "acknowledgement": "RESET HOME STARTER"}
        assert (await second.post("/api/installation/reset", json=good, headers=headers)).status == 200
        assert (await (await second.get("/api/installation", headers=headers)).json())["first_run"]
        assert (await second.post("/api/installation/reset", json=good, headers=headers)).status == 409
    finally:
        await second.close()


async def test_ha_outage_preserves_existing_mode_and_baseline(make_env, tmp_path):
    env = await make_env("ready")
    settings = replace(env.settings, data_dir=str(tmp_path))
    store = HouseholdStore(str(tmp_path))
    saved = store.save(household())
    app = create_app(settings, env.session)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        await app[K_STATE].installation()
        before = store.observation_path.read_bytes()

        async def unavailable():
            raise CoreError("api", "Fixture outage")

        app[K_STATE].core.states = unavailable
        status = await app[K_STATE].installation()
        assert not status["first_run"] and not status["inventory_complete"]
        assert before == store.observation_path.read_bytes() and saved == store.load()
    finally:
        await client.close()


async def test_confirmed_music_setup_records_existing_state_without_people(make_env):
    env = await make_env("ready")
    app = create_app(env.settings, env.session)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        response = await client.post("/api/music/setup", json={"confirm": True}, headers=headers)
        assert response.status == 202
        await app[K_STATE].setup.wait()
        assert app[K_STATE].household.load()["configured"]
        assert app[K_STATE].household.load()["people"] == []
        assert not any(method == "POST" and "/install" in path for method, path in env.mock.calls)
    finally:
        await client.close()
