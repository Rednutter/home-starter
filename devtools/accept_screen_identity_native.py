"""Actual disposable HA users → native session proof → browser restart → physical report.

Loopback fixture only. Browser storage and fictional credentials remain ignored/private.
This proves the mechanism, not an actual AirTouch or physical-device reboot.
"""

import asyncio
import json
import re
import secrets
import sys
from pathlib import Path

import aiohttp
from aiohttp.test_utils import TestClient, TestServer
from playwright.async_api import async_playwright, expect

BASE = "http://127.0.0.1:18123"
ROOT = Path(".runtime/screen-native-acceptance")
SHOTS = Path("screens/screen-identity-ui")


async def login(session, credentials):
    async with session.post(
        BASE + "/auth/login_flow", json={"client_id": BASE + "/", "handler": ["homeassistant", None], "redirect_uri": BASE + "/?auth_callback=1"}
    ) as r:
        flow = await r.json()
    async with session.post(
        BASE + "/auth/login_flow/" + flow["flow_id"], json={"client_id": BASE + "/", "username": credentials["username"], "password": credentials["password"]}
    ) as r:
        flow = await r.json()
    assert flow["type"] == "create_entry", "Disposable fixture login failed"
    async with session.post(BASE + "/auth/token", data={"grant_type": "authorization_code", "code": flow["result"], "client_id": BASE + "/"}) as r:
        return (await r.json())["access_token"]


async def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter.core import CoreClient
    from homestarter.household import HouseholdStore
    from homestarter.server import create_app, screen_status
    from homestarter.settings import Secret, Settings
    from homestarter.surfaces import fingerprint, publish
    from homestarter.this_house import digest
    from homestarter.this_house import load as house_confirmations
    from ingress_proxy import build_app
    from mock_supervisor import TOKEN, MockSupervisor

    ROOT.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    owner = json.loads(Path("screens/v3-core-credentials.json").read_text())
    async with aiohttp.ClientSession() as session:
        token = await login(session, owner)
        core = CoreClient(session, BASE + "/api", BASE.replace("http", "ws") + "/api/websocket", Secret(token))
        async with core.websocket() as ws:
            actor = (await ws.command("auth/current_user"))["id"]
            credentials_path = Path(".runtime/screen-probe-credentials.json")
            if credentials_path.exists():
                display = json.loads(credentials_path.read_text())
            else:
                user = (await ws.command("config/auth/create", name="Fixture display probe", group_ids=["system-users"], local_only=False))["user"]
                display = {"user_id": user["id"], "username": "fixture_display_probe", "password": secrets.token_urlsafe(24)}
                await ws.command("config/auth_provider/homeassistant/create", user_id=user["id"], username=display["username"], password=display["password"])
                credentials_path.write_text(json.dumps(display))
            user = next(u for u in await ws.command("config/auth/list") if u["id"] == display["user_id"])
            assert user["name"] == "Fixture display probe" and not user["is_owner"] and user["group_ids"] == ["system-users"]
            await ws.command("config/auth/update", user_id=user["id"], local_only=False)
            native_people = await ws.command("person/list")
            display_person = next((p for p in native_people["storage"] if p.get("user_id") == user["id"]), None)
            if not display_person:
                display_person = await ws.command("person/create", name="Fixture display record", user_id=user["id"], device_trackers=[])
            # A tracked display-only Person is not a household member. Preserve its
            # native link and tracker, matching an existing display-account case.
            async with session.post(
                BASE + "/api/states/device_tracker.fixture_display",
                headers={"Authorization": "Bearer " + token},
                json={"state": "home", "attributes": {"friendly_name": "Fixture display tracker"}},
            ) as response:
                assert response.status in (200, 201)
            display_person = await ws.command("person/update", person_id=display_person["id"], device_trackers=["device_tracker.fixture_display"])
        mock = MockSupervisor("ready", core_url=BASE, core_token=token, ma_host="127.0.0.1")
        async with TestServer(mock.app()) as supervisor, TestServer(mock.ma_app()) as ma:
            mock.ma_port = ma.port
            settings = Settings.from_env(
                {
                    "SUPERVISOR_TOKEN": TOKEN,
                    "HOME_STARTER_SUPERVISOR_URL": str(supervisor.make_url("")),
                    "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
                    "HOME_STARTER_MA_PORT": str(ma.port),
                    "HOME_STARTER_DATA_DIR": str(ROOT.resolve()),
                }
            )
            store = HouseholdStore(settings.data_dir)
            house = store.load()
            reviewed = house_confirmations(store)
            reviewed["people"][display_person["id"]] = {
                "role": "other",
                "signature": digest([display_person["id"], display_person["name"], sorted(display_person["device_trackers"])]),
            }
            store.write(store.this_house_path, reviewed)
            surface = {
                "id": "display_acceptance",
                "name": "Fixture control panel",
                "profile": "specialist",
                "person_id": None,
                "area_id": None,
                "audience": "everyone",
            }
            if not house["surfaces"]:
                house["surfaces"] = [surface]
                house = store.save(house)
            path = "home-starter-display-acceptance"
            config = {"views": [{"title": "Fixture panel", "path": "home", "cards": [{"type": "thermostat", "entity": "climate.kitchen_air_conditioning"}]}]}
            records = store.read(store.publication_path, {})
            generated = {"url_path": path, "config": config, "fingerprint": fingerprint(config), "surface": surface}
            records[path] = await publish(core, generated, records.get(path, {}).get("fingerprint"), records)
            store.write(store.publication_path, records)
            before = {p.name: p.read_bytes() for p in ROOT.iterdir() if p.is_file() and p.name not in {"screen-commissioning.json"}}
            async with TestClient(TestServer(create_app(settings))) as client, TestServer(build_app(str(client.server.make_url("")), user_id=actor)) as ingress:
                headers = {"X-Remote-User-Id": actor}

                async def view():
                    response = await client.get("/api/screens/identity", headers=headers)
                    assert response.status == 200
                    return await response.json()

                async def act(action, **extra):
                    current = await view()
                    response = await client.post(
                        "/api/screens/identity",
                        headers=headers,
                        json={"revision": current["revision"], "epoch": current["epoch"], "surface": surface["id"], "action": action, "confirm": True, **extra},
                    )
                    result = await response.json()
                    assert response.status == 200, result.get("error")
                    return result["screens"][0]

                async with async_playwright() as pw:
                    browser = await pw.chromium.launch()
                    admin = await browser.new_page(viewport={"width": 1280, "height": 900})
                    await admin.goto(str(ingress.make_url("/home_starter")))
                    frame = admin.frame_locator("#panel")
                    section = frame.locator("#screen-identity")
                    await section.locator(":scope > summary").click()
                    await expect(frame.locator("#screen-identity-status")).to_contain_text("Display checks read", timeout=30000)
                    await section.get_by_text("Dedicated account and permissions", exact=True).click()
                    await section.get_by_label("Dedicated display account", exact=True).select_option(display["user_id"])
                    prepare = section.get_by_role("button", name="Confirm enable local-only access and use selected display account", exact=True)
                    for label, size in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 390, "height": 844})):
                        await admin.set_viewport_size(size)
                        await prepare.scroll_into_view_if_needed()
                        await admin.screenshot(path=str(SHOTS / f"{label}-account-preparation.png"))
                    await prepare.click()
                    await expect(frame.locator("#screen-identity-status")).to_contain_text("state saved and read back")
                    prepared = (await view())["screens"][0]
                    assert prepared["stage"] == "published" and prepared["record"]["prepared"]["change"] == "local_only_enabled"
                    async with core.websocket() as ws:
                        unchanged = next(p for p in (await ws.command("person/list"))["storage"] if p["id"] == display_person["id"])
                    assert unchanged == display_person
                    await admin.close()
                    native_context = await browser.new_context(viewport={"width": 1280, "height": 900})
                    page = await native_context.new_page()
                    await page.goto(BASE + "/" + path + "/home")
                    await page.get_by_label("Username", exact=True).fill(display["username"])
                    await page.get_by_label("Password", exact=True).fill(display["password"])
                    await page.get_by_role("button", name="Log in", exact=True).click()
                    await expect(page.get_by_role("button", name="Sidebar toggle", exact=True)).to_be_visible(timeout=30000)
                    await page.goto(BASE + "/" + path + "/home")
                    thermostat = page.locator("hui-thermostat-card")
                    await expect(thermostat).to_be_visible(timeout=30000)
                    original = (await core.rest_get("/states/climate.kitchen_air_conditioning"))["attributes"]["temperature"]
                    try:
                        await thermostat.get_by_role("button").nth(1).click()
                        for _ in range(50):
                            changed = await core.rest_get("/states/climate.kitchen_air_conditioning")
                            if abs(changed["attributes"]["temperature"] - round(original + 0.1, 1)) < 0.001:
                                break
                            await asyncio.sleep(0.1)
                        assert abs(changed["attributes"]["temperature"] - round(original + 0.1, 1)) < 0.001
                        assert changed["context"]["user_id"] == display["user_id"]
                    finally:
                        await thermostat.get_by_role("button").nth(0).click()
                        for _ in range(50):
                            restored = await core.rest_get("/states/climate.kitchen_air_conditioning")
                            if abs(restored["attributes"]["temperature"] - original) < 0.001:
                                break
                            await asyncio.sleep(0.1)
                    await expect(thermostat).to_contain_text(re.compile(re.escape(f"{original:.1f}").replace(r"\.", r"\s*\.")))
                    assert abs((await core.rest_get("/states/climate.kitchen_air_conditioning"))["attributes"]["temperature"] - original) < 0.001
                    await page.goto(BASE + "/profile/preferences")
                    await expect(page.locator("ha-select")).to_be_visible(timeout=30000)
                    await page.locator("ha-select").click()
                    await page.get_by_role("menuitem", name="Fixture control panel", exact=True).click()
                    await page.reload()
                    await expect(page.locator("ha-select ha-dropdown-item[selected]")).to_have_text(re.compile(r"\s*Fixture control panel\s*"))
                    row = await act("begin", stage="session")
                    check_path = "/" + row["record"]["page"]["url_path"] + "/home"
                    await page.goto(BASE + check_path)
                    await page.get_by_role("button", name="Verify this display session", exact=True).click(timeout=30000)
                    row = await act("observe")
                    assert row["stage"] == "authenticated" and not row["record"]["physical"]
                    await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
                    await expect(page.locator("hui-button-card ha-svg-icon")).to_be_visible(timeout=30000)
                    await page.screenshot(path=str(SHOTS / "native-session.png"))
                    await act("begin", stage="restart")
                    await native_context.storage_state(path=str(ROOT / "browser-state.json"))
                    await browser.close()
                    browser = await pw.chromium.launch()
                    native_context = await browser.new_context(storage_state=str(ROOT / "browser-state.json"), viewport={"width": 1280, "height": 900})
                    page = await native_context.new_page()
                    await page.goto(BASE + "/")
                    await expect(page).to_have_url(re.compile(path + "(?:/home)?$"), timeout=30000)
                    await expect(page.locator("hui-thermostat-card")).to_be_visible(timeout=30000)
                    await expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
                    assert await page.get_by_role("button", name="Log in", exact=True).count() == 0
                    await page.screenshot(path=str(SHOTS / "native-after-browser-restart.png"))
                    await page.goto(BASE + check_path)
                    await page.get_by_role("button", name="Verify this display session", exact=True).click(timeout=30000)
                    await act("observe")
                    row = await act("physical", dashboard_opened=True, default_set=True, controls_worked=True, restart_kind="browser")
                    assert row["stage"] == "commissioned"
                    admin = await browser.new_page()
                    errors = []
                    admin.on("pageerror", lambda error: errors.append(str(error)))
                    for label, size in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 390, "height": 844})):
                        await admin.set_viewport_size(size)
                        await admin.goto(str(ingress.make_url("/home_starter")))
                        frame = admin.frame_locator("#panel")
                        section = frame.locator("#screen-identity")
                        await section.locator(":scope > summary").click()
                        await expect(frame.locator("#screen-identity-status")).to_contain_text("Display checks read", timeout=30000)
                        await expect(section).to_contain_text("State: commissioned")
                        await section.scroll_into_view_if_needed()
                        await admin.screenshot(path=str(SHOTS / f"{label}-commissioned.png"))
                        await section.get_by_text("Dedicated account and permissions", exact=True).click()
                        await section.get_by_role("button", name="Open HA user management", exact=True).scroll_into_view_if_needed()
                        await admin.screenshot(path=str(SHOTS / f"{label}-account.png"))
                        await section.get_by_text("Dedicated account and permissions", exact=True).click()
                        await section.get_by_text("Verify on the physical display", exact=True).click()
                        await section.locator("fieldset").scroll_into_view_if_needed()
                        await admin.screenshot(path=str(SHOTS / f"{label}-physical-checks.png"))
                        assert await frame.locator("body").evaluate("el=>el.scrollWidth<=el.clientWidth+1")
                    assert not errors, errors
                    await browser.close()
                assert all((ROOT / name).read_bytes() == body for name, body in before.items() if name not in {"inventory-history.json", "browser-state.json"})
                assert "password" not in store.screen_identity_path.read_text().lower()
                assert (await screen_status(core, house, records))[0]["status"] == "published"
            # Reopening the application must retain the completed scoped history.
            async with TestClient(TestServer(create_app(settings))) as restarted:
                result = await (await restarted.get("/api/screens/identity", headers=headers)).json()
                assert result["screens"][0]["stage"] == "commissioned"
    print(
        "Native non-admin caller proof, climate control/restoration, default-dashboard reload, browser restart, "
        "two-stage session proof, owner physical report, app restart and desktop/mobile UI: PASS"
    )


if __name__ == "__main__":
    asyncio.run(main())
