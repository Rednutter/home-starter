"""Fixture ingress acceptance for setup, shared navigation and publication/readback.

Run v3_harness.py --fixtures first. This does not assert native HA rendering.
"""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    shots = Path("screens/v4-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto("http://127.0.0.1:8124/home_starter")
        frame = page.frame_locator("#panel")
        expect(frame.locator("#surfaces-status")).to_contain_text("Choose who uses")
        frame.get_by_role("link", name="Make the house usable", exact=True).click()
        # Reuse the named fixture people on repeated runs; never touch live household data.
        existing = frame.get_by_label("Screen person", exact=True).locator("option").all_text_contents()
        if "Fixture adult" not in existing:
            add_people(frame)
        for profile in ("phone", "tablet", "specialist"):
            add = frame.locator("details").filter(has=frame.get_by_text("Add a screen", exact=True))
            if add.get_attribute("open") is None:
                add.locator("summary").click()
            frame.get_by_label("Screen name", exact=True).fill("Fixture " + profile)
            frame.get_by_label("Screen type", exact=True).select_option(profile)
            frame.get_by_label("Screen room", exact=True).select_option("kitchen")
            frame.get_by_role("button", name="Add screen", exact=True).click()
            frame.get_by_role("button", name="Save household settings", exact=True).click()
            expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            expect(frame.locator("#screen-preview")).to_be_visible()
            assert frame.locator(".preview-nav").inner_text().splitlines() == ["House", "Fixture adult", "Fixture child"]
            frame.get_by_text("Generation details", exact=True).click()
            config = json.loads(frame.locator("#screen-preview pre").inner_text())
            assert all(v.get("subview") for v in config["views"] if v["path"] in ("ambient", "dark"))
            assert "climate.fixture_system" in str(config) and "calendar.fixture_family" in str(config)
            frame.get_by_text("Generation details", exact=True).click()
            frame.get_by_text("Review publication", exact=True).click()
            frame.get_by_role("button", name="Confirm add dashboard", exact=True).click()
            expect(frame.locator("#surfaces-status")).to_contain_text("read back successfully")
            frame.locator("#screen-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"setup-{profile}-desktop.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            frame.locator("#screen-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"setup-{profile}-mobile.png"))
            page.set_viewport_size({"width": 1440, "height": 1000})
        assert not errors, errors
        browser.close()
    print("Fixture ingress: three profiles, House/people navigation and publication/readback verified; desktop/mobile captures saved.")


def add_people(frame):
    people = frame.locator("details").filter(has=frame.get_by_text("People", exact=True))
    if people.get_attribute("open") is None:
        people.locator("summary").click()
    frame.get_by_label("Person name", exact=True).fill("Fixture adult")
    frame.get_by_label("Person audience", exact=True).select_option("adult")
    frame.get_by_role("button", name="Add person", exact=True).click()
    people.locator("summary").click()
    frame.get_by_label("Person name", exact=True).fill("Fixture child")
    frame.get_by_role("button", name="Add person", exact=True).click()


if __name__ == "__main__":
    main()
