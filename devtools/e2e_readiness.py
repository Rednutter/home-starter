"""Synthetic conditional interview, source verification and persistent readiness UI."""

from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    output = Path("screens/readiness-ui")
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8124/home_starter")
        frame = page.frame_locator("#panel")
        expect(frame.locator("#readiness-status")).to_contain_text("Saved decisions loaded")
        # Explicit reset only in this named loopback fixture stack; never a live home.
        frame.get_by_role("link", name="Review setup", exact=True).click()
        frame.locator("#reset-setup > summary").click()
        frame.get_by_label("Reset confirmation", exact=True).fill("RESET HOME STARTER")
        frame.get_by_role("button", name="Reset Home Starter setup", exact=True).click()
        expect(frame.locator("body")).to_have_attribute("data-setup-state", "first-run")
        frame.get_by_role("link", name="People", exact=True).click()
        for name, audience in (("Adult 1", "adult"), ("Child 1", "everyone")):
            frame.get_by_label("Person name", exact=True).fill(name)
            frame.get_by_label("Person audience", exact=True).select_option(audience)
            frame.get_by_role("button", name="Add person", exact=True).click()
        frame.get_by_label("Screen name", exact=True).fill("Example phone")
        frame.get_by_role("button", name="Add screen", exact=True).click()
        frame.get_by_role("button", name="Save household settings", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("settings saved")
        frame.get_by_role("button", name="Refresh readiness", exact=True).click()
        expect(frame.locator("#readiness-displays")).to_contain_text("1 configured")
        frame.locator("#readiness-household > summary").click()
        frame.get_by_label("Household role for Adult 1", exact=True).select_option("adult")
        frame.get_by_label("Household role for Child 1", exact=True).select_option("child")
        frame.locator("#readiness-communications > summary").click()
        expect(frame.locator("#readiness-communications")).not_to_contain_text("Existing SIP/VoIP")
        frame.get_by_label("Decision for Communications", exact=True).select_option("wanted")
        expect(frame.locator("#readiness-communications")).to_contain_text("Existing SIP/VoIP")
        expect(frame.get_by_role("checkbox", name="Adult 1", exact=True)).not_to_be_checked()
        expect(frame.get_by_role("checkbox", name="Child 1", exact=True)).not_to_be_checked()
        expect(frame.locator("#readiness-communications")).to_contain_text("no extension or calling permission is enabled")
        frame.get_by_label("Decision for Communications", exact=True).select_option("later")
        frame.locator("#readiness-waste > summary").click()
        frame.get_by_label("Decision for Waste collection", exact=True).select_option("not_wanted")
        frame.locator("#readiness-calendars > summary").click()
        frame.get_by_label("Decision for Calendars", exact=True).select_option("wanted")
        frame.locator("#readiness-calendars").get_by_role("checkbox", name="Fixture family", exact=True).check()
        frame.locator("#readiness-calendars").get_by_role("checkbox", name="Example phone", exact=True).check()
        expect(frame.get_by_role("button", name="Verify Calendars source", exact=True)).to_be_disabled()
        frame.get_by_role("button", name="Save readiness choices", exact=True).click()
        expect(frame.locator("#readiness-household > summary")).to_contain_text("Context recorded")
        expect(frame.locator("#readiness-communications > summary")).to_contain_text("Not now")
        frame.get_by_role("button", name="Verify Calendars source", exact=True).click()
        expect(frame.locator("#readiness-calendars > summary")).to_contain_text("Verified upcoming event")
        for _ in range(2):
            page.reload()
            expect(frame.locator("#readiness-calendars > summary")).to_contain_text("Verified upcoming event")
            expect(frame.locator("#readiness-waste > summary")).to_contain_text("Not wanted")
            expect(frame.locator("#readiness-communications > summary")).to_contain_text("Not now")
        frame.get_by_role("link", name="Screens", exact=True).click()
        frame.get_by_role("button", name="Generate screen", exact=True).click()
        expect(frame.locator("#surfaces-status")).to_contain_text("Preview ready")
        expect(frame.locator("#screen-preview")).not_to_contain_text("Bins")
        expect(frame.locator("#screen-preview")).to_contain_text("Today")
        for size, name in (({"width": 1280, "height": 1000}, "desktop"), ({"width": 390, "height": 844}, "mobile")):
            page.set_viewport_size(size)
            frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
            page.evaluate("window.scrollTo(0, 0)")
            page.screenshot(path=str(output / f"readiness-{name}.png"))
            frame.get_by_role("link", name="Home Readiness", exact=True).click()
            frame.locator("#readiness-calendars > summary").click()
            expect(frame.get_by_role("button", name="Verify Calendars source", exact=True)).to_be_visible()
            page.screenshot(path=str(output / f"calendar-{name}.png"))
            frame.locator("#readiness-calendars > summary").click()
        assert not errors, errors
        browser.close()
    print("Readiness UI: membership, child call plan, deferral, selected calendar/display, event verification and repeat visits passed.")


if __name__ == "__main__":
    main()
