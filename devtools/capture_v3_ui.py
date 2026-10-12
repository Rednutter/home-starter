"""Republish only owned disposable screens and capture setup at desktop/mobile sizes."""

import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    paths = json.loads(Path("screens/v3-paths.json").read_text())
    shots = Path("screens/v3-ui")
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto("http://127.0.0.1:8124/home_starter")
        frame = page.frame_locator("#panel")
        expect(frame.locator("#surfaces-status")).to_contain_text("Choose who uses", timeout=30000)
        for profile, path in paths.items():
            frame.get_by_label("Selected screen", exact=True).select_option(path.removeprefix("home-starter-"))
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            expect(frame.locator("#screen-preview")).to_be_visible(timeout=30000)
            frame.get_by_text("Review publication", exact=True).click()
            frame.get_by_role("button", name="Confirm dashboard update", exact=True).click()
            expect(frame.locator("#surfaces-status")).to_contain_text("read back successfully", timeout=30000)
            frame.locator("#screen-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"setup-{profile}-desktop.png"))
        for label, viewport, scheme in (("desktop", {"width": 1280, "height": 900}, "light"), ("mobile", {"width": 390, "height": 844}, "dark")):
            page.set_viewport_size(viewport)
            page.emulate_media(color_scheme=scheme)
            frame.get_by_role("link", name="Make the house usable", exact=True).click()
            page.screenshot(path=str(shots / f"setup-{label}.png"))
            frame.get_by_label("Selected screen", exact=True).select_option(paths["phone"].removeprefix("home-starter-"))
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            expect(frame.locator("#screen-preview")).to_be_visible(timeout=30000)
            frame.locator("#screen-preview").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"setup-phone-{label}.png"))
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth"), label
        browser.close()
    print("Owned disposable dashboards updated and verified; desktop/mobile setup and previews captured without horizontal overflow.")


if __name__ == "__main__":
    main()
