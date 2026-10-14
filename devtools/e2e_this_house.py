"""Synthetic ingress checks for native registry reconciliation and returning state."""

import argparse
import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import expect, sync_playwright


def exercise(url):
    shots = Path("screens/this-house-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for label, viewport, scheme in (("desktop", {"width": 1280, "height": 900}, "light"), ("mobile", {"width": 390, "height": 844}, "dark")):
            page = browser.new_page(viewport=viewport, color_scheme=scheme)
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(url)
            frame = page.frame_locator("#panel")
            expect(frame.locator("#this-house-status")).to_contain_text("Live HA records")
            frame.get_by_role("link", name="This House", exact=True).click()
            page.screenshot(path=str(shots / f"{label}-house.png"))

            person = frame.locator("#this-house-people .house-row").filter(has_text="Example adult")
            person.locator("summary").click()
            person.get_by_label("Household role for Example adult").select_option("adult")
            person.get_by_role("button", name="Review person", exact=True).click()
            person.get_by_role("button", name="Confirm person", exact=True).click()
            expect(frame.locator("#this-house-body")).to_contain_text("Person confirmation saved.")
            expect(frame.locator("#this-house-status")).to_be_focused()

            floors = frame.locator(".house-part").filter(has=frame.get_by_role("heading", name="Floors & rooms", exact=True))
            floors.get_by_text("Floors (", exact=False).first.click()
            add_floor = floors.locator(".house-row").filter(has_text="Add a floor")
            add_floor.locator("summary").click()
            add_floor.get_by_label("Floor name", exact=True).fill("Example floor " + label)
            add_floor.get_by_role("button", name="Review floor change", exact=True).click()
            add_floor.get_by_role("button", name="Confirm floor change", exact=True).click()
            expect(frame.locator("#this-house-body")).to_contain_text("Floor saved and read back")

            kitchen = frame.locator(".house-part .house-row").filter(has=frame.locator("summary").filter(has_text="Kitchen")).first
            kitchen.locator("summary").click()
            kitchen.get_by_label("Floor for Kitchen", exact=True).select_option(label="Example floor " + label)
            kitchen.get_by_role("button", name="Review area change", exact=True).click()
            kitchen.get_by_role("button", name="Confirm area change", exact=True).click()
            expect(frame.locator("#this-house-body")).to_contain_text("Room saved and read back")

            frame.get_by_role("button", name="All equipment", exact=True).click()
            device = frame.locator("#placement-fixture_kitchen")
            device.locator("summary").click()
            device.get_by_label("Room for Kitchen temperature").select_option("garage" if label == "desktop" else "kitchen")
            device.get_by_role("button", name="Review placement", exact=True).click()
            device.locator(".house-review").first.scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-placement-review.png"))
            device.get_by_role("button", name="Confirm placement", exact=True).click()
            expect(frame.locator("#this-house-body")).to_contain_text("Device placement confirmed and read back from HA.")

            device.locator("summary").first.click()
            device.locator("summary").filter(has_text="Physical connection or function").click()
            device.get_by_label("Physical note for Kitchen temperature").fill("Measures the shared living space")
            device.get_by_role("button", name="Review physical note", exact=True).click()
            device.get_by_role("button", name="Confirm physical note", exact=True).click()
            expect(frame.locator("#this-house-body")).to_contain_text("Physical note saved.")
            page.reload()
            expect(frame.locator("#this-house-status")).to_contain_text("Live HA records")
            frame.get_by_role("button", name="All equipment", exact=True).click()
            device.locator("summary").first.click()
            device.locator("summary").filter(has_text="Physical connection or function").click()
            expect(device.get_by_label("Physical note for Kitchen temperature")).to_have_value("Measures the shared living space")
            page.screenshot(path=str(shots / f"{label}-return.png"))
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth"), "Horizontal overflow"
            assert "null" not in frame.locator("#this-house").inner_text().splitlines()
            assert not errors, errors
            page.close()
            print(label, "people, floor create, area update, placement write, notes, reload: PASS")
        browser.close()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url")
    args = parser.parse_args()
    if args.url:
        await asyncio.to_thread(exercise, args.url)
        return
    from aiohttp.test_utils import TestServer
    from ingress_proxy import build_app
    from mock_supervisor import TOKEN, MockSupervisor

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter.household import HouseholdStore, empty_household
    from homestarter.server import create_app
    from homestarter.settings import Settings

    with TemporaryDirectory(prefix="this-house-fixture-") as directory:
        mock = MockSupervisor("ready", ma_host="127.0.0.1")
        async with TestServer(mock.app()) as supervisor, TestServer(mock.ma_app()) as ma:
            mock.ma_port = ma.port
            settings = Settings.from_env(
                {
                    "SUPERVISOR_TOKEN": TOKEN,
                    "HOME_STARTER_SUPERVISOR_URL": str(supervisor.make_url("")),
                    "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
                    "HOME_STARTER_MA_PORT": str(ma.port),
                    "HOME_STARTER_DATA_DIR": directory,
                }
            )
            HouseholdStore(directory).save(empty_household())
            async with TestServer(create_app(settings)) as app, TestServer(build_app(str(app.make_url("")))) as ingress:
                await asyncio.to_thread(exercise, str(ingress.make_url("/home_starter")))


if __name__ == "__main__":
    asyncio.run(main())
