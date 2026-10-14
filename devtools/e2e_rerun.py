"""Synthetic first/returning launch, saved choices and deliberate reset in fixture ingress.

Start v3_harness.py --fixtures with a fresh ignored --data-dir first.
"""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    shots = Path("screens/rerun-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8124/home_starter")
        frame = page.frame_locator("#panel")
        expect(frame.locator("body")).to_have_attribute("data-commissioning", "maintenance")
        expect(frame.get_by_role("button", name="Finish setup", exact=True)).to_be_visible()
        expect(frame.locator("body")).to_have_attribute("data-setup-state", "existing")
        frame.get_by_role("link", name="People", exact=True).click()
        frame.get_by_label("Person name", exact=True).fill("Adult 1")
        frame.get_by_label("Person audience", exact=True).select_option("adult")
        frame.get_by_role("button", name="Add person", exact=True).click()
        frame.get_by_label("Screen name", exact=True).fill("Example tablet")
        frame.get_by_label("Screen type", exact=True).select_option("tablet")
        frame.get_by_role("button", name="Add screen", exact=True).click()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        frame.get_by_text("Pin, hide and reorder", exact=True).click()
        frame.get_by_role("checkbox", name="Pin Fixture room light", exact=True).check()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        frame.get_by_role("link", name="Activities", exact=True).click()
        frame.get_by_label("Activity name", exact=True).fill("Example appliance")
        frame.get_by_label("Appliance status", exact=True).select_option("sensor.fixture_appliance")
        frame.get_by_label("Running state", exact=True).fill("running")
        frame.get_by_label("Completed state", exact=True).fill("complete")
        frame.get_by_role("button", name="Add activity tracking", exact=True).click()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        for _ in range(2):
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            frame.get_by_text("Review publication", exact=True).click()
            frame.get_by_role("button", name="Confirm add dashboard" if _ == 0 else "Confirm dashboard update", exact=True).click()
            expect(frame.locator("#surfaces-status")).to_contain_text("read back successfully")
        for _ in range(2):
            page.reload()
            expect(frame.locator("body")).to_have_attribute("data-setup-state", "existing")
            expect(frame.locator("#installation-body")).to_contain_text("1 people · 1 screens · 1 activity rules")
            expect(frame.locator("#installation-body")).to_contain_text("Published · matches saved version")
            assert "false" not in frame.locator("#installation-body").inner_text()
            assert frame.locator("#review-setup").get_attribute("open") is None
            frame.get_by_text("Pin, hide and reorder", exact=True).click()
            expect(frame.get_by_role("checkbox", name="Pin Fixture room light", exact=True)).to_be_checked()
        page.route("**/api/installation/review", lambda route: route.fulfill(status=409, body="Fixture review conflict"))
        frame.get_by_role("button", name="Mark these differences reviewed", exact=True).click()
        expect(frame.locator("#installation-status")).to_contain_text("Fixture review conflict")
        expect(frame.get_by_role("button", name="Mark these differences reviewed", exact=True)).to_be_enabled()
        frame.locator("#house-status").scroll_into_view_if_needed()
        page.screenshot(path=str(shots / "review-error.png"))
        page.unroute("**/api/installation/review")
        frame.get_by_role("button", name="Mark these differences reviewed", exact=True).click()
        expect(frame.locator("#changes-body")).to_contain_text("No pending differences")
        frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(shots / "existing-desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
        page.evaluate("window.scrollTo(0, 0)")
        page.screenshot(path=str(shots / "existing-mobile.png"))
        frame.get_by_role("link", name="Review setup", exact=True).click()
        frame.locator("#reset-setup > summary").click()
        expect(frame.get_by_role("button", name="Reset Home Starter setup", exact=True)).to_be_disabled()
        frame.get_by_label("Reset confirmation", exact=True).fill("RESET HOME STARTER")
        frame.get_by_role("button", name="Reset Home Starter setup", exact=True).click()
        expect(frame.get_by_role("heading", name="Make Home Assistant useful for your household", exact=True)).to_be_visible()
        assert not errors, errors
        browser.close()
    print("Repeat-launch UI: initial review, persisted people/screen/pin/activity, repeated publication, returning landing and explicit reset verified.")


if __name__ == "__main__":
    main()
