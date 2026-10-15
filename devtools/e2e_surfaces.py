"""Desktop/mobile screen setup and native Core rendering/control acceptance."""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

from fixture_urls import fixture_url
from playwright.sync_api import expect, sync_playwright


def state(base, entity, headers):
    with urlopen(Request(base + "/api/states/" + entity, headers=headers), timeout=10) as response:  # noqa: S310 - hardcoded loopback fixture
        return json.load(response)["state"]


def main():
    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    base = "http://127.0.0.1:18123"
    headers = {"Authorization": "Bearer " + credentials["token"]}
    shots = Path("screens/v3-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1280, "height": 900}, color_scheme="light")
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(fixture_url("/home_starter"))
        frame = page.frame_locator("#panel")
        expect(frame.locator("#surfaces-status")).to_contain_text("Saved household loaded")
        frame.get_by_role("link", name="Screens", exact=True).click()
        frame.get_by_label("Person name", exact=True).fill("Alex")
        frame.get_by_label("Person audience", exact=True).select_option("adult")
        frame.get_by_role("button", name="Add screen profile", exact=True).click()
        person = frame.get_by_label("Screen person", exact=True).locator("option").filter(has_text="Alex").get_attribute("value")
        surface_ids = {}
        for profile, label in (("phone", "Alex phone"), ("tablet", "House tablet"), ("specialist", "Kitchen AC panel"), ("wall", "Wall display")):
            # Each Add screen rerenders and collapses the section after the first.
            detail = frame.locator("details").filter(has=frame.get_by_text("Add a screen", exact=True))
            if not detail.get_attribute("open") == "":
                detail.locator("summary").click()
            frame.get_by_label("Screen name", exact=True).fill(label)
            frame.get_by_label("Screen type", exact=True).select_option(profile)
            frame.get_by_label("Screen person", exact=True).select_option(person if profile == "phone" else "")
            frame.get_by_label("Screen room", exact=True).select_option("kitchen" if profile == "specialist" else "")
            frame.get_by_label("Screen audience", exact=True).select_option("adult" if profile != "wall" else "everyone")
            frame.get_by_role("button", name="Add screen", exact=True).click()
            surface_ids[profile] = frame.get_by_label("Selected screen", exact=True).input_value()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        frame.get_by_label("Selected screen", exact=True).select_option(surface_ids["phone"])
        frame.get_by_text("Pin, hide and reorder", exact=True).click()
        frame.get_by_role("checkbox", name="Pin Kitchen light", exact=True).check()
        expect(frame.get_by_role("button", name="Save household settings", exact=True)).to_be_enabled()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        # Explicit completion source is configured once, with no chores or inference.
        frame.get_by_text("Appliance activity today", exact=True).click()
        frame.get_by_label("Activity name", exact=True).fill("Washer")
        frame.get_by_label("Appliance status", exact=True).select_option("sensor.washer_status")
        frame.get_by_label("Running state", exact=True).fill("running")
        frame.get_by_label("Completed state", exact=True).fill("complete")
        frame.get_by_role("button", name="Add activity tracking", exact=True).click()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        paths = {}
        for profile in surface_ids:
            frame.get_by_label("Selected screen", exact=True).select_option(surface_ids[profile])
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            expect(frame.locator("#screen-preview")).to_be_visible()
            frame.locator("#screen-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"setup-{profile}-desktop.png"))
            frame.get_by_text("Review publication", exact=True).click()
            frame.get_by_role("button", name="Confirm add dashboard", exact=True).click()
            expect(frame.locator("#surfaces-status")).to_contain_text("read back successfully", timeout=30000)
            paths[profile] = "home-starter-" + surface_ids[profile]
        Path("screens/v3-paths.json").write_text(json.dumps(paths))
        page.reload()
        expect(frame.get_by_label("Selected screen", exact=True)).to_have_value(surface_ids["phone"])
        # Selection is not a preference; first saved screen is restored on page load.
        context.close()
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        page.goto(base)
        page.get_by_label("Username", exact=True).fill(credentials["username"])
        page.get_by_label("Password", exact=True).fill(credentials["password"])
        page.get_by_role("button", name="Log in", exact=True).click()
        expect(page.get_by_role("button", name="Log in", exact=True)).not_to_be_visible(timeout=30000)
        expect(page.get_by_role("button", name="Sidebar toggle", exact=True)).to_be_visible(timeout=30000)
        for profile in paths:
            page.locator(f'a[href="/{paths[profile]}"]').click()
            expect(page.locator("hui-sections-view")).to_be_visible(timeout=30000)
            expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
            assert page.locator("hui-error-card").count() == 0
            page.screenshot(path=str(shots / f"native-{profile}-desktop.png"))
            if profile == "phone":
                original = state(base, "light.kitchen_light", headers)
                tile = page.locator("hui-tile-card").filter(has_text="Kitchen light").first
                tile.locator("ha-tile-icon").click()
                expect(tile).to_contain_text("On" if original == "off" else "Off")
                actual = state(base, "light.kitchen_light", headers)
                assert actual != original
                tile.locator("ha-tile-icon").click()
                expect(tile).to_contain_text("Off" if original == "off" else "On")
            if profile == "specialist":
                expect(page.locator("hui-thermostat-card")).to_be_visible()
                page.locator("hui-thermostat-card").get_by_role("button").nth(1).click()
                expect(page.locator("hui-thermostat-card")).to_contain_text("22.1")
                page.locator("hui-thermostat-card").get_by_role("button").nth(0).click()
                # HA renders the integer and decimal fraction in separate spans.
                expect(page.locator("hui-thermostat-card")).to_contain_text(re.compile(r"22\s*\.0"))
        page.locator(f'a[href="/{paths["phone"]}"]').click()
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.locator("hui-sections-view")).to_be_visible()
        expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
        page.screenshot(path=str(shots / "native-phone-mobile.png"))
        assert not errors, errors
        browser.close()
    Path("screens/v3-paths.json").write_text(json.dumps(paths))
    print("Four native dashboards rendered; phone light toggle + restore verified; desktop/mobile captures saved.")


if __name__ == "__main__":
    main()
