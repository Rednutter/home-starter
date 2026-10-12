"""Repeatable render/control verification of the generated disposable dashboards."""
# ruff: noqa: S310 -- URLs are hardcoded to the disposable loopback Core.

import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    paths = json.loads(Path("screens/v3-paths.json").read_text())
    shots = Path("screens/v3-ui")
    base = "http://127.0.0.1:18123"

    def climate():
        with urlopen(  # noqa: S310 - hardcoded disposable loopback URL
            Request(base + "/api/states/climate.kitchen_air_conditioning", headers={"Authorization": "Bearer " + credentials["token"]}),
            timeout=10,  # noqa: S310
        ) as response:
            return json.load(response)["attributes"]["temperature"]

    def verify_target(target):
        deadline = time.monotonic() + 10
        while abs(climate() - target) >= 0.001 and time.monotonic() < deadline:
            time.sleep(0.1)
        assert abs(climate() - target) < 0.001

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(base)
        page.get_by_label("Username", exact=True).fill(credentials["username"])
        page.get_by_label("Password", exact=True).fill(credentials["password"])
        page.get_by_role("button", name="Log in", exact=True).click()
        expect(page.get_by_role("button", name="Log in", exact=True)).not_to_be_visible(timeout=30000)
        expect(page.get_by_role("button", name="Sidebar toggle", exact=True)).to_be_visible(timeout=30000)
        for profile, path in paths.items():
            page.locator(f'a[href="/{path}"]').click()
            expect(page.locator("hui-sections-view")).to_be_visible(timeout=30000)
            expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
            expect(page.get_by_text("Needs attention", exact=True)).not_to_be_visible()
            assert page.locator("hui-error-card").count() == 0
            if profile == "specialist":
                thermostat = page.locator("hui-thermostat-card")
                expect(thermostat).to_be_visible()
                print(
                    "Thermostat buttons:",
                    thermostat.get_by_role("button").evaluate_all(
                        "els => els.map(e => ({label:e.getAttribute('aria-label'),title:e.getAttribute('title'),text:e.textContent.trim()}))"
                    ),
                )
                original = climate()
                thermostat.get_by_role("button").nth(1).click()  # Native card's observed plus button; HA supplies no accessible label.
                expect(thermostat).to_contain_text(str(round(original + 0.1, 1)))
                verify_target(round(original + 0.1, 1))
                thermostat.get_by_role("button").nth(0).click()  # Observed minus button.
                expect(thermostat).to_contain_text(str(round(original, 1)))
                verify_target(original)
            # Templates must render; a visible section is not sufficient evidence.
            if profile in ("phone", "specialist"):
                expect(page.get_by_text("21.5°C", exact=True)).to_be_visible(timeout=30000)
            page.screenshot(path=str(shots / f"native-{profile}-desktop.png"))
        page.locator(f'a[href="/{paths["phone"]}"]').click()
        page.set_viewport_size({"width": 390, "height": 844})
        expect(page.get_by_text("Loading...", exact=True)).not_to_be_visible(timeout=30000)
        expect(page.get_by_text("21.5°C", exact=True)).to_be_visible(timeout=30000)
        page.screenshot(path=str(shots / "native-phone-mobile.png"))
        browser.close()
    print("Native dashboards fully loaded; climate target adjusted + restored through generated card; phone/mobile templates verified.")


if __name__ == "__main__":
    main()
