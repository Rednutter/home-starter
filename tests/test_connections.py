"""Connection consent, household identity and recovery contracts (synthetic data)."""

from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import calendar_access as calendars
from homestarter import connections, google_setup, household_music, household_services, music_identity_auth, readiness
from homestarter.household import HouseholdStore
from homestarter.inventory import collect_inventory
from homestarter.server import K_STATE, create_app
from homestarter.settings import Secret
from homestarter.surfaces import classify, generate


def providers():
    return [
        {"id": "fixture_" + household_music.normalized(n), "name": n, "domain": "spotify", "available": True, "enabled": True}
        for n in ("Spotify — Grant", "House", "House#2")
    ] + [{"id": "fixture_radio", "name": "Example radio", "domain": "radiobrowser", "available": True}]


async def test_six_users_reconcile_idempotently_and_pending_renae_is_healthy():
    users = [{"user_id": "fixture_admin", "username": "example.admin", "display_name": "Grant", "role": "admin", "provider_filter": []}]
    calls = []

    async def command(name, **args):
        calls.append(name)
        if name == "auth/users":
            return deepcopy(users)
        if name == "auth/user/create":
            assert len(args.pop("password")) >= 32
            users.append({**args, "user_id": "fixture_" + args["username"]})
        elif name == "auth/user/update":
            next(u for u in users if u["user_id"] == args["user_id"]).update(args)
        else:
            pytest.fail("Unexpected MA mutation")

    result = await household_music.reconcile(command, providers())
    assert result["state"] == "connected"
    assert (result["users"], result["connected"], result["pending"]) == (6, 3, 1)
    assert next(r for r in result["spotify"] if r["name"] == "Renae")["state"] == "ready_for_authentication"
    assert len(users) == 6
    assert calls.count("auth/user/create") == 5
    calls.clear()
    assert await household_music.reconcile(command, providers()) == result
    assert set(calls) == {"auth/users"}
    assert users[0]["user_id"] == "fixture_admin" and users[0]["role"] == "admin"
    for user in users:
        access = user["provider_filter"]
        assert "fixture_radio" in access
        if user["display_name"] != "Grant":
            assert "fixture_grant" not in access
        if user["display_name"] == "Renae":
            assert not set(access) & {"fixture_house", "fixture_house2"}


async def test_reconciliation_rejects_ambiguous_names_and_unverified_writes():
    command = AsyncMock(return_value=[{"user_id": "fixture_a", "display_name": "Grant"}, {"user_id": "fixture_b", "display_name": "Grant"}])
    with pytest.raises(ValueError, match="Duplicate"):
        await household_music.reconcile(command, providers())
    assert command.await_count == 1
    command = AsyncMock(return_value=[{"user_id": "fixture_a", "display_name": "Grant", "provider_filter": []}])
    with pytest.raises(ValueError, match="could not be verified"):
        await household_music.reconcile(command, providers())


def test_renae_native_auth_return_binds_default_provider_name_without_renaming(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.load()
    house["people"] = [{"id": "fixture_renae", "name": "Renae", "audience": "adult"}]
    house = store.save(house)
    before = providers()
    pending = music_identity_auth.begin(store, house, before, "Renae")
    assert not music_identity_auth.resume(store, house, before)
    assert sum(p["domain"] == "spotify" for p in before) == 3
    connected = before + [{"id": "fixture_new_account", "name": "Spotify", "domain": "spotify", "available": True}]
    # A repeated click must preserve the pre-authentication baseline.
    assert music_identity_auth.begin(store, house, connected, "Renae") == pending
    assert music_identity_auth.resume(store, house, connected)
    config = household_services.load(store, house)
    row = next(r for r in config["media_identities"] if r["name"] == "Renae")
    assert row["provider_id"] == "fixture_new_account" and row["scope"] == "personal"
    assert row["people"] == ["fixture_renae"]
    decorated = music_identity_auth.decorate(store, house, connected)
    assert household_music.providers_by_identity(decorated)["Renae"]["name"] == "Spotify"
    assert "fixture_new_account" in household_music.source_access("Renae", decorated)
    assert "fixture_new_account" not in household_music.source_access("Edie", decorated)
    assert not music_identity_auth.resume(store, house, connected)
    assert household_services.load(store, house) == config
    for child in ("Edie", "Maddie", "Flynn"):
        with pytest.raises(ValueError, match="intended"):
            music_identity_auth.begin(store, house, before, child)


def test_auth_return_with_two_new_providers_requires_review_and_preserves_them(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.load()
    music_identity_auth.begin(store, house, providers(), "Renae")
    added = [{"id": f"fixture_new_{i}", "name": "Spotify", "domain": "spotify", "available": True} for i in range(2)]
    with pytest.raises(ValueError, match="More than one"):
        music_identity_auth.resume(store, house, providers() + added)
    assert music_identity_auth.load(store, house)["provider_id"] is None
    assert not household_services.load(store, house)["media_identities"]


def test_abandoned_auth_intent_cannot_bind_an_unrelated_future_account(tmp_path, monkeypatch):
    store = HouseholdStore(str(tmp_path))
    house = store.load()
    monkeypatch.setattr(music_identity_auth.time, "time", lambda: 1000)
    music_identity_auth.begin(store, house, providers(), "Renae")
    monkeypatch.setattr(music_identity_auth.time, "time", lambda: 3000)
    extra = {"id": "fixture_later", "name": "Spotify", "domain": "spotify", "available": True}
    assert not music_identity_auth.resume(store, house, providers() + [extra])
    assert not household_services.load(store, house)["media_identities"]


def test_shared_allocator_order_personal_boundaries_and_unknown_grant_state():
    sources = providers()
    occupied = set()
    chosen = []
    for _ in range(3):
        provider = household_music.choose_provider(sources, occupied, grant_free=True)
        chosen.append(provider)
        occupied.add(provider)
    assert chosen == ["fixture_house", "fixture_house2", "fixture_grant"]
    with pytest.raises(ValueError, match="busy"):
        household_music.choose_provider(sources, occupied, grant_free=True)
    with pytest.raises(ValueError, match="busy"):
        household_music.choose_provider(sources, {"fixture_house", "fixture_house2"})
    sources.append({"id": "fixture_renae", "name": "Renae", "domain": "spotify", "available": True})
    with pytest.raises(ValueError, match="busy"):
        household_music.choose_provider(sources, occupied, grant_free=True)
    assert household_music.choose_provider(sources, occupied, personal="Renae") == "fixture_renae"
    assert household_music.choose_provider(sources, set(), personal="Grant") == "fixture_grant"
    assert "fixture_grant" not in household_music.source_access("Edie", sources)
    assert household_music.visible({"uri": "fixture_grant://playlist/private"}, "Edie", sources) is False
    assert household_music.visible({"uri": "fixture_house://playlist/shared"}, "Edie", sources) is True
    sources.append({"id": "fixture_unmapped", "name": "Unexpected account", "domain": "spotify", "available": True})
    status = household_music.user_status([{"display_name": n} for n in household_music.NAMES], sources)
    assert status["state"] == "needs_review" and status["unmapped"] == 1
    assert status["connected"] == 5


def test_provider_startup_is_not_a_request_to_reauthenticate():
    sources = providers()
    sources[0]["available"] = False
    status = household_music.user_status([{"display_name": n} for n in household_music.NAMES], sources)
    grant = next(r for r in status["spotify"] if r["name"] == "Grant")
    assert grant["state"] == "preparing"
    sources[0]["requires_auth"] = True
    status = household_music.user_status([{"display_name": n} for n in household_music.NAMES], sources)
    assert next(r for r in status["spotify"] if r["name"] == "Grant")["state"] == "reauth_required"


def test_calendar_classification_persistence_new_sources_and_reclassification(tmp_path):
    store = HouseholdStore(str(tmp_path))
    house = store.load()
    states = [{"entity_id": "calendar.fixture_one", "state": "off", "attributes": {"friendly_name": "Example"}}]
    first = calendars.discover(store, house, states)
    assert first["rows"][0]["mode"] == "review"
    assert first["state"] == "needs_review"
    body = {k: first[k] for k in ("version", "epoch", "revision", "calendars")}
    for mode in ("show", "context", "ignore"):
        body["calendars"]["calendar.fixture_one"] = mode
        result = calendars.save(store, house, states, body)
        assert calendars.load(HouseholdStore(str(tmp_path)), house)["calendars"]["calendar.fixture_one"] == mode
        body["revision"] = result["revision"]
    states.append({"entity_id": "calendar.fixture_two", "state": "off", "attributes": {}})
    assert calendars.discover(store, house, states)["counts"] == {"show": 0, "context": 0, "ignore": 1, "review": 1}
    assert not list(tmp_path.glob("*token*"))


def test_only_show_is_admitted_to_shared_surfaces():
    policy = {"calendars": ["calendar.fixture"], "calendars_screens": ["fixture_wall"], "calendar_access": {"calendar.fixture": "context"}}
    item = {"id": "calendar.fixture", "domain": "calendar"}
    surface = {"id": "fixture_wall", "person_id": None}
    assert not readiness.allowed(item, surface, {}, policy)
    policy["calendar_access"]["calendar.fixture"] = "show"
    assert readiness.allowed(item, surface, {}, policy)
    policy["calendar_access"].clear()
    assert not readiness.allowed(item, surface, {}, policy)
    assert calendars.permitted({"calendar.fixture": "context"}, "calendar.fixture", context=True)
    assert not calendars.permitted({"calendar.fixture": "ignore"}, "calendar.fixture", context=True)
    assert calendars.permitted(
        {"calendar.fixture": "context"}, "calendar.fixture", person="fixture_child", mappings=[{"entity_id": "calendar.fixture", "people": ["fixture_child"]}]
    )


async def test_context_calendar_can_appear_only_on_its_explicit_person_page(make_env):
    import json

    env = await make_env()
    store = HouseholdStore(env.settings.data_dir)
    house = store.load()
    person = "fixture_adult"
    house["people"] = [{"id": person, "name": "Example adult", "audience": "adult"}]
    surface = {"id": "fixture_tablet", "name": "Example tablet", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}
    house["surfaces"] = [surface]
    house = store.save(house)
    source = "calendar.fixture_personal"
    env.mock.entity_registry.append({"entity_id": source, "platform": "google", "name": "Example personal calendar", "device_id": None})
    env.mock.activity_states[source] = {"entity_id": source, "state": "off", "attributes": {}}
    inventory, states = await collect_inventory(env.core), await env.core.states()
    saved = readiness.load(store, house)
    choice = {"intent": "wanted", "sources": [source], "screens": [surface["id"]], "answers": {}, "permissions": {}}
    saved["choices"]["calendars"] = choice
    saved["verified"]["calendars"] = {"at": datetime.now(UTC).isoformat(), "signature": readiness.selection_signature(choice, inventory)}
    store.write(store.readiness_path, saved)
    config = household_services.load(store, house)
    config["calendars"] = [{"entity_id": source, "category": "person", "people": [person]}]
    household_services.save(store, house, config)
    value = calendars.load(store, house)
    value["calendars"][source] = "context"
    calendars.save(store, house, states, value)
    policy = readiness.policy_for(saved, house, inventory, states, store)
    dashboard = generate(house, surface, classify(inventory, states, {}), inventory["areas"], policy=policy)["config"]
    home = next(v for v in dashboard["views"] if v["path"] == "home")
    personal = [v for v in dashboard["views"] if v["path"].startswith("person-" + person.encode().hex())]
    assert source not in json.dumps(home)
    assert source in json.dumps(personal)


@pytest.mark.parametrize(
    "error,code,state",
    [
        ("401 invalid_client secret=synthetic-private", "invalid_client", "ready_for_authentication"),
        ("403 access_denied: app is in Testing", "testing", "ready_for_authentication"),
        ("403 access_denied", "access_denied", "ready_for_authentication"),
        ("redirect_uri_mismatch", "redirect_uri_mismatch", "ready_for_authentication"),
        ("Calendar API has not been used", "api_disabled", "connected_but_incomplete"),
        ("Branding incomplete", "branding", "ready_for_authentication"),
        ("invalid_grant revoked", "invalid_grant", "reauth_required"),
    ],
)
def test_oauth_errors_are_fixed_safe_diagnostics(error, code, state):
    result = google_setup.diagnose(error)
    assert (result["code"], result["state"]) == (code, state)
    assert "synthetic-private" not in str(result)
    if code == "testing":
        assert "In production" in result["detail"] and "Branding" in result["detail"]


async def test_admin_preview_is_ephemeral_bounded_and_does_not_change_consent(tmp_path):
    store = HouseholdStore(str(tmp_path))
    core = AsyncMock()
    core.states.return_value = [{"entity_id": "calendar.fixture", "state": "off"}]
    core.rest_get.return_value = [
        {"summary": "Example sports session", "start": "2026-11-02", "description": "private synthetic description", "attendees": ["private"]}
    ] * 9
    result = await connections.calendar_preview(core, "calendar.fixture")
    assert len(result["events"]) == 5
    assert "description" not in str(result) and "attendees" not in str(result)
    assert not calendars.load(store, store.load())["calendars"]
    assert not list(tmp_path.glob("*.json"))


async def test_connection_api_resumes_after_auth_and_calendar_save_does_not_reauth(make_env, monkeypatch):
    env = await make_env()
    client = TestClient(TestServer(create_app(env.settings, env.session)))
    await client.start_server()
    headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
    state = client.server.app[K_STATE]
    monkeypatch.setattr(state.music_runtime, "household", AsyncMock(return_value=household_music.user_status([], providers())))
    monkeypatch.setattr(connections, "reconcile_mappings", AsyncMock())
    state.waste_task.cancel()
    try:
        assert (await client.get("/api/connections")).status == 403
        before = await (await client.get("/api/connections", headers=headers)).json()
        assert before["google"]["state"] == "not_detected"
        env.mock.entries.append({"entry_id": "fixture_google", "domain": "google", "title": "Example hub", "state": "loaded"})
        env.mock.activity_states["calendar.fixture"] = {"entity_id": "calendar.fixture", "state": "off", "attributes": {"friendly_name": "Example calendar"}}
        env.mock.calendar_events["calendar.fixture"] = []
        env.mock.entity_registry.append(
            {"entity_id": "calendar.fixture", "platform": "google", "config_entry_id": "fixture_google", "name": "Example calendar", "device_id": None}
        )
        after = await (await client.post("/api/connections/prepare", headers=headers, json={})).json()
        assert after["google"]["state"] == "connected"
        assert after["google"]["credentials"] == "verified_by_connection"
        assert after["calendars"]["counts"]["review"] >= 1
        value = after["calendars"]
        body = {k: value[k] for k in ("version", "epoch", "revision", "calendars")}
        body["calendars"] = {"calendar.fixture": "context"}
        response = await client.post("/api/connections/calendars", headers=headers, json=body)
        assert response.status == 200, await response.text()
        assert calendars.load(state.household, state.household.load())["calendars"]["calendar.fixture"] == "context"
        configured = readiness.load(state.household, state.household.load())
        assert configured["choices"]["calendars"]["intent"] == "wanted"
        assert "calendar.fixture" in configured["choices"]["calendars"]["sources"]
        assert "calendars" in configured["verified"]
        env.mock.activity_states["calendar.fixture"]["state"] = "unavailable"
        failed = await (await client.post("/api/connections/prepare", headers=headers, json={})).json()
        assert failed["verification"]["state"] == "connected_but_incomplete"
        assert "calendars" not in readiness.load(state.household, state.household.load())["verified"]
        assert not any("flow" in str(call) for call in env.mock.calls if isinstance(call, str))
    finally:
        await client.close()


async def test_media_setup_requires_admin_and_current_household_before_mutations(make_env, monkeypatch):
    env = await make_env()
    client = TestClient(TestServer(create_app(env.settings, env.session)))
    await client.start_server()
    state = client.server.app[K_STATE]
    state.waste_task.cancel()
    headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
    monkeypatch.setattr(state.music_runtime, "connection", lambda: {"server_id": "fixture_server", "token": Secret("fixture_credential")})
    monkeypatch.setattr(state.music_runtime, "endpoint", AsyncMock(return_value="fixture_endpoint"))
    consent, sync, control = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(state.listening.media, "consent", consent)
    monkeypatch.setattr(state.listening.media, "sync", sync)
    monkeypatch.setattr(state.music_runtime, "control", control)
    try:
        assert (await client.get("/api/media")).status == 403
        epoch = state.household.load()["epoch"]
        for action in ("select", "allow_local_lookup", "disable_local_lookup", "cleanup"):
            response = await client.post("/api/media", headers=headers, json={"action": action, "epoch": epoch + 1, "selected": []})
            assert response.status == 409
        response = await client.post("/api/media", headers=headers, json={"action": "select", "epoch": epoch, "selected": "invalid"})
        assert response.status == 409
        consent.assert_not_awaited()
        sync.assert_not_awaited()
        control.assert_not_awaited()
    finally:
        await client.close()


async def test_reclassification_refreshes_owned_native_cards_without_overwriting_external_edits(tmp_path, monkeypatch):
    import json
    from contextlib import asynccontextmanager

    from homestarter.surfaces import fingerprint

    store = HouseholdStore(str(tmp_path))
    house = store.load()
    house["people"] = [{"id": "fixture_adult", "name": "Example adult", "audience": "adult"}]
    house["surfaces"] = [{"id": "fixture_tablet", "name": "Example tablet", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}]
    house = store.save(house)
    source = "calendar.fixture"
    states = [{"entity_id": source, "state": "off", "attributes": {"friendly_name": "Example feed"}}]
    config = household_services.load(store, house)
    config["calendars"] = [{"entity_id": source, "category": "person", "people": ["fixture_adult"]}]
    household_services.save(store, house, config)
    choice = calendars.load(store, house)
    choice["calendars"][source] = "context"
    calendars.save(store, house, states, choice)
    monkeypatch.setattr(readiness, "policy_for", lambda *args: {"calendars": [source], "calendars_screens": ["fixture_tablet"]})
    climate = {"type": "thermostat", "entity": "climate.fixture"}
    native = {"type": "calendar", "entities": [source], "title": "Example feed"}
    dashboard = {
        "views": [
            {"path": "home", "type": "sections", "sections": [{"type": "grid", "cards": [deepcopy(climate), deepcopy(native)]}]},
            {"path": "person-" + b"fixture_adult".hex(), "type": "sections", "sections": [{"type": "grid", "cards": [deepcopy(native)]}]},
        ]
    }
    url = "home-starter-fixture-tablet"
    store.write(store.publication_path, {url: {"fingerprint": fingerprint(dashboard), "verified": True}})

    class Core:
        saves = 0

        @asynccontextmanager
        async def websocket(self):
            yield self

        async def command(self, command, **args):
            nonlocal dashboard
            assert args["url_path"] == url
            if command == "lovelace/config":
                return deepcopy(dashboard)
            assert command == "lovelace/config/save"
            dashboard = deepcopy(args["config"])
            self.saves += 1

    core = Core()
    assert await calendars.refresh_publications(core, store, house, {}, states) == []
    assert source not in json.dumps(dashboard["views"][0])
    assert source in json.dumps(dashboard["views"][1])
    assert dashboard["views"][0]["sections"][0]["cards"][0] == climate
    assert core.saves == 1
    assert await calendars.refresh_publications(core, store, house, {}, states) == []
    assert core.saves == 1
    choice = calendars.load(store, house)
    choice["calendars"][source] = "show"
    calendars.save(store, house, states, choice)
    assert await calendars.refresh_publications(core, store, house, {}, states) == []
    assert source in json.dumps(dashboard["views"][0])
    dashboard["title"] = "External edit"
    snapshot = deepcopy(dashboard)
    issues = await calendars.refresh_publications(core, store, house, {}, states)
    assert issues and "existing dashboard edits" in issues[0]
    assert dashboard == snapshot


async def test_commissioning_resumes_verified_music_with_three_providers_and_renae_pending(tmp_path):
    from types import SimpleNamespace

    from homestarter import commissioning

    store = HouseholdStore(str(tmp_path))
    store.save(store.load())
    value = commissioning.load(store)
    value.update(phase="verification_incomplete", active=True, results={"household": {"status": "verified"}, "music": {"status": "incomplete"}})
    commissioning.write(store, value)
    music = household_music.user_status([{"display_name": n} for n in household_music.NAMES], providers())
    state = SimpleNamespace(household=store, music_runtime=SimpleNamespace(verified=AsyncMock(return_value=True)))
    assert music["connected"] == 3 and music["pending"] == 1
    await connections.resume_commissioning(state, music)
    result = commissioning.load(store)
    assert result["phase"] == "commissioned" and result["results"]["music"]["status"] == "verified"
    await connections.resume_commissioning(state, music)
    assert commissioning.load(store) == result
    state.music_runtime.verified.assert_awaited_once()
