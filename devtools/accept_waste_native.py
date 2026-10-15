"""Fictional waste service → native Template helpers → conditional UI → expiry.

Disposable HA at loopback only. No calendar writes, address uploads or hardware calls.
The test-only clock controls relevance; native availability uses HA's real clock.
"""

import asyncio
import copy
import json
import sys
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp.test_utils import TestClient, TestServer
from playwright.async_api import async_playwright, expect

BASE = "http://127.0.0.1:18123"
ROOT = Path(".runtime/waste-native-acceptance")
SHOTS = Path("screens/waste-ui")


async def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from accept_screen_identity_native import login
    from homestarter import waste, waste_runtime
    from homestarter.household import HouseholdStore
    from homestarter.server import K_STATE, create_app
    from homestarter.settings import Settings
    from homestarter.surfaces import generate, publish
    from ingress_proxy import build_app
    from mock_supervisor import TOKEN, MockSupervisor
    from waste_scenarios import FictionalProvider

    ROOT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    async with aiohttp.ClientSession() as session:
        token = await login(session, credentials)
        mock = MockSupervisor("ready", core_url=BASE, core_token=token, ma_host="127.0.0.1")
        async with TestServer(mock.app()) as supervisor, TestServer(mock.ma_app()) as ma:
            mock.ma_port = ma.port
            settings = Settings.from_env(
                {
                    "SUPERVISOR_TOKEN": TOKEN,
                    "HOME_STARTER_SUPERVISOR_URL": str(supervisor.make_url("")),
                    "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
                    "HOME_STARTER_DATA_DIR": str(ROOT.resolve()),
                    "HOME_STARTER_MA_PORT": str(ma.port),
                }
            )
            store = HouseholdStore(settings.data_dir)
            house = store.load()
            if not house["surfaces"]:
                house["surfaces"] = [
                    {"id": "waste_acceptance", "name": "Fixture waste panel", "profile": "tablet", "person_id": None, "area_id": None, "audience": "everyone"}
                ]
                house = store.save(house)
            # Keep owned helper identities across acceptance reruns.
            owned = store.read(waste.path(store), waste.empty(house))["helpers"]
            initial = waste.empty(house)
            initial["helpers"] = owned
            store.write(waste.path(store), initial)
            before = {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file() and p.name not in {"waste-collection.json", "inventory-history.json"}}
            original_view = waste.view
            clock = [None]

            def scene(value, zone, now=None):
                if clock[0] is None:
                    return original_view(value, zone, now)
                value = copy.deepcopy(value)
                if value["verified_at"]:
                    age = datetime.now(UTC) - waste.timestamp(value["verified_at"])
                    value["verified_at"] = (clock[0] - age).isoformat()
                return original_view(value, zone, clock[0])

            waste.view = scene
            try:
                app = create_app(settings, session)
                async with TestClient(TestServer(app)) as client:
                    state = app[K_STATE]
                    state.waste_provider = FictionalProvider()
                    state.waste_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await state.waste_task
                    core = state.core
                    async with core.websocket() as ws:
                        actor = (await ws.command("auth/current_user"))["id"]
                    headers = {"X-Remote-User-Id": actor}
                    async with TestServer(build_app(str(client.make_url("")), user_id=actor)) as ingress:
                        async with async_playwright() as pw:
                            browser = await pw.chromium.launch()
                            context = await browser.new_context(viewport={"width": 1280, "height": 900})
                            page = await context.new_page()
                            errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            await page.goto(str(ingress.make_url("/home_starter")))
                            frame = page.frame_locator("#panel")
                            await frame.get_by_role("link", name="Home Readiness", exact=True).wait_for()
                            await frame.get_by_text("Waste collection", exact=True).click()
                            await expect(frame.locator("#waste-body")).to_contain_text("Collection day not yet confirmed")

                            async def capture(name):
                                await page.wait_for_load_state("networkidle")
                                await frame.locator("#waste-collection > summary").evaluate(
                                    "e=>window.scrollTo(0,e.getBoundingClientRect().top+window.scrollY-24)"
                                )
                                await page.screenshot(path=str(SHOTS / ("desktop-" + name + ".png")))
                                await page.set_viewport_size({"width": 390, "height": 844})
                                await frame.locator("#waste-collection > summary").evaluate(
                                    "e=>window.scrollTo(0,e.getBoundingClientRect().top+window.scrollY-24)"
                                )
                                assert await frame.locator("body").evaluate("e=>e.scrollWidth<=e.clientWidth")
                                await page.screenshot(path=str(SHOTS / ("mobile-" + name + ".png")))
                                await page.set_viewport_size({"width": 1280, "height": 900})

                            await capture("initial")
                            await frame.get_by_role("button", name="Check Wodonga collection service", exact=True).click()
                            await expect(frame.locator("#waste-status")).to_contain_text("Review the collection day", timeout=20000)
                            await frame.get_by_role("checkbox", name="Fixture waste panel", exact=True).check()
                            await frame.get_by_role("button", name="Confirm service and create bin entities", exact=True).click()
                            await expect(frame.locator("#waste-status")).to_contain_text("verified", timeout=30000)
                            response = await client.get("/api/waste", headers=headers)
                            data = await response.json()
                            assert response.status == 200 and data["configured"] and data["entities_ready"], data
                            await capture("confirmed")
                            saved = waste.load(store, house)
                            assert len(saved["helpers"]) == 6
                            assert all((ROOT / name).read_bytes() == body for name, body in before.items())

                            async def states():
                                return {s["entity_id"]: s for s in await core.states()}

                            async def wait_state(entity, expected, seconds=10):
                                for _ in range(seconds * 5):
                                    current = await states()
                                    if current.get(entity, {}).get("state") == expected:
                                        return current
                                    await asyncio.sleep(0.2)
                                raise AssertionError(f"Native state mismatch: {entity} expected {expected}")

                            async def set_scene(when):
                                clock[0] = datetime.fromisoformat(when).replace(tzinfo=ZoneInfo("Australia/Melbourne"))
                                await waste_runtime.project(core, store, house)
                                await frame.get_by_role("button", name="Refresh saved waste state", exact=True).click()

                            await set_scene("2026-10-14T19:00:00")
                            await expect(frame.locator("#waste-body")).to_contain_text("Bins tonight")
                            await wait_state("binary_sensor.home_starter_bin_night", "on")
                            native_states = await wait_state("sensor.home_starter_next_bin_collection", "2026-10-15")
                            assert native_states["sensor.home_starter_next_bin_types"]["state"] == "Green · Recycling"
                            assert native_states["sensor.home_starter_bin_days_until"]["state"] == "1"
                            assert native_states["sensor.home_starter_bin_collection_day"]["state"] == "Thursday"
                            await capture("evening")
                            surface = house["surfaces"][0]
                            generated = generate(house, surface, [], [], policy={"bin_context_screens": [surface["id"]]})
                            records = store.read(store.publication_path, {})
                            result = await publish(core, generated, records.get(generated["url_path"], {}).get("fingerprint"), records)
                            records[result["url_path"]] = result
                            store.write(store.publication_path, records)
                            native_page = await context.new_page()
                            await native_page.goto(BASE + "/" + generated["url_path"] + "/home")
                            await native_page.get_by_label("Username", exact=True).fill(credentials["username"])
                            await native_page.get_by_label("Password", exact=True).fill(credentials["password"])
                            await native_page.get_by_role("button", name="Log in", exact=True).click()
                            await expect(native_page.get_by_text("Bins tonight", exact=True)).to_be_visible(timeout=30000)
                            assert await native_page.locator("hui-error-card").count() == 0
                            await native_page.screenshot(path=str(SHOTS / "native-evening.png"))
                            await set_scene("2026-10-15T05:30:00")
                            await expect(frame.locator("#waste-body")).to_contain_text("Bins out this morning")
                            await wait_state("binary_sensor.home_starter_bin_night", "off")
                            await expect(native_page.get_by_text("Bins out this morning", exact=True)).to_be_visible()
                            await capture("morning")
                            await native_page.screenshot(path=str(SHOTS / "native-morning.png"))
                            await set_scene("2026-10-15T06:00:00")
                            await wait_state("sensor.home_starter_bin_context", "quiet")
                            await expect(native_page.get_by_text("Bins out this morning", exact=True)).not_to_be_visible()
                            await native_page.screenshot(path=str(SHOTS / "native-quiet.png"))
                            current = waste.load(store, house)
                            current["error"] = {"kind": "unavailable", "message": "Fictional Council outage"}
                            waste.save(store, current)
                            await set_scene("2026-10-14T19:00:00")
                            await expect(frame.locator("#waste-body")).to_contain_text("last known valid")
                            await wait_state("binary_sensor.home_starter_bin_night", "on")
                            current = waste.load(store, house)
                            current["verified_at"] = (datetime.now(UTC) - timedelta(days=8)).isoformat()
                            waste.save(store, current)
                            await set_scene("2026-10-14T19:00:00")
                            await expect(frame.locator("#waste-body")).to_contain_text("Bin schedule needs checking")
                            await wait_state("binary_sensor.home_starter_bin_night", "unavailable")
                            await capture("stale")
                            await expect(native_page.get_by_text("Bin schedule needs checking", exact=True)).to_be_visible()
                            await native_page.screenshot(path=str(SHOTS / "native-stale.png"))
                            # HA evaluates now() itself after the app's data heartbeat expires.
                            clock[0] = None
                            current = waste.load(store, house)
                            current.update(error=None, verified_at=datetime.now(UTC).isoformat())
                            waste.save(store, current)
                            await waste_runtime.project(core, store, house)
                            live = (await states())[waste.SOURCE_ENTITY]
                            live["attributes"]["bin_night"] = True
                            live["attributes"]["valid_until"] = (datetime.now(UTC) + timedelta(seconds=2)).isoformat()
                            await core.context_state(waste.SOURCE_ENTITY, {"state": live["state"], "attributes": live["attributes"]})
                            await wait_state("binary_sensor.home_starter_bin_night", "on")
                            print("Native setup, six helpers, dates/types, evening/morning/quiet/stale rendering: PASS; awaiting native expiry", flush=True)
                            await wait_state("binary_sensor.home_starter_bin_night", "unavailable", seconds=70)
                            assert not errors, errors
                            await browser.close()
                    preserved = waste.load(store, house)
                async with TestClient(TestServer(create_app(settings, session))) as restarted:
                    response = await restarted.get("/api/waste", headers=headers)
                    assert response.status == 200 and (await response.json())["entities_ready"]
                    assert waste.load(store, house) == preserved
                assert store.path.read_bytes() == before["household.json"]
                assert all(word not in waste.path(store).read_text().lower() for word in ("latitude", "longitude", "password", "address"))
            finally:
                waste.view = original_view
    print("Native expiry after stopped projection, app restart, persisted ownership and privacy: PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
