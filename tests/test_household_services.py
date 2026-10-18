"""Household relationships, scoped credentials and honest commissioning status."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import household_services as services
from homestarter.household import HouseholdStore, empty_household
from homestarter.server import create_app


@pytest.fixture
def configured(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = empty_household()
    house["people"] = [{"id": "adult", "name": "Example adult", "audience": "adult"}, {"id": "child", "name": "Example child", "audience": "everyone"}]
    house["surfaces"] = [{"id": "wall", "name": "Example wall", "profile": "wall", "person_id": None, "area_id": None, "audience": "everyone"}]
    house = store.save(house)
    value = services.empty(house["epoch"])
    value["media_identities"] = [
        {"id": "personal", "name": "Adult", "service": "spotify", "scope": "personal", "people": ["adult"], "provider_id": None},
        {"id": "shared", "name": "House", "service": "spotify", "scope": "shared", "people": ["child"], "provider_id": None},
        {"id": "shared2", "name": "House second", "service": "spotify", "scope": "shared", "people": ["child"], "provider_id": None},
    ]
    value["endpoints"] = [
        {
            "id": "endpoint",
            "name": "Example endpoint",
            "health_url": "http://example.local:8741/health",
            "surface_id": "wall",
            "player_id": None,
            "voice_entity": None,
        }
    ]
    return store, house, value


def test_identity_boundaries_and_stale_revision(configured):
    store, house, value = configured
    saved = services.save(store, house, value)
    assert saved["revision"] == 1
    with pytest.raises(ValueError, match="changed"):
        services.save(store, house, value)
    changed = deepcopy(saved)
    changed["media_identities"][0]["people"] = ["child"]
    with pytest.raises(ValueError, match="adult"):
        services.save(store, house, changed)
    changed = deepcopy(saved)
    for row in changed["media_identities"][1:]:
        row["provider_id"] = "same-provider"
    with pytest.raises(ValueError, match="share one"):
        services.save(store, house, changed)
    assert services.load(store, house) == saved


def test_timetable_mapping_requires_one_person_and_stores_no_class_payload(configured):
    store, house, value = configured
    value["calendars"] = [{"entity_id": "calendar.fictional_timetable", "category": "timetable", "people": ["child"]}]
    saved = services.save(store, house, value)
    assert services.load(store, house)["calendars"] == saved["calendars"]
    assert services.save(store, house, saved) == saved
    for owners in ([], ["child", "adult"]):
        changed = deepcopy(saved)
        changed["calendars"][0]["people"] = owners
        with pytest.raises(ValueError, match="exactly one"):
            services.validate(changed, house)
    changed = deepcopy(saved)
    changed["calendars"][0]["subjects"] = ["Fictional class"]
    with pytest.raises(ValueError, match="without copying events"):
        services.validate(changed, house)


def test_private_key_and_future_file_preservation(configured):
    store, house, value = configured
    services.save(store, house, value)
    key = "fixture-health-secret-" + "x" * 32
    services.bind(store, value, "endpoint", key)
    assert key not in str(services.load(store, house))
    future = {**value, "version": 99, "epoch": house["epoch"] - 1}
    store.write(services.path(store), future)
    with pytest.raises(ValueError, match="Unsupported"):
        services.load(store, house)
    assert store.read(services.path(store), {}) == future


@pytest.mark.parametrize(
    "url",
    [
        "https://example.local/health",
        "http://example.com/health",
        "http://fixture:fixture@example.invalid/health",  # pragma: allowlist secret -- synthetic rejected URL
        "http://example.local/health?command=reboot",
    ],
)
def test_health_address_is_dedicated_and_local(configured, url):
    _, house, value = configured
    value["endpoints"][0]["health_url"] = url
    with pytest.raises(ValueError):
        services.validate(value, house)


def test_libraries_cannot_claim_unimplemented_provider_user_isolation(configured):
    _, house, value = configured
    value["libraries"] = [{"id": "library", "name": "Example books", "provider_id": "example", "people": ["child"], "progress_mode": "provider_user"}]
    with pytest.raises(ValueError, match="progress"):
        services.validate(value, house)


def test_endpoint_status_needs_fresh_authenticated_display_and_all_services(configured):
    _, house, value = configured
    attrs = {
        "home_starter_endpoint": {"id": "endpoint", "epoch": house["epoch"]},
        "valid_until": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        "browser_alive": True,
        "dashboard_open": True,
        "authenticated_display_verified": False,
        "audio_service": "inactive",
        "voice_service": "inactive",
        "voice_connected": True,
        "voice_muted": False,
    }
    state = {"entity_id": services.endpoint_entity("endpoint"), "state": "online", "attributes": attrs}

    def status():
        return next(r["status"] for r in services.status(value, [], [state], {}) if r["name"] == "Example endpoint")

    assert status() == "Needs login"
    attrs["authenticated_display_verified"] = True
    assert status() == "Needs setup"
    attrs.update(audio_service="active", voice_service="active")
    assert status() == "Needs setup"
    value["endpoints"][0].update(player_id="media_player.endpoint", voice_entity="assist_satellite.endpoint")
    states = [state, {"entity_id": "media_player.endpoint", "state": "idle"}, {"entity_id": "assist_satellite.endpoint", "state": "idle"}]
    assert next(r["status"] for r in services.status(value, [], states, {}) if r["name"] == "Example endpoint") == "Ready"
    attrs["voice_muted"] = True
    assert next(r["status"] for r in services.status(value, [], states, {}) if r["name"] == "Example endpoint") == "Microphone muted"
    attrs["voice_muted"] = False
    attrs["voice_connected"] = False
    assert next(r["status"] for r in services.status(value, [], states, {}) if r["name"] == "Example endpoint") == "Needs setup"
    attrs["voice_connected"] = True
    states[1]["state"] = "unavailable"
    assert next(r["status"] for r in services.status(value, [], states, {}) if r["name"] == "Example endpoint") == "Needs setup"
    states[1]["state"] = "idle"
    attrs["dashboard_open"] = False
    assert next(r["status"] for r in services.status(value, [], states, {}) if r["name"] == "Example endpoint") == "Needs setup"
    attrs["dashboard_open"] = True
    attrs["valid_until"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    assert status() == "Device offline"


async def test_service_api_requires_admin(make_env):
    env = await make_env("ready")
    async with TestClient(TestServer(create_app(env.settings, env.session))) as client:
        assert (await client.get("/api/services")).status == 403
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        response = await client.get("/api/services", headers=headers)
        assert response.status == 200
        data = await response.json()
        assert data["endpoint_keys_configured"] == []
        assert data["configuration"]["media_identities"] == []
        assert "setup" in data


def test_setup_choices_exclude_events_and_credentials(configured):
    _, house, _ = configured
    inventory = {"integrations": [{"entry_id": "google-hub", "title": "Calendar hub", "domain": "google", "state": "loaded", "secret": "not-public"}]}
    states = [{"entity_id": "calendar.family", "attributes": {"friendly_name": "Family", "message": "private event"}}]
    music = {"providers": [{"id": "spotify-one", "name": "Shared", "domain": "spotify", "status": "connected", "values": {"token": "not-public"}}]}
    options = services.setup_options(house, inventory, states, music)
    assert options["calendars"] == [{"id": "calendar.family", "name": "Family"}]
    assert "private event" not in str(options) and "not-public" not in str(options)


def test_new_provider_bindings_require_matching_discovered_instances(configured):
    _, house, previous = configured
    value = deepcopy(previous)
    value["media_identities"][0]["provider_id"] = "fabricated"
    with pytest.raises(ValueError, match="matching"):
        services.check_new_bindings(value, previous, {"google": [], "calendars": [], "providers": []})
    options = {"google": [], "calendars": [], "providers": [{"id": "fabricated", "domain": "audiobookshelf"}]}
    with pytest.raises(ValueError, match="matching"):
        services.check_new_bindings(value, previous, options)
    options["providers"][0]["domain"] = "spotify"
    services.check_new_bindings(value, previous, options)
    # An outage must not force users to delete their saved identities.
    services.check_new_bindings(value, value, {"google": [], "calendars": [], "providers": []})


def test_calendar_bindings_require_native_choices(configured):
    _, house, previous = configured
    value = deepcopy(previous)
    value.update(calendar_hub="invented", calendars=[{"entity_id": "calendar.new", "category": "person", "people": ["child"]}])
    options = {"google": [], "calendars": [], "providers": []}
    with pytest.raises(ValueError, match="Google"):
        services.check_new_bindings(value, previous, options)
    options["google"] = [{"id": "invented"}]
    with pytest.raises(ValueError, match="calendar"):
        services.check_new_bindings(value, previous, options)
    options["calendars"] = [{"id": "calendar.new"}]
    services.check_new_bindings(value, previous, options)
