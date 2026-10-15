"""The completion view distinguishes evidence from discovery and remains read-only."""

from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import readiness
from homestarter.house_readiness import report
from homestarter.household import HouseholdStore
from homestarter.inventory import collect_inventory
from homestarter.music_runtime import MusicRuntimeError
from homestarter.server import K_STATE, create_app


@pytest.fixture
async def inventory(make_env):
    env = await make_env("ready")
    return await collect_inventory(env.core)


def source(inv, domain, state="on", name="Example source"):
    entity = {"entity_id": domain + ".example", "name": name, "observed": True, "state": state}
    inv["unattached_entities"].append(entity)
    return entity


def rows(inv, **checks):
    checks.setdefault("readiness", readiness.empty(0))
    checks.setdefault("screens", [])
    checks.setdefault("music", {"connected": False})
    return {row["id"]: row for row in report(inv, [], checks)}


@pytest.mark.parametrize("status,expected", [("current", "ready"), ("last_known_valid", "partial"), ("stale", "problem"), ("needs_checking", "problem")])
async def test_confirmed_waste_provider_takes_precedence_over_legacy_calendar_discovery(inventory, status, expected):
    source(inventory, "calendar", name="Example bin collection")
    bins = {"configured": True, "status": status, "entities_ready": True, "message": "Provider evidence result", "entity_issue": None}
    row = rows(inventory, waste=bins)["waste"]
    assert row["state"] == expected and row["route"] == "#waste-collection"
    assert row["detail"] == bins["message"]


async def test_music_needs_current_scoped_playback_proof(inventory):
    proof = {"at": datetime.now(UTC).isoformat(), "provider_id": "example_provider", "player_id": "example_speaker"}
    assert rows(inventory, music={"connected": True, "proof": proof})["music"]["state"] == "ready"
    for changed in ({**proof, "at": (datetime.now(UTC) - timedelta(days=2)).isoformat()}, {**proof, "player_id": None}, {}):
        assert rows(inventory, music={"connected": True, "proof": changed})["music"]["state"] == "needs_setup"
    assert rows(inventory, music=None)["music"]["state"] == "unknown"


async def test_reporting_climate_or_camera_is_not_functional_verification(inventory):
    source(inventory, "climate", "cool")
    source(inventory, "camera", "idle")
    checked = rows(inventory)
    assert checked["climate"]["state"] == checked["cameras"]["state"] == "partial"
    assert "responds to commands" in checked["climate"]["detail"]
    assert "have not been checked" in checked["cameras"]["detail"]


async def test_unknown_sources_and_partial_reads_do_not_claim_missing_setup(inventory):
    entity = source(inventory, "camera", "unknown")
    assert rows(inventory)["cameras"]["state"] == "unknown"
    entity["state"] = "unavailable"
    assert rows(inventory)["cameras"]["state"] == "problem"
    inventory["sources"]["states"]["status"] = "unavailable"
    assert rows(inventory)["cameras"]["state"] == "unknown"


async def test_calendar_reuses_bounded_source_proof_not_calendar_name(inventory):
    calendar = source(inventory, "calendar", "off", "Example household calendar")
    value = readiness.empty(0)
    value["choices"]["calendars"] = {"intent": "wanted", "sources": [calendar["entity_id"]], "screens": []}
    assert rows(inventory, readiness=value)["calendars"]["state"] == "needs_setup"
    value["verified"]["calendars"] = {"at": datetime.now(UTC).isoformat(), "signature": readiness.selection_signature(value["choices"]["calendars"], inventory)}
    assert rows(inventory, readiness=value)["calendars"]["state"] == "ready"
    calendar["entity_id"] = "calendar.renamed_source"
    assert rows(inventory, readiness=value)["calendars"]["state"] == "problem"
    assert rows(inventory, readiness=None)["calendars"]["state"] == "unknown"


async def test_deferred_choices_and_dashboard_readback_limits(inventory):
    value = readiness.empty(0)
    value["choices"]["music"] = {"intent": "later"}
    assert rows(inventory, readiness=value, music={"connected": True})["music"]["state"] == "not_applicable"
    for status, expected in (("published", "ready"), ("external_edits", "partial"), ("missing", "problem"), ("unavailable", "unknown")):
        row = rows(inventory, screens=[{"status": status}])["dashboards"]
        assert row["state"] == expected and "Physical display" in row["detail"]
    checks = [{"status": "published", "profile": "specialist", "commissioning": {"required": True, "stage": "published"}}]
    assert rows(inventory, screens=checks)["dashboards"]["state"] == "ready"
    assert rows(inventory, screens=checks)["display_commissioning"]["state"] == "partial"
    checks[0]["commissioning"]["stage"] = "commissioned"
    assert rows(inventory, screens=checks)["display_commissioning"]["state"] == "ready"


async def test_presence_exclusions_are_respected_without_home_away_claims(inventory):
    people = [{"role": "child", "presence_plan": "untracked", "usable_tracker": False}, {"role": "adult", "presence_plan": None, "usable_tracker": True}]
    row = next(r for r in report(inventory, people, {"music": None, "screens": [], "readiness": {}}) if r["id"] == "presence")
    assert "1 members intentionally untracked" in row["detail"]
    assert "accuracy is unverified" in row["detail"] and row["state"] == "partial"


async def test_incomplete_discovery_and_deferred_intent_survive_special_status_rules(inventory):
    inventory["integrations"].extend([{"domain": "voip"}, {"domain": "google_assistant"}])
    inventory["sources"]["states"]["status"] = "unavailable"
    people = [{"role": "adult", "presence_plan": None, "usable_tracker": True}]
    checked = {r["id"]: r for r in report(inventory, people, {"music": None, "screens": [], "readiness": readiness.empty(0)})}
    for key in ("presence", "communications", "voice"):
        assert checked[key]["state"] == "unknown"
        assert "reporting" not in checked[key]["detail"]
    value = readiness.empty(0)
    value["choices"]["presence"] = {"intent": "later"}
    assert rows(inventory, readiness=value)["presence"]["state"] == "not_applicable"
    inventory["sources"]["states"]["status"] = "ok"
    assert rows(inventory, readiness=value)["presence"]["state"] == "not_applicable"


async def test_readiness_outage_cannot_block_house_records_or_write_setup(make_env, monkeypatch):
    env = await make_env("ready")
    app = create_app(env.settings)

    async def failed():
        raise MusicRuntimeError("private fixture error")

    store = HouseholdStore(env.settings.data_dir)
    async with TestClient(TestServer(app)) as client:
        monkeypatch.setattr(app[K_STATE].music_runtime, "snapshot", failed)
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/house/status")).status == 403
        assert (await client.get("/api/house", headers=headers)).status == 200
        response = await client.get("/api/house/status", headers=headers)
        assert response.status == 200
        result = await response.json()
        assert next(r for r in result["capabilities"] if r["id"] == "music")["state"] == "unknown"
        assert "private fixture error" not in str(result)
    assert not store.this_house_path.exists() and not store.readiness_path.exists()
    assert not any(c["type"].endswith(("/update", "/create", "/delete")) for c in env.mock.ws_calls)
