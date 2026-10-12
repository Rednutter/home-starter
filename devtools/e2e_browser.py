"""Drive the real UI in Chromium through the simulated HA frontend + ingress.

Expects the dev stack to be running (see README "Development"):
    mock Supervisor (scenario 'absent')  :8181  (+ fake Music Assistant :8195)
    Home Starter (container or python)    :8099
    devtools/ingress_proxy.py             :8124

    python devtools/e2e_browser.py --screens /tmp/screens

Walks: scan -> Music around the house -> Install -> progress -> discovered
integration -> (simulated user confirmation in HA) -> Check again -> ready ->
Open Music Assistant, and checks that Home Assistant was asked to navigate to
the Music Assistant app panel.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from ingress_proxy import INGRESS_TOKEN
from playwright.sync_api import expect, sync_playwright

MOCK = "http://127.0.0.1:8181"


def post(url: str) -> None:
    urllib.request.urlopen(urllib.request.Request(url, method="POST", data=b""), timeout=5).read()  # noqa: S310 - local dev URL


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screens", type=Path, default=None)
    parser.add_argument("--expect-fallback", action="store_true", help="old frontend: expect top-level navigation")
    parser.add_argument("--ha", default="http://127.0.0.1:8124", help="simulated HA frontend (ingress_proxy.py)")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--mobile", action="store_true")
    parser.add_argument("--handoff", action="store_true", help="mock runs with scenario default_role: expect the native hand-off")
    parser.add_argument("--install-fails", action="store_true", help="mock runs with scenario install_fails: expect error + hand-off")
    args = parser.parse_args()
    HA = args.ha
    shots = args.screens
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    def snap(page, name):
        if shots:
            # The app lives in the ingress iframe; capture its whole content.
            page.frame_locator("#panel").locator("#app").screenshot(path=str(shots / f"{name}.png"))

    with sync_playwright() as pw:
        # A preinstalled Chromium can be used via PLAYWRIGHT_CHROMIUM (path).
        exe = os.environ.get("PLAYWRIGHT_CHROMIUM")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        viewport = {"width": 390, "height": 2400} if args.mobile else {"width": 1280, "height": 2000}
        page = browser.new_page(viewport=viewport, color_scheme="dark" if args.dark else "light")
        console = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.goto(f"{HA}/home_starter")
        frame = page.frame_locator("#panel")

        # 1. Scan renders inside the ingress iframe.
        expect(frame.locator("#scan-status")).to_contain_text("Read-only scan", timeout=20000)
        frame.locator("#system > summary").click()
        expect(frame.locator(".tile").first).to_be_visible()
        print("scan tiles:", frame.locator(".tile-label").all_inner_texts())
        snap(page, "01-scan")

        # 2. Choose the outcome.
        frame.get_by_role("button", name="Music around the house").click()
        status = frame.locator("#music-body .status h3")
        expect(status).to_have_text("Couldn't check Music Assistant compatibility" if args.handoff else "Music Assistant is ready to install", timeout=15000)
        snap(page, "02-music-available")

        if args.handoff:
            # No direct install offered; the primary action is the App Store page.
            assert frame.get_by_role("button", name="Install Music Assistant").count() == 0
            expect(frame.locator("#music-body")).to_contain_text("Continue in Home Assistant")
            frame.get_by_role("button", name="Continue in the App Store").click()
            page.wait_for_function("window.__navigations.length > 0", timeout=5000)
            navs = page.evaluate("window.__navigations")
            assert len(navs) == 1 and navs[0]["via"] == "message", navs
            assert navs[0]["path"].startswith("/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"), navs
            print("hand-off navigation:", json.dumps(navs))
            if shots:
                page.screenshot(path=str(shots / "handoff-ha-page.png"))
            browser.close()
            print("E2E HANDOFF OK")
            return 0

        # 3. Explicit install with confirmation.
        frame.get_by_role("button", name="Install Music Assistant").click()
        expect(frame.locator(".confirm")).to_be_visible()
        snap(page, "03-confirm")
        frame.get_by_role("button", name="Yes, install it").click()
        expect(frame.locator(".operation")).to_be_visible(timeout=5000)
        snap(page, "04-installing")

        if args.install_fails:
            expect(frame.locator(".operation.failed")).to_contain_text("no space left on device", timeout=30000)
            snap(page, "install-failed")
            frame.get_by_role("button", name="Try again").click()
            expect(frame.locator(".confirm")).to_be_visible()
            frame.get_by_role("button", name="Cancel", exact=True).click()
            frame.get_by_role("button", name="Continue in Home Assistant instead").click()
            page.wait_for_function("window.__navigations.length > 0", timeout=5000)
            navs = page.evaluate("window.__navigations")
            assert navs == [{"via": "message", "path": "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"}], navs
            print("failure hand-off navigation:", json.dumps(navs))
            browser.close()
            print("E2E INSTALL-FAILURE OK")
            return 0

        # 4. After install+start, Music Assistant announces itself.
        expect(status).to_have_text("One step left: connect it to Home Assistant", timeout=60000)
        print("checks:", frame.locator(".check").all_inner_texts())
        snap(page, "05-discovered")

        # 5. User confirms the integration in HA (simulated), comes back, rechecks.
        post(f"{MOCK}/_mock/confirm_integration")
        frame.locator("#music-body").get_by_role("button", name="Check again").click()
        expect(status).to_have_text("Music Assistant is ready", timeout=15000)
        checks = frame.locator(".check").all_inner_texts()
        print("verified checks:", checks)
        assert all(c.startswith("✓") for c in checks), checks
        snap(page, "06-ready")

        # Failure after a successful check must not retain a green ready claim.
        error_start = len(console)
        page.route("**/api/music", lambda route: route.fulfill(status=503, body="Temporary failure"))
        frame.locator("#music-body").get_by_role("button", name="Check again").click()
        expect(status).to_have_text("Couldn't verify Music Assistant")
        # Chromium reports the deliberately injected HTTP failure to its console.
        expected_error = "error: Failed to load resource: the server responded with a status of 503 (Service Unavailable)"
        console[error_start:] = [c for c in console[error_start:] if c != expected_error]
        page.unroute("**/api/music")
        frame.locator("#music-body").get_by_role("button", name="Check again").click()
        expect(status).to_have_text("Music Assistant is ready")

        # 6. Open Music Assistant.
        frame.get_by_role("button", name="Open Music Assistant").first.click()
        if args.expect_fallback:
            page.wait_for_url(f"{HA}/app/d5369777_music_assistant", timeout=10000)
            navs = page.evaluate("window.__navigations")
            assert navs == [], navs  # fresh page after a top-level navigation
            print("navigated via top-level fallback to", page.url)
        else:
            page.wait_for_function("window.__navigations.length > 0", timeout=5000)
            navs = page.evaluate("window.__navigations")
            assert navs == [{"via": "message", "path": "/app/d5369777_music_assistant"}], navs
            print("navigated via HA message:", json.dumps(navs))
        expect(page.locator("#ma-page")).to_contain_text("d5369777_music_assistant")
        if shots:
            page.screenshot(path=str(shots / "07-open-music-assistant.png"))

        # Browser Back and refresh must restore the ingress app and saved outcome.
        page.go_back()
        expect(page.frame_locator("#panel").locator("#music-body .status h3")).to_have_text("Music Assistant is ready", timeout=15000)
        page.reload()
        expect(page.frame_locator("#panel").locator("#music-body .status h3")).to_have_text("Music Assistant is ready", timeout=15000)
        page.goto(f"{HA}/api/hassio_ingress/{INGRESS_TOKEN}")
        expect(page.locator("#music-body .status h3")).to_have_text("Music Assistant is ready", timeout=15000)

        errors = [c for c in console if c.startswith(("error", "pageerror"))]
        browser.close()
    if errors:
        print("console errors:", errors)
        return 1
    print("E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
