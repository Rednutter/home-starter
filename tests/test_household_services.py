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
        "authenticated_display_verified": False,
        "audio_service": "inactive",
        "voice_service": "inactive",
    }
    state = {"entity_id": services.endpoint_entity("endpoint"), "state": "online", "attributes": attrs}

    def status():
        return next(r["status"] for r in services.status(value, [], [state], {}) if r["name"] == "Example endpoint")

    assert status() == "Needs login"
    attrs["authenticated_display_verified"] = True
    assert status() == "Needs setup"
    attrs.update(audio_service="active", voice_service="active")
    assert status() == "Ready"
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
