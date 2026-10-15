"""Reference panel rendered and operated by a non-admin on disposable HA only."""

import asyncio
import copy
import json
import sys
from pathlib import Path

import aiohttp
from accept_screen_identity_native import BASE, login
from playwright.async_api import async_playwright, expect

ROOT = Path(".runtime/panel-native")
SHOTS = Path("screens/panel-ui")


async def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter.core import CoreClient
    from homestarter.household import empty_household
    from homestarter.inventory import collect_inventory
    from homestarter.settings import Secret
    from homestarter.surfaces import classify, generate, publish

    ROOT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    owner = json.loads(Path("screens/v3-core-credentials.json").read_text())
    display = json.loads(Path(".runtime/screen-probe-credentials.json").read_text())
    async with aiohttp.ClientSession() as session:
        token = await login(session, owner)
        headers = {"Authorization": "Bearer " + token}
        core = CoreClient(session, BASE + "/api", BASE.replace("http", "ws") + "/api/websocket", Secret(token))
        async with core.websocket() as ws:
            resources = await ws.command("lovelace/resources/list")
            if not any(r["url"].startswith("/local/button-card.js") for r in resources):
                await ws.command("lovelace/resources/create", url="/local/button-card.js?v=7.0.1", res_type="module")
            await ws.command("config/auth/update", user_id=display["user_id"], group_ids=["system-users"], local_only=False)
        inv, states = await collect_inventory(core), await core.states()
        climate = next(s for s in states if s["entity_id"] == "climate.kitchen_air_conditioning")
        original_target = climate["attributes"]["temperature"]
        house = empty_household()
        house["people"] = [{"id": "alex", "name": "Alex", "audience": "adult"}, {"id": "sam", "name": "Sam", "audience": "everyone"}]
        surface = {
            "id": "panel_acceptance",
            "name": "Fixture household panel",
            "profile": "specialist",
            "area_id": "fixture_kitchen",
            "person_id": None,
            "audience": "everyone",
        }
        house["surfaces"] = [surface]
        items = [i for i in classify(inv, states, {}) if i["entity_id"] == climate["entity_id"]]
        assert len(items) == 1 and items[0]["usable"], "Disposable thermostat must report normally"
        items[0]["area_id"] = "fixture_kitchen"
        items[0]["platform"] = "airtouch5"  # Fictional adapter label; native services remain real.
        weather = {"entity_id": "weather.fixture_panel", "state": "partlycloudy", "attributes": {"temperature": 14, "temperature_unit": "°C"}}
        async with session.post(BASE + "/api/states/" + weather["entity_id"], headers=headers, json=weather) as response:
            assert response.status in (200, 201)
        items += classify({"devices": [], "unattached_entities": [{**weather, "name": "Fixture weather", "observed": True}]}, [weather], {})
        areas = [{"area_id": "fixture_kitchen", "name": "Fixture kitchen"}]
        before = copy.deepcopy(house)
        records_path = ROOT / "publications.json"
        records = json.loads(records_path.read_text()) if records_path.exists() else {}
        generated = generate(house, surface, items, areas, policy={"landscape_panel": True})
        assert generated["config"]["views"][0]["cards"][0]["variables"]["panel"]["weather"] == weather["entity_id"]
        result = await publish(core, generated, records.get(generated["url_path"], {}).get("fingerprint"), records)
        records[result["url_path"]] = result
        records_path.write_text(json.dumps(records))
        assert house == before
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda err: errors.append(str(err)))
            await page.goto(BASE + "/" + result["url_path"] + "/home")
            await page.get_by_label("Username", exact=True).fill(display["username"])
            await page.get_by_label("Password", exact=True).fill(display["password"])
            await page.get_by_role("button", name="Log in", exact=True).click()
            try:
                await expect(page.get_by_role("main", name="Fixture household panel")).to_be_visible(timeout=30000)
            except AssertionError:
                print("Panel browser errors:", errors)
                print(
                    "Panel cards:",
                    await page.locator("button-card").evaluate_all(
                        "els=>els.map(e=>({text:e.shadowRoot?.textContent?.slice(-2000),html:e.shadowRoot?.querySelector('#container')?.innerHTML?.slice(0,2000)}))"
                    ),
                )
                await page.screenshot(path=str(SHOTS / "load-failure.png"))
                raise
            if await page.get_by_role("button", name="Sidebar toggle", exact=True).is_visible():
                await page.get_by_role("button", name="Sidebar toggle", exact=True).click()
                await page.wait_for_timeout(300)  # HA drawer's native close transition.
            await expect(page.get_by_text("No verified commitments to show", exact=True)).to_be_visible()
            await expect(page.get_by_role("link", name="Open climate controls", exact=True)).to_be_visible()
            await expect(page.get_by_role("navigation", name="Household", exact=True)).to_be_visible()
            assert await page.locator("hui-error-card").count() == 0
            style = await page.locator(".hs-climate").evaluate(
                "el=>({image:getComputedStyle(el).backgroundImage!=='none',backdrop:getComputedStyle(el).getPropertyValue('--hs-backdrop').length})"
            )
            assert style["image"] and 0 < style["backdrop"] < 1_000_000
            layout_issues = []
            for name, width, height in [("landscape", 1280, 800), ("compact-landscape", 1024, 600), ("narrow", 390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.evaluate("()=>document.fonts.ready")
                await page.evaluate("()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                await page.screenshot(path=str(SHOTS / (name + ".png")), full_page=True)
                header = await page.locator(".hs-header").bounding_box()
                await expect(page.locator(".hs-weather")).to_contain_text("14°")
                assert header and header["height"] < 70, "Weather icon must not expand the header"
                assert await page.locator(".hs-panel").evaluate("el=>el.scrollWidth<=el.clientWidth+1")
                if width > 720:
                    bounds = await page.locator(".hs-nav").evaluate("el=>({bottom:el.getBoundingClientRect().bottom,height:innerHeight})")
                    if bounds["bottom"] > height + 1:
                        layout_issues.append((name, bounds))
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.get_by_role("link", name="Open climate controls", exact=True).click()
            await expect(page.locator("hui-thermostat-card")).to_be_visible()
            thermostat = page.locator("hui-thermostat-card").first
            assert await thermostat.get_by_role("button").count() == 3
            assert await thermostat.get_by_role("button").nth(2).get_attribute("aria-label") == "Show more information"

            async def target_matches(condition):
                for _ in range(40):
                    live = await core.rest_get("/states/" + climate["entity_id"])
                    if condition(live["attributes"]["temperature"]):
                        return
                    await asyncio.sleep(0.25)
                raise AssertionError("Native thermostat target did not match the control action")

            try:
                await thermostat.get_by_role("button").nth(1).click()  # Native HA plus button has no label.
                await target_matches(lambda t: t > original_target)
                await thermostat.get_by_role("button").nth(0).click()  # Native HA minus button has no label.
                await target_matches(lambda t: t == original_target)
            finally:
                async with session.post(
                    BASE + "/api/services/climate/set_temperature", headers=headers, json={"entity_id": climate["entity_id"], "temperature": original_target}
                ) as restored:
                    assert restored.status == 200
            await page.screenshot(path=str(SHOTS / "native-climate-controls.png"))
            await page.goto(BASE + "/" + result["url_path"] + "/home")
            await page.get_by_role("link", name="Alex", exact=True).click()
            await expect(page.get_by_role("heading", name="Air conditioning", exact=True)).to_be_visible()
            assert await page.locator("hui-error-card").count() == 0
            await page.goto(BASE + "/" + result["url_path"] + "/home")
            await page.reload()
            await expect(page.get_by_role("main", name="Fixture household panel")).to_be_visible()

            async def show_scene(scene):
                saved = await publish(core, scene, records[scene["url_path"]]["fingerprint"], records)
                records[saved["url_path"]] = saved
                records_path.write_text(json.dumps(records))
                await page.reload()
                await settled()

            async def settled():
                await page.wait_for_load_state("networkidle")
                await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible()
                await page.evaluate("document.fonts.ready")
                await page.evaluate("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))")

            # Fixture-only unavailable entity: never falsify the working thermostat.
            offline_items = copy.deepcopy(items)
            offline_items[0].update(id="climate.fixture_panel_offline", entity_id="climate.fixture_panel_offline", state="unavailable", usable=False)
            async with session.post(
                BASE + "/api/states/climate.fixture_panel_offline", headers=headers, json={"state": "unavailable", "attributes": climate["attributes"]}
            ) as response:
                assert response.status in (200, 201)
            await show_scene(generate(house, surface, offline_items, areas, policy={"landscape_panel": True}))
            await expect(page.get_by_text("Connection unavailable", exact=True)).to_be_visible()
            await page.screenshot(path=str(SHOTS / "offline.png"))
            # Activity evidence uses a virtual fixture, never starts real cooling.
            idle_items = copy.deepcopy(offline_items)
            idle_items[0].update(state="cool", usable=True)
            async with session.post(
                BASE + "/api/states/climate.fixture_panel_offline",
                headers=headers,
                json={"state": "cool", "attributes": {**climate["attributes"], "hvac_action": "idle"}},
            ) as response:
                assert response.status == 200
            await show_scene(generate(house, surface, idle_items, areas, policy={"landscape_panel": True}))
            await expect(page.get_by_text("Idle", exact=True)).to_be_visible()
            await page.screenshot(path=str(SHOTS / "idle.png"))
            # Same fixture projection contract as the waste acceptance; restore it.
            source = next((s for s in await core.states() if s["entity_id"] == "sensor.home_starter_bin_source"), {"state": "unavailable", "attributes": {}})

            async def source_scene(expired=False):
                from datetime import UTC, datetime, timedelta

                until = datetime.now(UTC) + timedelta(minutes=-1 if expired else 2)
                async with session.post(
                    BASE + "/api/states/sensor.home_starter_bin_source",
                    headers=headers,
                    json={
                        "state": "current",
                        "attributes": {
                            **source["attributes"],
                            "attention": "tonight",
                            "summary": "Bins tonight\n\nGreen · Recycling",
                            "valid_until": until.isoformat(),
                        },
                    },
                ) as response:
                    assert response.status in (200, 201)

            try:
                await source_scene()
                await show_scene(generate(house, surface, items, areas, policy={"landscape_panel": True, "bin_context_screens": [surface["id"]]}))
                await expect(page.get_by_text("Green · Recycling", exact=False)).to_be_visible()
                await page.screenshot(path=str(SHOTS / "bins-tonight.png"))
                await source_scene(expired=True)
                await page.reload()
                await settled()
                await expect(page.get_by_text("Bin schedule needs checking", exact=True)).to_be_visible()
                await page.screenshot(path=str(SHOTS / "stale.png"))
            finally:
                async with session.post(
                    BASE + "/api/states/sensor.home_starter_bin_source", headers=headers, json={"state": source["state"], "attributes": source["attributes"]}
                ) as response:
                    assert response.status == 200
                await show_scene(generated)
            assert not errors, errors
            assert not layout_issues, layout_issues
            await browser.close()
    print("Native landscape/narrow rendering, non-admin navigation, climate increase/restore and reload: PASS")


if __name__ == "__main__":
    asyncio.run(main())
