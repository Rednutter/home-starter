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
            person.locator("summary").click()
            person.get_by_label("Presence for Example adult", exact=True).select_option("")
            person.get_by_role("button", name="Review presence choice", exact=True).click()
            expect(frame.locator("#this-house-status")).to_contain_text("Choose whether presence is wanted or intentionally untracked first.")
            expect(person.get_by_role("button", name="Confirm presence choice", exact=True)).to_have_count(0)
            person.get_by_label("Presence for Example adult", exact=True).select_option("untracked")
            person.get_by_role("button", name="Review presence choice", exact=True).click()
            person.get_by_role("button", name="Confirm presence choice", exact=True).click()
            expect(person.locator("summary")).to_contain_text("intentionally untracked")
            page.reload()
            expect(person.locator("summary")).to_contain_text("intentionally untracked")

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
            device.get_by_role("button", name="Serves several rooms", exact=True).click()
            device.get_by_role("button", name="Confirm coverage", exact=True).click()
            expect(device.locator("summary").first).to_contain_text("Serves several rooms")
            page.reload()
            frame.get_by_role("button", name="All equipment", exact=True).click()
            expect(device.locator("summary").first).to_contain_text("Serves several rooms")
            device.locator("summary").first.click()
            device.locator("summary").filter(has_text="Physical connection or function").click()
            expect(device.get_by_label("Physical note for Kitchen temperature")).to_have_value("Measures the shared living space")
            page.screenshot(path=str(shots / f"{label}-return.png"))
            room_browser = frame.locator("#house-room-view")
            room_browser.locator(":scope > summary").click()
            room_browser.locator(":scope > details").filter(has=frame.locator("summary").filter(has_text="Example floor " + label)).first.locator(
                ":scope > summary"
            ).click()
            room_kitchen = room_browser.locator(".house-row").filter(has=frame.locator(":scope > summary").filter(has_text="Kitchen ·")).first
            room_kitchen.locator(":scope > summary").click()
            room_device = room_browser.locator("#room-device-fixture_kitchen")
            if label == "mobile":
                room_device.locator(":scope > summary").click()
                expect(room_device.get_by_label("Room for Kitchen temperature")).to_have_value("kitchen")
                room_device.get_by_label("Room for Kitchen temperature").select_option("garage")
                room_device.get_by_role("button", name="Review placement", exact=True).click()
                room_device.get_by_role("button", name="Confirm placement", exact=True).click()
                expect(frame.locator("#this-house-body")).to_contain_text("Device placement confirmed and read back from HA.")
                page.reload()
                frame.get_by_role("button", name="All equipment", exact=True).click()
                device.locator(":scope > summary").click()
                expect(device.get_by_label("Room for Kitchen temperature")).to_have_value("garage")
                room_browser.locator(":scope > summary").click()
                garage = room_browser.locator(".house-row").filter(has=frame.locator(":scope > summary").filter(has_text="Garage ·")).first
                floor = room_browser.locator(":scope > details").filter(has=frame.locator("#room-device-fixture_kitchen"))
                floor.locator(":scope > summary").click()
                garage.locator(":scope > summary").click()
                room_device.locator(":scope > summary").click()
                expect(room_device.get_by_label("Room for Kitchen temperature")).to_have_value("garage")
            else:
                expect(room_kitchen.locator(":scope > summary")).to_contain_text("0 equipment records · 2 services")
                expect(room_kitchen).to_contain_text("Example family")
            room_browser.scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-rooms.png"))
            readiness = frame.locator("#this-house-capabilities")
            expect(readiness).to_contain_text("Evidence checked", timeout=20000)
            climate = readiness.locator(".house-row").filter(has_text="Climate")
            expect(climate.locator("summary")).to_contain_text("Partially ready")
            climate.locator("summary").click()
            expect(climate).to_contain_text("does not prove")
            readiness.scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-readiness.png"))
            page.route(
                "**/api/house/status",
                lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"Evidence temporarily unavailable"}'),
            )
            readiness.get_by_role("button", name="Refresh readiness evidence", exact=True).click()
            expect(readiness).to_contain_text("Readiness evidence unavailable")
            frame.get_by_role("button", name="Refresh from HA", exact=True).click()
            expect(frame.locator("#this-house-status")).to_contain_text("Live HA records")
            page.unroute("**/api/house/status")
            readiness.get_by_role("button", name="Refresh readiness evidence", exact=True).click()
            expect(readiness).to_contain_text("Evidence checked", timeout=20000)
            calendars = readiness.locator(".house-row").filter(has_text="Calendars")
            calendars.locator("summary").click()
            calendars.get_by_role("link", name="Review Calendars", exact=True).click()
            expect(frame.locator("#home-readiness")).to_be_visible()
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth"), "Horizontal overflow"
            assert "null" not in frame.locator("#this-house").inner_text().splitlines()
            assert not errors, errors
            page.close()
            print(label, "people, floors, rooms, placement, notes, readiness, evidence outage, native handoff, reload: PASS")
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
        mock.entity_registry.extend(
            {"entity_id": entity_id, "name": name, "platform": "example", "device_id": None, "area_id": "kitchen", "disabled_by": None}
            for entity_id, name in (("climate.example_zone", "Example zone"), ("calendar.example_family", "Example family"))
        )
        mock.activity_states.update(
            {
                entity_id: {"entity_id": entity_id, "state": "off", "attributes": {"friendly_name": name}}
                for entity_id, name in (("climate.example_zone", "Example zone"), ("calendar.example_family", "Example family"))
            }
        )
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
