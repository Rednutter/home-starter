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
KIOSK = "--kiosk" in sys.argv


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
            if KIOSK and not any(r["url"].startswith("/local/kiosk-mode.js") for r in resources):
                await ws.command("lovelace/resources/create", url="/local/kiosk-mode.js?v=15.0.0", res_type="module")
            await ws.command("config/auth/update", user_id=display["user_id"], group_ids=["system-users"], local_only=False)
            users = await ws.command("config/auth/list")
            display_name = next(u["name"] for u in users if u["id"] == display["user_id"])
        inv, states = await collect_inventory(core), await core.states()
        for _ in range(40):
            if any(s["entity_id"] == "climate.kitchen_air_conditioning" for s in states):
                break
            await asyncio.sleep(0.5)
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
        if KIOSK:
            surface["kiosk"] = True
        panel_policy = {"landscape_panel": True, **({"kiosk_user_name": display_name} if KIOSK else {})}
        items = [i for i in classify(inv, states, {}) if i["entity_id"] == climate["entity_id"]]
        assert len(items) == 1 and items[0]["usable"], "Disposable thermostat must report normally"
        items[0]["area_id"] = "fixture_kitchen"
        items[0]["platform"] = "airtouch5"  # Fictional adapter label; native services remain real.
        items[0]["attributes"]["fan_modes"] = ["auto"]  # Identify the main unit, as AirTouch does.
        # Render a full-sized fictional system; only the real fixture thermostat is operated.
        for index, name in enumerate(["Kitchen / dining / living", "Lounge", "Main bedroom", "Bedroom two", "Bedroom three", "Bedroom four"]):
            for domain in ("climate", "cover"):
                entity_id = f"{domain}.fixture_panel_zone_{index}"
                attrs = (
                    {
                        "friendly_name": name,
                        "temperature": 25,
                        "current_temperature": None if index == 1 else 21.5,
                        "hvac_modes": ["off", "fan_only"],
                        "supported_features": 385,
                        "min_temp": 16,
                        "max_temp": 35,
                    }
                    if domain == "climate"
                    else {"friendly_name": name + " airflow", "device_class": "damper", "current_position": 60, "supported_features": 0}
                )
                state = {"entity_id": entity_id, "state": "fan_only" if domain == "climate" else "open", "attributes": attrs}
                async with session.post(BASE + "/api/states/" + entity_id, headers=headers, json=state) as response:
                    assert response.status in (200, 201)
                items += classify(
                    {
                        "devices": [],
                        "unattached_entities": [
                            {
                                "entity_id": entity_id,
                                "name": attrs["friendly_name"],
                                "platform": "airtouch5",
                                "device_id": f"fixture_zone_{index}",
                                "observed": True,
                                "state": state["state"],
                                "area_id": "fixture_kitchen",
                            }
                        ],
                    },
                    [state],
                    {},
                )
        weather = {"entity_id": "weather.fixture_panel", "state": "partlycloudy", "attributes": {"temperature": 14, "temperature_unit": "°C"}}
        async with session.post(BASE + "/api/states/" + weather["entity_id"], headers=headers, json=weather) as response:
            assert response.status in (200, 201)
        items += classify({"devices": [], "unattached_entities": [{**weather, "name": "Fixture weather", "observed": True}]}, [weather], {})
        safety = {
            "entity_id": "binary_sensor.fixture_panel_smoke",
            "state": "off",
            "attributes": {"device_class": "smoke", "friendly_name": "Fixture smoke alarm"},
        }
        async with session.post(BASE + "/api/states/" + safety["entity_id"], headers=headers, json=safety) as response:
            assert response.status in (200, 201)
        items += classify({"devices": [], "unattached_entities": [{**safety, "name": "Fixture smoke alarm", "observed": True}]}, [safety], {})
        areas = [{"area_id": "fixture_kitchen", "name": "Fixture kitchen"}]
        before = copy.deepcopy(house)
        records_path = ROOT / "publications.json"
        records = json.loads(records_path.read_text()) if records_path.exists() else {}
        generated = generate(house, surface, items, areas, policy=panel_policy)
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
            document_requests = []
            page.on(
                "request",
                lambda request: document_requests.append(request.url) if request.is_navigation_request() and request.frame == page.main_frame else None,
            )
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

            async def copy_fits():
                clipped = await page.locator(".hs-tile-copy").evaluate_all(
                    "els=>els.filter(e=>e.getBoundingClientRect().bottom>e.closest('.hs-tile').getBoundingClientRect().bottom-4).map(e=>e.closest('.hs-tile').className)"
                )
                assert not clipped, f"Tile detail text must remain inside its panel: {clipped}"

            for name, width, height in [("landscape", 1280, 800), ("panel-landscape", 1280, 720), ("compact-landscape", 1024, 600), ("narrow", 390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.evaluate("()=>document.fonts.ready")
                await page.evaluate("()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                await page.screenshot(path=str(SHOTS / (name + ".png")), full_page=True)
                header = await page.locator(".hs-header").bounding_box()
                await expect(page.locator(".hs-weather")).to_contain_text("14°")
                assert header and header["height"] < 70, "Weather icon must not expand the header"
                await copy_fits()
                assert await page.locator(".hs-nav a span").evaluate_all(
                    "els=>els.every(e=>e.getBoundingClientRect().height<=parseFloat(getComputedStyle(e).fontSize)*1.5)"
                ), "Footer labels must not split midword"
                assert await page.locator(".hs-panel").evaluate("el=>el.scrollWidth<=el.clientWidth+1")
                if width > 720:
                    bounds = await page.locator(".hs-nav").evaluate("el=>({bottom:el.getBoundingClientRect().bottom,height:innerHeight})")
                    if bounds["bottom"] > height + 1:
                        layout_issues.append((name, bounds))
            await page.set_viewport_size({"width": 1280, "height": 800})
            if KIOSK:
                menu = page.get_by_role("button", name="Sidebar toggle", exact=True)
                await expect(menu).not_to_be_visible()
                bounds = await page.locator(".hs-panel").bounding_box()
                assert bounds and bounds["y"] < 2 and bounds["height"] == 800
                await page.screenshot(path=str(SHOTS / "kiosk.png"))
                requests_before = len(document_requests)
                await page.get_by_role("link", name="Settings", exact=True).click()
                await expect(menu).to_be_visible()
                await expect(page.get_by_role("button", name="Panel mode", exact=True)).to_be_visible()
                assert len(document_requests) == requests_before, "Settings must stay inside the companion app"
                await page.wait_for_load_state("networkidle")
                await page.screenshot(path=str(SHOTS / "kiosk-settings.png"))
                await page.get_by_role("button", name="Panel mode", exact=True).click()
                await expect(menu).not_to_be_visible()
                assert len(document_requests) == requests_before, "Panel mode must use native HA navigation"
                await page.reload()
                await expect(page.get_by_role("main", name=surface["name"])).to_be_visible()
                await expect(menu).not_to_be_visible()
                owner_context = await browser.new_context(viewport={"width": 1280, "height": 800})
                owner_page = await owner_context.new_page()
                await owner_page.goto(BASE + "/" + result["url_path"] + "/home")
                await owner_page.get_by_label("Username", exact=True).fill(owner["username"])
                await owner_page.get_by_label("Password", exact=True).fill(owner["password"])
                await owner_page.get_by_role("button", name="Log in", exact=True).click()
                await expect(owner_page.get_by_role("main", name=surface["name"])).to_be_visible(timeout=30000)
                await expect(owner_page.get_by_role("button", name="Sidebar toggle", exact=True)).to_be_visible()
                await owner_context.close()
            requests_before = len(document_requests)
            await page.get_by_role("link", name="Open climate controls", exact=True).click()
            await expect(page.locator("hui-thermostat-card")).to_be_visible()
            assert len(document_requests) == requests_before, "Climate tap must not load an external browser document"
            if KIOSK:
                await expect(page.get_by_role("link", name="Back", exact=True)).to_be_visible()
            thermostat = page.locator("hui-thermostat-card").first
            for name, width, height in [
                ("landscape", 1280, 800),
                ("panel-landscape", 1280, 720),
                ("compact-landscape", 1024, 600),
                ("narrow", 390, 844),
                ("tall-tablet", 800, 1280),
            ]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.reload()  # Reset native view sizing after full-page narrow captures.
                await expect(thermostat).to_be_visible()
                await page.wait_for_load_state("networkidle")
                await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible()
                await page.evaluate("()=>document.fonts.ready")
                await page.evaluate("()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))")
                canvas = await page.locator("button-card").first.evaluate("e=>e.shadowRoot.querySelector('#card').getBoundingClientRect().bottom")
                assert canvas >= height - 1, f"The navy canvas must fill the viewport: {name}, bottom {canvas}, expected {height}"
                await page.screenshot(path=str(SHOTS / ("climate-" + name + ".png")), full_page=name != "tall-tablet")
                assert await page.locator("hui-error-card").count() == 0
                await expect(page.locator("hui-tile-card")).to_have_count(6)
                await expect(page.locator(".hs-room-airflow")).to_have_count(6)
                await expect(page.locator(".hs-room-airflow").first).to_contain_text("60%")
                assert await page.locator("hui-target-temperature-card-feature").evaluate_all("els=>els.every(e=>e.getBoundingClientRect().width>=130)"), (
                    "Native +/- and target value need separate usable space"
                )
                if width >= 1280 and height >= 720:
                    assert await page.locator(".hs-room-airflow").evaluate_all("els=>els.every(e=>e.getBoundingClientRect().bottom<=innerHeight)"), (
                        "Every room's airflow must be visible without scrolling at AirTouch size"
                    )
                bounds = await page.locator("hui-tile-card").evaluate_all(
                    "els=>els.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}})"
                )
                assert all(
                    a["right"] <= b["x"] + 1 or b["right"] <= a["x"] + 1 or a["bottom"] <= b["y"] + 1 or b["bottom"] <= a["y"] + 1
                    for i, a in enumerate(bounds)
                    for b in bounds[i + 1 :]
                ), "Native zone cards must never overlap"
                assert await page.locator("hui-panel-view").evaluate("el=>el.scrollWidth<=el.clientWidth+1")
                assert await thermostat.evaluate("el=>getComputedStyle(el).getPropertyValue('--primary-text-color').trim()") == "#f7f8fa"
                assert (await thermostat.bounding_box())["y"] < 130, "Tall screens must not vertically center the whole control page"
                if name == "tall-tablet":
                    await page.locator(".hs-room-airflow").last.scroll_into_view_if_needed()
                    await page.screenshot(path=str(SHOTS / "climate-tall-tablet-rooms.png"))
                    await thermostat.scroll_into_view_if_needed()
            linked_room = page.locator("button-card").filter(has=page.get_by_text("Kitchen / dining / living", exact=True)).last
            missing_temperature_room = page.locator("button-card").filter(has=page.get_by_text("Lounge", exact=True)).last
            assert await missing_temperature_room.locator(".hs-room-now").count() == 0
            # A linked readout must follow native HA updates without regenerating/reloading.
            for state, position, expected in [("closed", 0, "0%"), ("unavailable", 60, "Unavailable"), ("open", 60, "60%")]:
                async with session.post(
                    BASE + "/api/states/cover.fixture_panel_zone_0",
                    headers=headers,
                    json={"state": state, "attributes": {"device_class": "damper", "current_position": position, "supported_features": 0}},
                ) as response:
                    assert response.status == 200
                await expect(linked_room.locator(".hs-room-airflow")).to_have_attribute(
                    "aria-label", "Damper " + ("unavailable" if expected == "Unavailable" else expected + " open")
                )
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
            await page.set_viewport_size({"width": 1280, "height": 800})
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
            await show_scene(generate(house, surface, offline_items, areas, policy=panel_policy))
            await expect(page.get_by_text("Connection unavailable", exact=True)).to_be_visible()
            await page.set_viewport_size({"width": 1280, "height": 720})
            await copy_fits()
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
            await show_scene(generate(house, surface, idle_items, areas, policy=panel_policy))
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
                await show_scene(generate(house, surface, items, areas, policy={**panel_policy, "bin_context_screens": [surface["id"]]}))
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
