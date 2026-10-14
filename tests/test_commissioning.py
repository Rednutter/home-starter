"""Flow-level contracts: no writes before Go, independent results, safe return."""

import asyncio
import copy

import pytest
from aiohttp.test_utils import TestClient, TestServer
from homestarter import commissioning as c
from homestarter.household import HouseholdStore
from homestarter.server import K_STATE, create_app


async def client_for(env):
    client = TestClient(TestServer(create_app(env.settings, env.session)))
    await client.start_server()
    return client, {"X-Remote-User-Id": env.mock.users[0]["id"]}


async def get(client, headers):
    response = await client.get("/api/commissioning", headers=headers)
    assert response.status == 200, await response.text()
    return await response.json()


async def action(client, headers, state, name, **extra):
    response = await client.post("/api/commissioning/" + name, json={"revision": state["revision"], "epoch": state["epoch"], **extra}, headers=headers)
    assert response.status == 200, await response.text()
    return (await response.json())["state"]


async def wait_result(client, headers):
    for _ in range(100):
        state = (await get(client, headers))["state"]
        if state["phase"] != "executing":
            return state
        await asyncio.sleep(0.01)
    pytest.fail("Commissioning did not return a result")


async def reviewed(client, headers, selected=(), *, screens=False):
    state = (await get(client, headers))["state"]
    state = await action(client, headers, state, "start")
    state = await action(client, headers, state, "scan")
    draft = copy.deepcopy(state["draft"])
    draft["house"]["people"] = [
        {"id": "example_adult", "name": "Example adult", "audience": "adult"},
        {"id": "example_child", "name": "Example child", "audience": "everyone"},
    ]
    draft["readiness"]["members"] = {
        p["id"]: {"kind": "adult" if p["audience"] == "adult" else "child", "rooms": [], "devices": [], "presence": [], "access": "later"}
        for p in draft["house"]["people"]
    }
    draft["selected"] = list(selected)
    for key in c.r.CAPABILITIES:
        draft["readiness"]["choices"][key] = {
            "intent": "wanted" if key in selected else "later",
            "sources": [],
            "screens": [],
            "answers": {},
            "permissions": {},
        }
    if screens:
        draft["house"]["surfaces"] = [
            {"id": "example_phone", "name": "Example phone", "profile": "phone", "person_id": "example_adult", "area_id": None, "audience": "everyone"}
        ]
        draft["publish_ids"] = ["example_phone"]
    state = await action(client, headers, state, "save", step="household", draft=draft)
    assert state["phase"] == "household_defined"
    state = await action(client, headers, state, "save", step="choose", draft=state["draft"])
    state = await action(client, headers, state, "save", step="configure", draft=state["draft"])
    return await action(client, headers, state, "review")


@pytest.mark.parametrize(
    "scenario,selected",
    [
        ("simple", ("displays",)),
        ("complex", ()),
        ("music_no_provider", ("music",)),
        ("no_bins", ("waste",)),
        ("communications", ("communications",)),
        ("minimal_skip", ()),
    ],
)
async def test_complete_commissioning_scenarios(make_env, scenario, selected):
    env = await make_env("ready" if scenario in ("complex", "music_no_provider") else "absent", fresh=True)
    client, headers = await client_for(env)
    store = client.server.app[K_STATE].household
    try:
        initial = await get(client, headers)
        assert initial["state"]["phase"] == "not_started" and initial["state"]["draft"]["selected"] == []
        assert "discovery" not in initial and not store.path.exists()
        state = await reviewed(client, headers, selected, screens=scenario == "simple")
        assert state["phase"] == "reviewed" and not store.path.exists() and not env.mock.dashboard_configs
        assert not any(method == "POST" for method, _ in env.mock.calls)
        assert state["review"]["automatic"] and state["review"]["draft_hash"]
        if scenario == "music_no_provider":
            assert state["review"]["music_state"] == "ready"
            assert not state["draft"]["readiness"]["choices"]["music"]["answers"]
        if scenario == "communications":
            assert state["draft"]["readiness"]["choices"]["communications"]["permissions"] == {}
        if scenario == "no_bins":
            assert state["review"]["checks"]["waste"]["status"] == "incomplete"
        state = await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        assert state["phase"] == "executing"
        state = await wait_result(client, headers)
        assert state["results"]["household"]["status"] == "verified" and store.load()["configured"]
        if selected:
            assert state["phase"] == "verification_incomplete"
            if scenario == "simple":
                assert state["results"]["display:example_phone"]["status"] == "published"
                assert "calendar." not in str(env.mock.dashboard_configs) and "Bins" not in str(env.mock.dashboard_configs)
                state = await action(client, headers, state, "display", key="display:example_phone", confirm=True)
                assert state["results"]["display:example_phone"]["verification"] == "user_confirmed_display"
            else:
                assert state["results"][selected[0]]["status"] == "incomplete"
                state = await action(client, headers, state, "skip", key=selected[0], confirm=True)
                assert state["results"][selected[0]]["status"] == "skipped"
                assert c.r.load(store, store.load())["choices"][selected[0]]["intent"] == "later"
        assert state["phase"] == "commissioned" and not state["active"]
        saved = copy.deepcopy(store.load())
        for _ in range(2):
            assert (await get(client, headers))["state"]["phase"] == "commissioned"
            assert store.load() == saved
    finally:
        await client.close()


async def test_pre_go_writes_stale_review_and_unauthorised_requests_are_rejected(make_env):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        assert (await client.get("/api/commissioning")).status == 403
        assert (await client.post("/api/commissioning/start", json={"revision": 0, "epoch": 0})).status == 403
        for route in (
            "/api/household",
            "/api/readiness/save",
            "/api/music/setup",
            "/api/inventory/area",
            "/api/surfaces/example/publish",
            "/api/installation/complete",
        ):
            assert (await client.post(route, json={"confirm": True}, headers=headers)).status == 409
        state = await reviewed(client, headers)
        bad = await client.post(
            "/api/commissioning/go", json={"revision": state["revision"], "epoch": state["epoch"], "token": "old-plan", "confirm": True}, headers=headers
        )
        assert bad.status == 409
        app = client.server.app[K_STATE]
        current = app.household.load()
        app.household.save(current)
        stale = await client.post(
            "/api/commissioning/go",
            json={"revision": state["revision"], "epoch": state["epoch"], "token": state["review"]["token"], "confirm": True},
            headers=headers,
        )
        assert stale.status == 409 and not env.mock.dashboard_configs
    finally:
        await client.close()


async def test_legacy_home_is_not_commissioned_or_forced_back_into_onboarding(make_env):
    env = await make_env("ready")
    client, headers = await client_for(env)
    try:
        store = client.server.app[K_STATE].household
        house = store.load()
        house["people"] = [{"id": f"occupant{n}", "name": f"Example occupant {n}", "audience": "adult" if n < 2 else "everyone"} for n in range(5)]
        house["surfaces"] = [
            {"id": f"existing{n}", "name": f"Example screen {n}", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}
            for n in range(3)
        ]
        store.save(house)
        env.mock.dashboard_configs["example-existing-dashboard"] = {"title": "Example existing", "views": []}
        dashboards = copy.deepcopy(env.mock.dashboard_configs)
        state = (await get(client, headers))["state"]
        assert state["legacy"] and not state["active"] and state["phase"] == "not_started"
        assert not state["draft"]["publish_ids"]
        assert len(state["draft"]["house"]["people"]) == 5
        saved = client.server.app[K_STATE].household.load()
        state = await action(client, headers, state, "start")
        assert state["phase"] == "preparing"
        state = await action(client, headers, state, "leave")
        assert not state["active"] and client.server.app[K_STATE].household.load() == saved
        assert env.mock.dashboard_configs == dashboards
    finally:
        await client.close()


def test_corrupt_and_future_commissioning_fail_closed(tmp_path):
    store = HouseholdStore(str(tmp_path))
    store.write(store.commissioning_path, {"version": 99, "epoch": 0})
    with pytest.raises(ValueError, match="preserved"):
        c.load(store)


async def test_local_save_interruption_resumes_without_destroying_other_work(make_env, monkeypatch):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers)
        store = client.server.app[K_STATE].household
        original = store.write
        failed = False

        def fail_once(path, value):
            nonlocal failed
            if path == store.readiness_path and not failed:
                failed = True
                raise OSError("Fixture interrupted sidecar write")
            return original(path, value)

        monkeypatch.setattr(store, "write", fail_once)
        await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        state = await wait_result(client, headers)
        assert state["phase"] == "verification_incomplete" and store.load()["people"]
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert state["phase"] == "commissioned" and len(store.load()["people"]) == 2
        assert not env.mock.dashboard_configs
    finally:
        await client.close()


async def test_interrupted_execution_requires_explicit_resume(make_env):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers)
        state["phase"] = "executing"
        c.write(client.server.app[K_STATE].household, state)
        state = (await get(client, headers))["state"]
        assert state["phase"] == "verification_incomplete" and not env.mock.dashboard_configs
        assert not client.server.app[K_STATE].household.path.exists()
    finally:
        await client.close()


async def test_publication_failure_preserves_other_screen_and_retry_does_not_rewrite_it(make_env, monkeypatch):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers, ["displays"], screens=True)
        draft = state["draft"]
        draft["house"]["surfaces"].append({**draft["house"]["surfaces"][0], "id": "example_tablet", "name": "Example tablet"})
        draft["publish_ids"].append("example_tablet")
        state = await action(client, headers, state, "save", step="configure", draft=draft)
        state = await action(client, headers, state, "review")
        original = c.publish
        attempts = []

        async def fail_phone_once(core, generated, expected, records):
            identifier = generated["surface"]["id"]
            attempts.append(identifier)
            if identifier == "example_phone" and attempts.count(identifier) == 1:
                raise ValueError("Fixture protected/conflicting screen")
            return await original(core, generated, expected, records)

        monkeypatch.setattr(c, "publish", fail_phone_once)
        await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        state = await wait_result(client, headers)
        assert state["results"]["display:example_phone"]["status"] == "incomplete"
        assert state["results"]["display:example_tablet"]["status"] == "published"
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert state["results"]["display:example_phone"]["status"] == "published"
        assert attempts == ["example_phone", "example_tablet", "example_phone"]
    finally:
        await client.close()


async def test_music_installer_is_explicit_post_go_and_not_replayed(make_env, monkeypatch):
    from types import SimpleNamespace

    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        setup = client.server.app[K_STATE].setup
        calls = []
        monkeypatch.setattr(setup, "start", lambda user: calls.append(user) or SimpleNamespace(id="example-operation"))
        state = await reviewed(client, headers, ["music"])
        draft = state["draft"]
        draft["install_music"] = True
        state = await action(client, headers, state, "save", step="configure", draft=draft)
        state = await action(client, headers, state, "review")
        assert not calls
        await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        state = await wait_result(client, headers)
        assert len(calls) == 1 and state["results"]["music"]["status"] == "incomplete"
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert len(calls) == 1 and state["phase"] == "verification_incomplete"
    finally:
        await client.close()


async def test_music_retry_requires_device_progress_and_hearing(make_env):
    from mock_music_runtime import TOKEN

    env = await make_env("ready", fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers, ["music"])
        await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        state = await wait_result(client, headers)
        assert state["results"]["music"]["status"] == "incomplete"
        runtime = client.app[K_STATE].music_runtime
        await runtime.connect(TOKEN)
        runtime.interval = 0.01
        original = runtime.sample

        async def progress(*args):
            value = await original(*args)
            env.mock.music_api.started -= 3
            return value

        runtime.sample = progress
        observed = await runtime.observe("fixture_radio", "fixture_speaker", headers["X-Remote-User-Id"])
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert state["results"]["music"]["status"] == "incomplete"
        await runtime.heard(observed["id"], headers["X-Remote-User-Id"])
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert state["results"]["music"]["status"] == "verified"
        assert state["phase"] == "commissioned"
        assert not env.mock.music_api.calls or all(
            command in {"providers", "config/providers", "players/all", "players/get", "player_queues/get_active_queue"}
            for command, _ in env.mock.music_api.calls
        )
    finally:
        await client.close()


async def test_edit_before_go_keeps_the_entire_unapplied_plan(make_env):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers, ["displays"], screens=True)
        draft = copy.deepcopy(state["draft"])
        state = await action(client, headers, state, "edit")
        assert state["phase"] == "configuration_incomplete" and state["draft"] == draft
        assert not client.server.app[K_STATE].household.path.exists()
        state = await action(client, headers, state, "review")
        assert len(state["review"]["screens"]) == 1
    finally:
        await client.close()


async def test_retry_retains_explicit_skip_of_unconfigured_displays(make_env):
    env = await make_env(fresh=True)
    client, headers = await client_for(env)
    try:
        state = await reviewed(client, headers, ["displays", "music"])
        await action(client, headers, state, "go", token=state["review"]["token"], confirm=True)
        state = await wait_result(client, headers)
        state = await action(client, headers, state, "skip", key="displays", confirm=True)
        await action(client, headers, state, "retry")
        state = await wait_result(client, headers)
        assert state["results"]["displays"]["status"] == "skipped"
        state = await action(client, headers, state, "skip", key="music", confirm=True)
        assert state["phase"] == "commissioned"
    finally:
        await client.close()
