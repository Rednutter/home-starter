"""Six commissioning journeys against the named disposable loopback fixture only."""

import json
from pathlib import Path
from urllib.request import Request, urlopen

from fixture_urls import fixture_url
from playwright.sync_api import expect, sync_playwright


def fixture_api(path, body=None):
    request = Request(  # noqa: S310 -- fixture_url always returns fixed loopback, only port offset varies
        fixture_url("/api/" + path, "app"),
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "X-Remote-User-Id": "a1b2c3d4e5f6"},
    )
    with urlopen(request) as response:  # noqa: S310 -- fixed loopback fixture; no credentials or arbitrary URL
        return json.load(response)


def reset_fixture():
    house = fixture_api("household")["household"]
    fixture_api("installation/reset", {"revision": house["revision"], "confirm": True, "acknowledgement": "RESET HOME STARTER"})


def capture_review(page, frame, path, width, height):
    page.set_viewport_size({"width": width, "height": height})
    content_height = frame.locator("body").evaluate("body => body.scrollHeight")
    page.set_viewport_size({"width": width, "height": max(height, content_height + 20)})
    frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(path), full_page=True, animations="disabled")
    page.set_viewport_size({"width": width, "height": height})


def main():
    shots = Path("screens/commissioning-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scenario in ("legacy", "simple", "music", "waste", "communications", "minimal"):
            if scenario != "legacy":
                reset_fixture()
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(fixture_url("/home_starter"))
            frame = page.frame_locator("#panel")
            if scenario == "legacy":
                expect(frame.locator("body")).to_have_attribute("data-commissioning", "maintenance")
                expect(frame.get_by_role("button", name="Finish setup", exact=True)).to_be_visible()
                frame.get_by_role("button", name="Finish setup", exact=True).click()
            else:
                expect(frame.get_by_role("heading", name="Make Home Assistant useful for your household", exact=True)).to_be_visible()
                expect(frame.locator("#house-status")).not_to_be_visible()
                if scenario == "simple":
                    page.screenshot(path=str(shots / "welcome-desktop.png"))
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.screenshot(path=str(shots / "welcome-mobile.png"))
                    page.set_viewport_size({"width": 1280, "height": 1000})
                frame.get_by_role("button", name="Prepare my home", exact=True).click()
            expect(frame.get_by_role("heading", name="Fresh Batteries", exact=True)).to_be_visible()
            if scenario == "simple":
                page.screenshot(path=str(shots / "prepare-desktop.png"))
            frame.get_by_role("button", name="Scan my home", exact=True).click()
            expect(frame.get_by_role("heading", name="Here is what we found", exact=True)).to_be_visible()
            frame.get_by_role("button", name="Tell us about your household", exact=True).click()
            frame.get_by_label("Name or nickname", exact=True).fill("Example adult")
            frame.get_by_role("button", name="Add household member", exact=True).click()
            frame.get_by_role("button", name="Continue to choices", exact=True).click()
            expect(frame.get_by_role("heading", name="What would you like help with?", exact=True)).to_be_visible()
            for name in ("Music & radio", "Household calling / intercom", "Waste collection / bins"):
                expect(frame.get_by_role("checkbox", name=name, exact=True)).not_to_be_checked()
            selected = {
                "simple": ["Household displays", "Calendars & events"],
                "music": ["Music & radio"],
                "waste": ["Waste collection / bins"],
                "communications": ["Household calling / intercom"],
            }.get(scenario, [])
            for name in selected:
                frame.get_by_role("checkbox", name=name, exact=True).check()
            if scenario == "simple":
                page.screenshot(path=str(shots / "choose-desktop.png"))
            frame.get_by_role("button", name="Configure selected capabilities", exact=True).click()
            expect(frame.get_by_role("heading", name="Set up your choices", exact=True)).to_be_visible()
            if scenario == "simple":
                frame.get_by_label("Commissioning screen name", exact=True).fill("Example phone")
                frame.get_by_role("button", name="Add display to plan", exact=True).click()
                frame.get_by_text("Calendars & events", exact=True).click()
                frame.get_by_role("checkbox", name="Fixture family", exact=True).check()
                frame.get_by_role("checkbox", name="Example phone", exact=True).check()
            if scenario == "music":
                frame.get_by_text("Music & radio", exact=True).click()
                expect(frame.locator("#commissioning-body")).to_contain_text("Music Assistant is ready")
                expect(frame.get_by_role("checkbox", name="spotify", exact=True)).not_to_be_checked()
                expect(frame.get_by_role("checkbox", name="Run Music Assistant setup after Go if needed", exact=True)).not_to_be_checked()
            if scenario == "communications":
                frame.get_by_text("Household calling / intercom", exact=True).click()
                expect(frame.locator("#commissioning-body")).to_contain_text("Existing SIP/VoIP")
                frame.get_by_label("service for Household calling / intercom", exact=True).select_option("existing")
            frame.get_by_role("button", name="Review setup plan", exact=True).click()
            expect(frame.get_by_role("heading", name="Ready to set up your home", exact=True)).to_be_visible()
            draft = fixture_api("commissioning")["state"]
            assert draft["phase"] == "reviewed"
            assert not fixture_api("household")["household"]["configured"] if scenario != "legacy" else True
            if scenario == "simple":
                capture_review(page, frame, shots / "review-desktop.png", 1280, 1000)
                capture_review(page, frame, shots / "review-mobile.png", 390, 844)
                page.set_viewport_size({"width": 1280, "height": 1000})
            page.reload()
            expect(frame.get_by_role("heading", name="Ready to set up your home", exact=True)).to_be_visible()
            frame.get_by_role("button", name="Set up my home", exact=True).click()
            if selected:
                expect(frame.get_by_role("heading", name="Finish verification", exact=True)).to_be_visible()
                if scenario == "simple":
                    expect(frame.locator("#commissioning-body")).to_contain_text("Real upcoming event retrieved")
                    # Synthetic user attestation tests the contract, not native rendering.
                    frame.get_by_role("button", name="I opened this screen and it displayed correctly", exact=True).click()
                else:
                    title = {"music": "Music & radio", "waste": "Waste collection / bins", "communications": "Household calling / intercom"}[scenario]
                    frame.get_by_role("button", name="Skip " + title + " for now", exact=True).click()
            expect(frame.get_by_role("heading", name="Setup review complete", exact=True)).to_be_visible()
            if scenario == "simple":
                page.screenshot(path=str(shots / "complete-desktop.png"))
            frame.get_by_role("button", name="Go to Home Readiness", exact=True).click()
            expect(frame.locator("body")).to_have_attribute("data-commissioning", "maintenance")
            expect(frame.locator("#home-readiness")).to_be_visible()
            page.reload()
            expect(frame.locator("body")).to_have_attribute("data-commissioning", "maintenance")
            assert not errors, errors
            page.close()
            print("Commissioning browser: " + scenario + " passed")
        browser.close()


if __name__ == "__main__":
    main()
