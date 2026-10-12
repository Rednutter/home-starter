"""First-use Pin + Hide + Reorder and reload acceptance in disposable ingress."""

from playwright.sync_api import expect, sync_playwright


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto("http://127.0.0.1:8124/home_starter")
        frame = page.frame_locator("#panel")
        expect(frame.locator("#surfaces-status")).to_contain_text("Choose who uses", timeout=30000)
        frame.get_by_text("Pin, hide and reorder", exact=True).click()
        owners = frame.get_by_label("Preferences for", exact=True)
        owner = owners.locator("option").filter(has_text="Person: Alex").get_attribute("value")
        owners.select_option(owner)
        pin = frame.get_by_role("checkbox", name="Pin Kitchen light", exact=True)
        hide = frame.get_by_role("checkbox", name="Hide Kitchen temperature", exact=True)
        pin.check()
        hide.check()
        frame.get_by_role("button", name="Move Kitchen light up", exact=True).click()
        expect(pin).to_be_checked()
        expect(hide).to_be_checked()
        expect(frame.get_by_role("button", name="Move Kitchen light up", exact=True)).to_be_focused()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved", timeout=30000)
        page.reload()
        expect(frame.locator("#surfaces-status")).to_contain_text("Choose who uses", timeout=30000)
        frame.get_by_text("Pin, hide and reorder", exact=True).click()
        frame.get_by_label("Preferences for", exact=True).select_option(owner)
        expect(pin).to_be_checked()
        expect(hide).to_be_checked()
        # Restore the test temperature visibility for the representative captures.
        hide.uncheck()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved", timeout=30000)
        browser.close()
    print("First-use Pin + Hide survive Reorder, focus and saved reload; test hidden measurement restored.")


if __name__ == "__main__":
    main()
