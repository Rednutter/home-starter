"""Music acceptance against the fixed synthetic loopback harness only."""

import argparse
from pathlib import Path

from fixture_urls import fixture_url
from mock_music_runtime import TOKEN
from playwright.sync_api import expect, sync_playwright


def capture(page, frame, target, shots, state):
    for width, height, name in ((1280, 900, "desktop"), (390, 844, "mobile")):
        page.set_viewport_size({"width": width, "height": height})
        content_height = frame.locator("body").evaluate("el => el.scrollHeight")
        page.set_viewport_size({"width": width, "height": max(height, content_height + 80)})
        target.scroll_into_view_if_needed()
        assert frame.locator("body").evaluate("el => el.scrollWidth <= innerWidth"), "horizontal overflow"
        frame.locator("#music").screenshot(path=str(shots / (state + name + ".png")))
        page.set_viewport_size({"width": width, "height": height})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--infrequent", action="store_true")
    args = parser.parse_args()
    shots = Path("screens/music-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(fixture_url("/home_starter"))
        frame = page.frame_locator("iframe")
        frame.get_by_role("link", name="Music", exact=True).click()
        runtime = frame.locator(".music-runtime")
        expect(runtime.get_by_label("Music Assistant API token", exact=True)).to_have_count(1)
        if runtime.locator("details").first.get_attribute("open") is None:
            runtime.locator("summary").first.click()
        capture(page, frame, runtime, shots, "connection-")
        runtime.get_by_label("Music Assistant API token", exact=True).fill(TOKEN)
        connect = runtime.get_by_role("button", name="Connect Music Assistant", exact=True)
        (connect if connect.count() else runtime.get_by_role("button", name="Replace API connection", exact=True)).click()
        expect(runtime.get_by_text("Fixture radio · connected", exact=True)).to_be_visible()
        expect(runtime.get_by_text("Music is incomplete until", exact=False)).to_be_visible()
        expect(runtime.get_by_text("Fixture disabled account · disabled", exact=True)).to_be_visible()
        expect(runtime.get_by_text("Spotify Connect", exact=True)).to_have_count(0)
        runtime.get_by_text("Add or repair a music source", exact=True).click()
        runtime.get_by_label("Source to set up", exact=True).select_option(label="Spotify")
        expect(runtime.get_by_text("For Spotify, open Music Assistant", exact=False)).to_be_visible()
        runtime.get_by_label("Music source to test").select_option("fixture_radio")
        runtime.get_by_label("Speaker to test").select_option("fixture_speaker")
        runtime.get_by_role("button", name="Check selected speaker playback", exact=True).click()
        expect(runtime.get_by_role("button", name="I heard it on this speaker", exact=True)).to_be_visible(timeout=20000)
        if args.infrequent:
            expect(runtime.get_by_text("MA reports playback; automatic progress is unverified", exact=False)).to_be_visible()
        capture(page, frame, runtime, shots, "pending-")
        # A reload must not fabricate audible confirmation.
        page.reload()
        frame.get_by_role("link", name="Music", exact=True).click()
        runtime = frame.locator(".music-runtime")
        expect(runtime.get_by_role("button", name="I heard it on this speaker", exact=True)).to_be_visible()
        expect(runtime.get_by_text("Music is incomplete until", exact=False)).to_be_visible()
        runtime.get_by_role("button", name="I heard it on this speaker", exact=True).click()
        expect(runtime.get_by_text("Playback verified: Fixture radio on Fixture speaker.", exact=False)).to_be_visible()
        if args.infrequent:
            expect(runtime.get_by_text("You confirmed hearing it; automatic progress is unverified.", exact=False)).to_be_visible()
        capture(page, frame, runtime, shots, "")
        runtime.get_by_text("Music Assistant connection", exact=True).click()
        runtime.get_by_label("Music Assistant API token", exact=True).fill("invalid-fixture-token")
        runtime.get_by_role("button", name="Replace API connection", exact=True).click()
        expect(runtime.get_by_text("Music Assistant denied API access.", exact=False)).to_be_visible()
        runtime.get_by_role("button", name="Refresh sources and speakers", exact=True).click()
        expect(runtime.get_by_text("Fixture radio · connected", exact=True)).to_be_visible()
        assert not errors, errors
        browser.close()
    print("Music browser flow passed: recognition, missing-source guide, playback evidence, reload, hearing, scoped proof and failed-replacement preservation.")


if __name__ == "__main__":
    main()
