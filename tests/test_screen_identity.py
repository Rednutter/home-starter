"""Only fictional users and surfaces. No passwords or authentication storage access."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from homestarter import screen_identity as identity
from homestarter.core import CoreError
from homestarter.household import HouseholdStore, empty_household
from homestarter.surfaces import fingerprint

NOW = datetime(2026, 6, 8, 1, tzinfo=UTC)


class NativeCore:
    def __init__(self):
        self.users = [
            {
                "id": "fixture_display",
                "name": "Fixture panel",
                "username": "fixture_panel",
                "is_owner": False,
                "is_active": True,
                "local_only": True,
                "system_generated": False,
                "group_ids": ["system-users"],
                "credentials": [{"type": "homeassistant"}],
            }
        ]
        self.people = {"storage": [], "config": []}
        self.helpers = []
        self.registry = []
        self.observed = []
        self.dashboards = {}
        self.configs = {}
        self.commands = []
        self.fail = None

    def websocket(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def command(self, kind, **kw):
        self.commands.append((kind, kw))
        if self.fail == kind:
            raise CoreError("api", "Fixture unavailable")
        if kind == "config/auth/list":
            return deepcopy(self.users)
        if kind == "person/list":
            return deepcopy(self.people)
        if kind == "config/auth/update":
            next(u for u in self.users if u["id"] == kw["user_id"]).update({k: v for k, v in kw.items() if k != "user_id"})
            return None
        if kind == "input_button/create":
            helper = {"id": "fixture_check", **kw}
            self.helpers.append(helper)
            self.registry.append({"entity_id": "input_button.fixture_check", "platform": "input_button", "unique_id": helper["id"]})
            self.observed.append({"entity_id": "input_button.fixture_check", "state": "unknown", "context": {"user_id": None}})
            return deepcopy(helper)
        if kind == "input_button/list":
            return deepcopy(self.helpers)
        if kind == "config/entity_registry/list":
            return deepcopy(self.registry)
        if kind == "lovelace/dashboards/list":
            return list(deepcopy(self.dashboards).values())
        if kind == "lovelace/dashboards/create":
            self.dashboards[kw["url_path"]] = kw
            return kw
        if kind == "lovelace/config/save":
            self.configs[kw["url_path"]] = kw["config"]
            return None
        if kind == "lovelace/config":
            return deepcopy(self.configs[kw["url_path"]])
        raise AssertionError(kind)

    async def states(self):
        return deepcopy(self.observed)

    def press(self, at, user="fixture_display", context="fixture_context"):
        self.observed[0].update(state=at.isoformat(), context={"id": context, "user_id": user})


@pytest.fixture
def setup(tmp_path):
    store = HouseholdStore(str(tmp_path / "runtime"))
    house = empty_household()
    house["surfaces"] = [
        {"id": "fixture_panel", "name": "Fixture AirTouch panel", "profile": "specialist", "person_id": None, "area_id": None, "audience": "everyone"}
    ]
    house = store.save(house)
    published = [{"id": "fixture_panel", "status": "published", "fingerprint": fingerprint({"fixture": "dashboard"})}]
    return NativeCore(), store, house, published


async def act(setup, action, at=NOW, **extra):
    core, store, house, published = setup
    value = identity.load(store, house)
    return await identity.apply(
        core,
        store,
        house,
        published,
        {"revision": value["revision"], "epoch": house["epoch"], "surface": "fixture_panel", "action": action, "confirm": True, **extra},
        "fixture_admin",
        at,
    )


async def select(setup):
    return await act(setup, "select", user_id="fixture_display", permission="control")


async def session(setup):
    await select(setup)
    await act(setup, "begin", stage="session")
    setup[0].press(NOW + timedelta(seconds=1))
    return await act(setup, "observe", NOW + timedelta(seconds=2))


async def restart(setup):
    await session(setup)
    await act(setup, "begin", NOW + timedelta(seconds=3), stage="restart")
    setup[0].press(NOW + timedelta(seconds=4), context="fixture_restart")
    return await act(setup, "observe", NOW + timedelta(seconds=5))


async def test_publication_does_not_commission_or_write_migration(setup):
    core, store, house, published = setup
    before = store.path.read_bytes()
    result = await identity.inspect(core, store, house, published)
    assert result["screens"][0]["stage"] == "published"
    assert "identity not yet verified" in result["screens"][0]["issue"]
    assert not store.screen_identity_path.exists()
    assert store.path.read_bytes() == before
    assert not any(kind.endswith("/create") for kind, _ in core.commands)


async def test_full_lifecycle_requires_native_identity_and_separate_physical_report(setup):
    core, store, house, published = setup
    await session(setup)
    assert (await identity.inspect(core, store, house, published))["screens"][0]["stage"] == "authenticated"
    await act(setup, "begin", NOW + timedelta(seconds=3), stage="restart")
    core.press(NOW + timedelta(seconds=4), context="fixture_restart")
    await act(setup, "observe", NOW + timedelta(seconds=5))
    assert (await identity.inspect(core, store, house, published))["screens"][0]["stage"] != "commissioned"
    await act(setup, "physical", NOW + timedelta(seconds=6), dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="browser")
    row = (await identity.inspect(core, store, house, published))["screens"][0]
    assert row["stage"] == "commissioned"
    assert row["record"]["physical"]["by"] == "fixture_admin"
    fresh = HouseholdStore(str(store.path.parent))
    assert identity.load(fresh, house) == identity.load(store, house)
    assert "password" not in store.screen_identity_path.read_text().lower()
    assert len(core.helpers) == 1
    assert not next(iter(core.dashboards.values()))["show_in_sidebar"]
    assert set(core.configs) == {row["record"]["page"]["url_path"]}


@pytest.mark.parametrize("change", ["admin", "owner", "system", "inactive", "person", "remote", "credentials", "group"])
async def test_unsuitable_accounts_cannot_be_bound(setup, change):
    core = setup[0]
    if change == "admin":
        core.users[0]["group_ids"] = ["system-admin"]
    if change == "owner":
        core.users[0]["is_owner"] = True
    if change == "system":
        core.users[0]["system_generated"] = True
    if change == "inactive":
        core.users[0]["is_active"] = False
    if change == "person":
        core.people["storage"] = [{"id": "fixture_person", "user_id": "fixture_display"}]
    if change == "remote":
        core.users[0]["local_only"] = False
    if change == "credentials":
        core.users[0]["credentials"] = []
    if change == "group":
        core.users[0]["group_ids"] = ["custom_unknown"]
    with pytest.raises(ValueError, match="Select an active"):
        await select(setup)
    assert not setup[1].screen_identity_path.exists()


@pytest.mark.parametrize("failure", ["wrong_user", "old_press", "future", "no_press", "replay", "expired"])
async def test_session_proof_fails_closed(setup, failure):
    await select(setup)
    await act(setup, "begin", stage="session")
    setup[0].press(NOW + timedelta(seconds=1), user="fixture_owner" if failure == "wrong_user" else "fixture_display")
    if failure == "old_press":
        setup[0].press(NOW - timedelta(seconds=1))
    if failure == "future":
        setup[0].press(NOW + timedelta(hours=1))
    if failure == "no_press":
        setup[0].observed[0]["state"] = "unknown"
    if failure == "replay":
        await act(setup, "observe", NOW + timedelta(seconds=2))
        await act(setup, "begin", NOW + timedelta(seconds=3), stage="restart")
    with pytest.raises(ValueError):
        await act(setup, "observe", NOW + (timedelta(minutes=16) if failure == "expired" else timedelta(seconds=5)))


@pytest.mark.parametrize("change", ["user", "surface", "dashboard", "missing", "unavailable"])
async def test_changed_evidence_invalidates_commissioning(setup, change):
    await restart(setup)
    await act(setup, "physical", NOW + timedelta(seconds=6), dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="device")
    core, store, house, published = setup
    if change == "user":
        core.users[0]["name"] = "Fixture renamed"
    if change == "surface":
        house["surfaces"][0]["area_id"] = "fixture_other_room"
    if change == "dashboard":
        published[0]["fingerprint"] = fingerprint({"changed": True})
    if change == "missing":
        published[0]["status"] = "missing"
    if change == "unavailable":
        core.fail = "config/auth/list"
    result = await identity.inspect(core, store, house, published)
    assert result["screens"][0]["stage"] not in {"commissioned", "authenticated"}
    assert identity.load(store, house)["screens"]["fixture_panel"]["physical"]


@pytest.mark.parametrize("missing", ["dashboard_opened", "default_set", "controls_worked"])
async def test_physical_attestation_must_be_explicit(setup, missing):
    await restart(setup)
    fields = dict(dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="app")
    fields[missing] = False
    with pytest.raises(ValueError, match="explicitly confirm"):
        await act(setup, "physical", NOW + timedelta(seconds=6), **fields)


async def test_uncertain_helper_creation_is_not_repeated(setup):
    await select(setup)
    setup[0].fail = "input_button/create"
    with pytest.raises(CoreError):
        await act(setup, "begin", stage="session")
    setup[0].fail = None
    with pytest.raises(ValueError, match="creation is incomplete"):
        await act(setup, "begin", stage="session")
    assert sum(kind == "input_button/create" for kind, _ in setup[0].commands) == 1


async def test_external_check_page_edits_are_protected(setup):
    await select(setup)
    await act(setup, "begin", stage="session")
    setup[0].press(NOW + timedelta(seconds=1))
    setup[0].configs[next(iter(setup[0].configs))]["title"] = "Fixture external edit"
    with pytest.raises(ValueError, match="check page changed"):
        await act(setup, "observe", NOW + timedelta(seconds=2))


async def test_readonly_wall_restriction_is_explicit_and_does_not_fake_session(setup):
    core, store, house, published = setup
    house["surfaces"][0]["profile"] = "wall"
    with pytest.raises(ValueError):
        await select(setup)
    user = (await identity.accounts(core))[0]
    await act(setup, "restrict", user_id=user["id"], user_signature=user["signature"])
    assert core.users[0]["group_ids"] == ["system-read-only"]
    with pytest.raises(ValueError, match="Read-only accounts cannot press"):
        await act(setup, "begin", stage="session")
    assert (await identity.inspect(core, store, house, published))["screens"][0]["stage"] == "published"
    assert not core.helpers


async def test_reset_does_not_reuse_old_physical_proof(setup):
    await restart(setup)
    before = setup[1].screen_identity_path.read_bytes()
    house = deepcopy(setup[2])
    house["epoch"] += 1
    assert not identity.load(setup[1], house)["screens"]
    assert setup[1].screen_identity_path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("version", 2), ("revision", True), ("screens", []), ("epoch", 99)])
async def test_corrupt_or_future_files_are_preserved(setup, field, value):
    raw = identity.empty(setup[2])
    raw[field] = value
    setup[1].write(setup[1].screen_identity_path, raw)
    before = setup[1].screen_identity_path.read_bytes()
    with pytest.raises(ValueError):
        identity.load(setup[1], setup[2])
    result = await identity.inspect(*setup)
    assert result["issue"]
    assert setup[1].screen_identity_path.read_bytes() == before


async def test_unknown_secret_fields_and_stale_revisions_are_rejected(setup):
    with pytest.raises(ValueError):
        await act(setup, "select", user_id="fixture_display", permission="control", password="never accepted")
    await select(setup)
    with pytest.raises(ValueError, match="changed"):
        await identity.apply(*setup, {"revision": 0, "epoch": 0, "surface": "fixture_panel", "action": "observe", "confirm": True}, "fixture_admin", NOW)


async def test_all_existing_private_files_survive_identity_selection(setup):
    store = setup[1]
    names = ["household.json", "readiness.json", "publications.json", "house-confirmations.json", "music-connection.json", "music-playback.json"]
    for name in names[1:]:
        store.write(store.path.parent / name, {"fictional_preserved_value": name, "context": {"rules": [], "events": {}}})
    before = {name: (store.path.parent / name).read_bytes() for name in names}
    await select(setup)
    assert {name: (store.path.parent / name).read_bytes() for name in names} == before


@pytest.mark.parametrize(
    "role,tracked,accepted",
    [("other", False, True), ("other", True, True), ("adult", False, False), ("child", False, False), ("adult", True, False), ("child", True, False)],
)
async def test_existing_display_only_person_record_can_remain_without_becoming_a_household_member(setup, role, tracked, accepted):
    from homestarter.this_house import digest, empty

    core, store, _, _ = setup
    person = {
        "id": "fixture_display_person",
        "name": "Fixture display record",
        "user_id": "fixture_display",
        "device_trackers": ["device_tracker.fixture_tablet"] if tracked else [],
    }
    core.people["storage"] = [person]
    reviewed = empty()
    reviewed["people"][person["id"]] = {"role": role, "signature": digest([person["id"], person["name"], sorted(person["device_trackers"])])}
    store.write(store.this_house_path, reviewed)
    before = deepcopy(core.people)
    core.users[0]["local_only"] = False
    user = (await identity.accounts(core, store))[0]
    assert user["can_prepare"] is accepted
    if accepted:
        await act(setup, "local_only", user_id=user["id"], user_signature=user["signature"])
        assert core.users[0]["local_only"] is True
        assert identity.load(store, setup[2])["screens"]["fixture_panel"]["prepared"]["change"] == "local_only_enabled"
    else:
        with pytest.raises(ValueError):
            await act(setup, "local_only", user_id=user["id"], user_signature=user["signature"])
    assert core.people == before
    assert not any(kind in {"person/update", "config/auth/create", "config/auth/delete"} for kind, _ in core.commands)


@pytest.mark.parametrize("change", ["tracker", "duplicate_link"])
async def test_stale_or_ambiguous_display_person_review_cannot_prepare_account(setup, change):
    from homestarter.this_house import digest, empty

    core, store, _, _ = setup
    person = {"id": "fixture_display_person", "name": "Fixture display record", "user_id": "fixture_display", "device_trackers": []}
    core.people["storage"] = [person]
    reviewed = empty()
    reviewed["people"][person["id"]] = {"role": "other", "signature": digest([person["id"], person["name"], []])}
    store.write(store.this_house_path, reviewed)
    if change == "tracker":
        person["device_trackers"] = ["device_tracker.fixture_changed"]
    else:
        core.people["storage"].append({**person, "id": "fixture_second_person"})
    core.users[0]["local_only"] = False
    user = (await identity.accounts(core, store))[0]
    assert user["issue"] == "Linked to a HA Person"
    assert user["can_prepare"] is False
    with pytest.raises(ValueError):
        await act(setup, "local_only", user_id=user["id"], user_signature=user["signature"])
    assert core.users[0]["local_only"] is False


async def test_personal_phone_is_not_treated_as_a_fixed_display(setup):
    setup[2]["surfaces"][0]["profile"] = "phone"
    view = await identity.inspect(*setup)
    assert view["screens"][0]["required"] is False
    with pytest.raises(ValueError, match="fixed/shared"):
        await select(setup)


async def test_reconfirming_same_valid_account_keeps_all_evidence_and_revision(setup):
    await restart(setup)
    await act(setup, "physical", NOW + timedelta(seconds=6), dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="browser")
    before = setup[1].screen_identity_path.read_bytes()
    await select(setup)
    assert setup[1].screen_identity_path.read_bytes() == before
    assert (await identity.inspect(*setup))["screens"][0]["stage"] == "commissioned"


async def test_a_different_account_requires_fresh_physical_and_session_checks(setup):
    await restart(setup)
    await act(setup, "physical", NOW + timedelta(seconds=6), dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="app")
    user = deepcopy(setup[0].users[0])
    user.update(id="fixture_second", name="Fixture second display", username="fixture_second")
    setup[0].users.append(user)
    result = await act(setup, "select", user_id=user["id"], permission="control")
    row = result["screens"]["fixture_panel"]
    assert row["session"] is row["restart"] is row["physical"] is None
    assert row["helper"] and row["page"]


async def test_api_is_admin_only_and_does_not_rewrite_existing_settings(make_env):
    from aiohttp.test_utils import TestClient, TestServer
    from homestarter.server import create_app

    env = await make_env("ready")
    store = HouseholdStore(env.settings.data_dir)
    house = store.load()
    house["surfaces"] = [{"id": "fixture_panel", "name": "Fixture panel", "profile": "specialist", "person_id": None, "area_id": None, "audience": "everyone"}]
    house = store.save(house)
    env.mock.users.append(NativeCore().users[0])
    path = "home-starter-fixture-panel"
    config = {"views": [{"title": "Fixture", "cards": []}]}
    env.mock.dashboards.append({"url_path": path})
    env.mock.dashboard_configs[path] = config
    store.write(store.publication_path, {path: {"fingerprint": fingerprint(config)}})
    before = {p.name: p.read_bytes() for p in store.path.parent.iterdir() if p.is_file()}
    async with TestClient(TestServer(create_app(env.settings))) as client:
        headers = {"X-Remote-User-Id": env.mock.users[0]["id"]}
        assert (await client.get("/api/screens/identity")).status == 403
        assert (await client.get("/api/screens/identity", headers={"X-Remote-User-Id": "fixture_display"})).status == 403
        response = await client.get("/api/screens/identity", headers=headers)
        assert response.status == 200
        view = await response.json()
        assert view["screens"][0]["stage"] == "published"
        body = {
            "revision": view["revision"],
            "epoch": view["epoch"],
            "surface": "fixture_panel",
            "action": "select",
            "confirm": True,
            "user_id": "fixture_display",
            "permission": "control",
        }
        assert (await client.post("/api/screens/identity", headers=headers, json={**body, "password": None})).status == 409
        assert (await client.post("/api/screens/identity", headers=headers, json=body)).status == 200
        assert (await client.post("/api/screens/identity", headers=headers, json=body)).status == 409
        loaded = await (await client.get("/api/screens/identity", headers=headers)).json()
        assert loaded["screens"][0]["record"]["session"] is None
    assert all((store.path.parent / name).read_bytes() == content for name, content in before.items() if name != "inventory-history.json")
