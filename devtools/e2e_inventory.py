"""Exercise household preparation, inventory and reversible room writes in mock ingress."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    shots = Path("screens/inventory-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for label, viewport, scheme in (("desktop", {"width": 1280, "height": 900}, "light"), ("mobile", {"width": 390, "height": 844}, "dark")):
            page = browser.new_page(viewport=viewport, color_scheme=scheme)
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto("http://127.0.0.1:8124/home_starter")
            frame = page.frame_locator("#panel")
            frame.get_by_role("link", name="Review setup", exact=True).click()
            expect(frame.get_by_role("button", name="Scan now", exact=True)).to_be_enabled()
            expect(frame.locator("#inventory-status")).to_contain_text("Read-only inventory")
            frame.locator("#filter-needs_room").click()
            expect(frame.locator("#filter-needs_room")).to_be_focused()
            frame.locator("#filter-all").click()
            page.screenshot(path=str(shots / f"{label}-preparation.png"), full_page=True)
            frame.get_by_role("button", name="Scan now", exact=True).click()
            expect(frame.locator("#fresh-batteries details")).not_to_have_attribute("open", "")
            # No preparation checkbox was required.
            frame.locator(".room > summary").filter(has_text="Kitchen").click()
            frame.locator("#device-fixture_kitchen > summary").click()
            device = frame.locator("#device-fixture_kitchen")
            device.locator("select").select_option("garage")
            device.get_by_role("button", name="Review room change", exact=True).click()
            expect(device.locator(".room-review")).to_contain_text("from Kitchen to Garage")
            device.locator(".room-review").scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-review.png"), full_page=True)
            device.get_by_role("button", name="Confirm room change", exact=True).click()
            expect(frame.locator(".notice")).to_contain_text("Verified: Kitchen temperature is now in Garage.")
            expect(frame.locator(".notice")).to_be_focused()
            page.screenshot(path=str(shots / f"{label}-verified.png"), full_page=True)
            frame.locator(".room > summary").filter(has_text="Garage").click()
            frame.locator("#device-fixture_kitchen > summary").click()
            device.locator("select").select_option("kitchen")
            device.get_by_role("button", name="Review room change", exact=True).click()
            device.get_by_role("button", name="Confirm room change", exact=True).click()
            expect(frame.locator(".notice")).to_contain_text("Verified: Kitchen temperature is now in Kitchen.")
            frame.get_by_role("checkbox", name="Old phone / tablet", exact=True).check()
            expect(frame.get_by_text("Possible uses: bedside clock or alarm", exact=False)).to_be_visible()
            frame.get_by_role("link", name="Get the house ready", exact=True).click()
            page.reload()
            expect(frame.get_by_role("heading", name="Fresh Batteries", exact=True)).to_be_visible()
            expect(frame.get_by_role("checkbox", name="Old phone / tablet", exact=True)).not_to_be_checked()
            page.screenshot(path=str(shots / f"{label}-final.png"), full_page=True)
            assert not errors, errors
            print(label, "preparation, inventory, verified assignment + restore, optional hardware, refresh: PASS")
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
