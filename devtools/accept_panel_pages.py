"""AirTouch page-system acceptance on disposable loopback HA only.

Fictional adapter projections prove UI contracts, not calls/camera/audio services.
Only the fixture's actual kitchen light and thermostat are operated and restored.
"""

import asyncio
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp
from accept_screen_identity_native import BASE, login
from playwright.async_api import async_playwright, expect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
from homestarter.context import entity_id
from homestarter.core import CoreClient
from homestarter.household import empty_household
from homestarter.inventory import collect_inventory
from homestarter.settings import Secret
from homestarter.surfaces import classify, generate, publish

ROOT = Path(".runtime/panel-pages-native")
SHOTS = Path("screens/panel-nav-ui")


async def main():
    assert BASE == "http://127.0.0.1:18123"
    ROOT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    (ROOT / "result.json").write_text(json.dumps({"passed": False, "status": "running"}), encoding="utf-8")
    owner = json.loads(Path("screens/v3-core-credentials.json").read_text())
    display = json.loads(Path(".runtime/screen-probe-credentials.json").read_text())
    async with aiohttp.ClientSession() as session:
        token = await login(session, owner)
        headers = {"Authorization": "Bearer " + token}
        core = CoreClient(session, BASE + "/api", BASE.replace("http", "ws") + "/api/websocket", Secret(token))
        async with core.websocket() as ws:
            users = await ws.command("config/auth/list")
            user = next(u for u in users if u["id"] == display["user_id"])
            assert not user.get("is_owner") and "system-users" in user["group_ids"]
            resources = await ws.command("lovelace/resources/list")
            assert any("button-card" in r["url"] for r in resources)
            assert any("kiosk-mode" in r["url"] for r in resources)
        inv = await collect_inventory(core)
        states = await core.states()
        items = classify(inv, states, {})
        items = [i for i in items if i["entity_id"] in ["climate.kitchen_air_conditioning", "light.kitchen_light"]]
        for i in items:
            i["area_id"] = "fixture_kitchen"
        main_unit = next(i for i in items if i["entity_id"] == "climate.kitchen_air_conditioning")
        main_unit["platform"] = "airtouch5"
        main_unit["attributes"]["fan_modes"] = ["auto"]
        original_target = next(s["attributes"]["temperature"] for s in states if s["entity_id"] == main_unit["entity_id"])
        # Full six-zone layout; these synthetic zone states have no real services.
        for index, name in enumerate(["Kitchen / dining / living", "Lounge", "Main bedroom", "Bedroom two", "Bedroom three", "Bedroom four"]):
            for domain in ("climate", "cover"):
                id = f"{domain}.fixture_panel_zone_{index}"
                attrs = (
                    {
                        "friendly_name": name,
                        "temperature": 25,
                        "current_temperature": 21.5,
                        "hvac_modes": ["off", "fan_only"],
                        "supported_features": 385,
                        "min_temp": 16,
                        "max_temp": 35,
                    }
                    if domain == "climate"
                    else {"friendly_name": name + " airflow", "device_class": "damper", "current_position": 60, "supported_features": 0}
                )
                value = "fan_only" if domain == "climate" else "open"
                async with session.post(BASE + "/api/states/" + id, headers=headers, json={"state": value, "attributes": attrs}) as response:
                    assert response.status in (200, 201)
                items += classify(
                    {
                        "devices": [],
                        "unattached_entities": [
                            {
                                "entity_id": id,
                                "name": attrs["friendly_name"],
                                "platform": "airtouch5",
                                "device_id": f"fixture_zone_{index}",
                                "observed": True,
                                "state": value,
                                "area_id": "fixture_kitchen" if index == 0 else f"fixture_zone_{index}",
                            }
                        ],
                    },
                    [{"entity_id": id, "state": value, "attributes": attrs}],
                    {},
                )
        house = empty_household()
        house["people"] = [{"id": "alex", "name": "Alex", "audience": "adult"}, {"id": "sam", "name": "Sam", "audience": "everyone"}]
        house["people"] += [{"id": f"fixture_member_{n}", "name": f"Fixture member {n}", "audience": "everyone"} for n in range(6)]
        surface = {
            "id": "panel_pages_acceptance",
            "name": "Fixture AirTouch pages",
            "profile": "specialist",
            "area_id": "fixture_kitchen",
            "person_id": None,
            "audience": "adult",
            "kiosk": True,
        }
        house["surfaces"] = [surface]
        areas = [{"area_id": "fixture_kitchen", "name": "Kitchen"}, {"area_id": "fixture_bedroom", "name": "Bedroom"}]
        areas += [
            {"area_id": f"fixture_zone_{index}", "name": name}
            for index, name in enumerate(["Kitchen", "Lounge", "Main bedroom", "Bedroom two", "Bedroom three", "Bedroom four"])
            if index
        ]

        async def state(entity, state_value, attributes):
            async with session.post(BASE + "/api/states/" + entity, headers=headers, json={"state": state_value, "attributes": attributes}) as response:
                assert response.status in (200, 201)

        fictional = [
            (
                "media_player.fixture_house",
                "Kitchen speaker",
                "fixture_kitchen",
                "playing",
                {"supported_features": 16437, "media_title": "Fixture recording", "media_artist": "Fixture artist", "volume_level": 0.25},
            ),
            (
                "media_player.fixture_child",
                "Bedroom speaker",
                "fixture_bedroom",
                "paused",
                {"supported_features": 16437, "media_title": "Fixture story", "volume_level": 0.15},
            ),
            ("weather.fixture_pages", "Weather", None, "partlycloudy", {"temperature": 14, "temperature_unit": "°C"}),
        ]
        for id, name, area, value, attrs in fictional:
            await state(id, value, attrs)
            items += classify(
                {"devices": [], "unattached_entities": [{"entity_id": id, "name": name, "area_id": area, "device_id": id, "observed": True, "state": value}]},
                [{"entity_id": id, "state": value, "attributes": attrs}],
                {},
            )
        policy = {
            "landscape_panel": True,
            "kiosk_user_name": user["name"],
            "members": {
                "sam": {"kind": "child", "rooms": ["fixture_bedroom"], "devices": ["media_player.fixture_house"]},
                "alex": {"kind": "adult", "rooms": ["fixture_kitchen"], "devices": []},
            },
        }
        scene = generate(house, surface, items, areas, policy=policy)
        records_path = ROOT / "publications.json"
        records = json.loads(records_path.read_text()) if records_path.exists() else {}
        result = await publish(core, scene, records.get(scene["url_path"], {}).get("fingerprint"), records)
        records[result["url_path"]] = result
        records_path.write_text(json.dumps(records))
        (ROOT / "generated.json").write_text(json.dumps(scene))
        errors = []
        routes = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()
            page.on("pageerror", lambda e: errors.append(e.stack))

            async def capture(**kwargs):
                if "--no-capture" not in sys.argv:
                    await page.screenshot(**kwargs)

            await page.goto(BASE + "/" + scene["url_path"] + "/home")
            await page.get_by_label("Username", exact=True).fill(display["username"])
            await page.get_by_label("Password", exact=True).fill(display["password"])
            await page.get_by_role("button", name="Log in", exact=True).click()
            await expect(page.get_by_role("main", name=surface["name"])).to_be_visible(timeout=30000)

            async def nav_visible():
                await expect(page.get_by_role("navigation", name="Household", exact=True)).to_be_visible()
                assert await page.locator(".hs-nav").evaluate("e=>{const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight+1}"), (
                    "Household menu must stay inside the viewport"
                )
                assert await page.locator(".hs-household a").count() == len(house["people"]) + 1
                assert await page.locator(".hs-nav").evaluate(
                    """e=>{const r=e.getBoundingClientRect();return [...e.querySelectorAll('a')].every(a=>{
                      const b=a.getBoundingClientRect();return b.left>=r.left&&b.right<=r.right+1&&b.top>=r.top&&b.bottom<=r.bottom+1;
                    })}"""
                ), "Every household/display target must fit within the visible menu"

            for label, width, height in [("landscape", 1280, 720), ("tablet", 800, 1280), ("narrow", 390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.reload()
                await page.wait_for_load_state("networkidle")
                await nav_visible()
                menu_before = await page.locator(".hs-nav").bounding_box()
                await page.locator(".hs-board").evaluate("e=>e.scrollTop=e.scrollHeight")
                await nav_visible()
                assert abs((await page.locator(".hs-nav").bounding_box())["y"] - menu_before["y"]) < 1
                await capture(path=str(SHOTS / ("home-" + label + ".png")))
            await page.set_viewport_size({"width": 1280, "height": 720})

            async def load(path):
                await page.goto(BASE + "/" + scene["url_path"] + "/" + path)
                await page.wait_for_load_state("networkidle")
                await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible()
                await page.evaluate("document.fonts.ready")
                await expect(
                    page.get_by_role("heading", name=next(v["title"] for v in scene["config"]["views"] if v["path"] == path), exact=True).first
                ).to_be_visible()
                assert await page.locator("hui-error-card").count() == 0
                await page.locator("hui-panel-view button-card").first.evaluate(
                    """async el=>{
                      let old='',since=performance.now();const start=since;
                      while(performance.now()-start<5000){
                        const r=el.shadowRoot.querySelector('#card').getBoundingClientRect();
                        const size=[r.width,r.height,document.documentElement.scrollHeight].join();
                        if(size!==old){old=size;since=performance.now();}
                        if(performance.now()-since>750)return;
                        await new Promise(resolve=>setTimeout(resolve,100));
                      }
                      throw Error('Layout failed to settle');
                    }"""
                )

            selected = [
                "today",
                "call",
                "cameras",
                "music",
                "rooms",
                "climate",
                "person-616c6578",
                "person-73616d",
                "person-73616d-today",
                "person-73616d-music",
                "settings",
                "ambient",
            ]
            selected += [next(v["path"] for v in scene["config"]["views"] if v["path"].startswith("room-"))]
            for path in selected:
                for name, width, height in [("landscape", 1280, 720), ("tablet", 800, 1280), ("narrow", 390, 844)]:
                    await page.set_viewport_size({"width": width, "height": height})
                    await load(path)
                    await capture(path=str(SHOTS / (path + "-" + name + ".png")), full_page=True)
                    assert await page.locator("hui-panel-view").evaluate("e=>e.scrollWidth<=e.clientWidth+1"), path + " overflow"
                    assert await page.locator(".hs-back").count() == 1
                    await nav_visible()
                    menu_before = await page.locator(".hs-nav").bounding_box()
                    await page.locator("button-card").first.evaluate("e=>{const b=e.shadowRoot.querySelector('#body');b.scrollTop=b.scrollHeight;}")
                    await nav_visible()
                    assert abs((await page.locator(".hs-nav").bounding_box())["y"] - menu_before["y"]) < 1
                    if path == "climate":
                        await capture(path=str(SHOTS / ("climate-scrolled-" + name + ".png")))
                    await page.locator("button-card").first.evaluate("e=>e.shadowRoot.querySelector('#body').scrollTop=0")
                    assert await page.locator(".hs-page-content button ha-icon,.hs-room-link ha-icon").evaluate_all(
                        "es=>es.every(e=>getComputedStyle(e).marginLeft==='0px'&&getComputedStyle(e).marginRight==='0px')"
                    ), path + " icon spacing"
                    assert await page.locator(".hs-page-content button ha-icon,.hs-room-link ha-icon,.hs-control-head ha-icon").evaluate_all(
                        "es=>es.every(e=>{const r=e.getBoundingClientRect();return r.width<=40&&r.height<=40})"
                    ), path + " icon bounds"
                    if path == "person-73616d" and width == 1280:
                        assert (await page.get_by_role("link", name="Your Today", exact=True).bounding_box())["y"] < height - 56
                        assert (await page.locator(".hs-household").bounding_box())["y"] < height - 56
                    assert await page.locator(".hs-page-content button,.hs-page-content a,.hs-back,.hs-household a").evaluate_all(
                        "es=>es.every(e=>{const r=e.getBoundingClientRect();return r.width>=48&&r.height>=48})"
                    ), path + " touch targets"
                await load(path)
                await page.locator(".hs-back").click()
                await expect(page).to_have_url(BASE + next(v["back_path"] for v in scene["config"]["views"] if v["path"] == path))
                routes.append(path)
            await page.set_viewport_size({"width": 1280, "height": 720})
            await page.goto(BASE + "/" + scene["url_path"] + "/dark")
            await expect(page.get_by_role("link", name="Wake", exact=True)).to_be_visible()
            await page.wait_for_load_state("networkidle")
            await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible()
            await page.evaluate("document.fonts.ready")
            for label, width, height in [("landscape", 1280, 720), ("tablet", 800, 1280), ("narrow", 390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.reload()
                await page.wait_for_load_state("networkidle")
                await nav_visible()
                await capture(path=str(SHOTS / ("dark-" + label + ".png")))
            await page.get_by_role("link", name="Wake", exact=True).click()
            await expect(page.get_by_role("main", name=surface["name"])).to_be_visible()
            # Context projections are fixture-only representations of the engine contract.
            for who, title in [(None, "Fixture household departure"), ("sam", "Fixture personal requirement")]:
                await state(
                    entity_id(surface["id"], who),
                    "current",
                    {
                        "home_starter_context": {"surface": surface["id"], "epoch": 0, **({"person_id": who} if who else {})},
                        "checked_at": datetime.now(UTC).isoformat(),
                        "valid_until": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
                        "briefing": [
                            {"id": "fixture", "title": title, "when": "Next", "detail": "Leave by 08:30"},
                            {"id": "fixture-later", "title": "Fixture later activity", "when": "Tomorrow", "detail": "Bring kit"},
                        ],
                    },
                )
            for path in ["today", "person-73616d", "person-73616d-today"]:
                await load(path)
                await capture(path=str(SHOTS / ("populated-" + path + ".png")), full_page=True)
            # Native thermostat remains operable inside the shared shell, with six zones.
            await page.set_viewport_size({"width": 1280, "height": 720})
            await load("climate")
            assert await page.locator("hui-thermostat-card").count() == 1
            assert await page.locator("hui-tile-card").count() == 6
            assert await page.locator(".hs-room-airflow").count() == 6
            thermostat = page.locator("hui-thermostat-card")
            try:
                await thermostat.get_by_role("button").nth(1).click()
                for _ in range(30):
                    target = next(s["attributes"]["temperature"] for s in await core.states() if s["entity_id"] == main_unit["entity_id"])
                    if target > original_target:
                        break
                    await asyncio.sleep(0.2)
                assert target > original_target
            finally:
                async with session.post(
                    BASE + "/api/services/climate/set_temperature", headers=headers, json={"entity_id": main_unit["entity_id"], "temperature": original_target}
                ) as response:
                    assert response.status == 200
            # Explicit Settings escape works without removing native account access.
            await load("settings")
            await page.get_by_role("link", name="Exit panel", exact=True).click()
            # HA 2026.10 redirects the legacy Overview route to /home/overview.
            await expect(page).to_have_url(re.compile(re.escape(BASE) + r"/(?:lovelace/0(?:\?disable_km)?|home/overview)$"))
            await expect(page.get_by_role("button", name="Search Home Assistant (Ctrl + K)", exact=True)).to_be_visible()
            # Operate only a real disposable fixture light, then restore its state.
            room = next(v for v in scene["config"]["views"] if v["path"].startswith("room-") and v["title"] == "Kitchen")
            original = next(s["state"] for s in await core.states() if s["entity_id"] == "light.kitchen_light")
            try:
                await load(room["path"])
                button = page.locator('[data-entity="light.kitchen_light"][data-command="toggle"]')
                await button.click()
                for _ in range(30):
                    value = next(s["state"] for s in await core.states() if s["entity_id"] == "light.kitchen_light")
                    if value != original:
                        break
                    await asyncio.sleep(0.2)
                assert value != original
            finally:
                async with session.post(
                    BASE + "/api/services/light/" + ("turn_on" if original == "on" else "turn_off"), headers=headers, json={"entity_id": "light.kitchen_light"}
                ) as response:
                    assert response.status == 200
            assert not errors, errors
            (ROOT / "result.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "routes": routes,
                        "viewports": 3,
                        "browser_errors": errors,
                        "fixture_light_restored": True,
                        "native_thermostat_restored": True,
                        "six_zone_layout": True,
                        "settings_escape": True,
                        "persistent_household_menu": True,
                        "configured_people": len(house["people"]),
                    },
                    indent=2,
                )
            )
            await browser.close()
            print("Native AirTouch page-system shell, scoped routes, controls, context, kiosk and reload: PASS")


if __name__ == "__main__":
    asyncio.run(main())
