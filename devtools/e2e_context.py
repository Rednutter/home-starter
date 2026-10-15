"""Self-hosted synthetic ingress acceptance; never claims native dashboard rendering."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from aiohttp.test_utils import TestServer
from playwright.sync_api import expect, sync_playwright


def exercise(url):
    shots = Path("screens/context-ui")
    shots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for label, size in (("desktop", {"width": 1280, "height": 900}), ("mobile", {"width": 390, "height": 844})):
            page = browser.new_page(viewport=size, color_scheme="light" if label == "desktop" else "dark")
            errors = []
            page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
            page.goto(url)
            frame = page.frame_locator("#panel")
            section = frame.locator("#household-context")
            section.locator(":scope > summary").click()
            expect(frame.locator("#context-status")).to_contain_text("Current context read", timeout=20000)
            frame.get_by_role("button", name="Add date-scoped morning rule", exact=True).click()
            rule = section.locator(".house-row").filter(has_text="New morning rule")
            rule.locator("summary").click()
            rule.get_by_label("Morning rule", exact=False).fill("Example kit check " + label)
            rule.locator('input[type="date"]').nth(0).fill("2026-01-01")
            rule.locator('input[type="date"]').nth(1).fill("2026-12-31")
            rule.get_by_label("Thu", exact=True).check()
            frame.get_by_role("button", name="Save context choices", exact=True).click()
            expect(frame.locator("#context-status")).to_contain_text("Context choices saved")
            page.reload()
            section.locator(":scope > summary").click()
            expect(section).to_contain_text("Example kit check " + label, timeout=20000)
            departure = section.locator("details").filter(has=frame.locator("summary").filter(has_text="People and departures for a chosen event")).first
            departure.locator(":scope > summary").click()
            departure.get_by_label("Event to link").select_option(index=1)
            departure.get_by_role("button", name="Link selected event", exact=True).click()
            link = section.locator(".house-row").filter(has_text="Example appointment").first
            link.locator(":scope > summary").click()
            link.get_by_label("Travel minutes", exact=False).fill("17")
            link.get_by_label("Departure margin", exact=False).fill("5")
            link.get_by_label("Departure rounding", exact=False).select_option("10")
            frame.get_by_role("button", name="Save context choices", exact=True).click()
            expect(frame.locator("#context-status")).to_contain_text("Context choices saved")
            section.scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-settings.png"))
            page.reload()
            section.locator(":scope > summary").click()
            link.locator(":scope > summary").click()
            expect(link.get_by_label("Travel minutes", exact=False)).to_have_value("17")
            expect(link.get_by_label("Departure rounding", exact=False)).to_have_value("10")
            link.scroll_into_view_if_needed()
            page.screenshot(path=str(shots / f"{label}-departure.png"))
            frame.get_by_role("button", name="Generate screen", exact=True).click()
            expect(frame.locator("#screen-preview")).to_contain_text("Household context now", timeout=20000)
            expect(frame.locator("#screen-preview")).to_contain_text("may enter recorder history")
            assert section.locator("input").count() > 0
            assert frame.locator("body").evaluate("el => el.scrollWidth <= el.clientWidth"), "Horizontal overflow"
            assert not errors, errors
            page.close()
            print(label, "context rules, event departure, persistence, wall preview and privacy notice: PASS")
        browser.close()


async def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter.household import HouseholdStore
    from homestarter.inventory import collect_inventory
    from homestarter.readiness import empty, selection_signature
    from homestarter.server import K_STATE, create_app
    from homestarter.settings import Settings
    from ingress_proxy import build_app
    from mock_supervisor import TOKEN, MockSupervisor

    with TemporaryDirectory(prefix="context-fixture-") as directory:
        mock = MockSupervisor("ready", ma_host="127.0.0.1")
        source = "calendar.example_context"
        mock.entity_registry.append({"entity_id": source, "name": "Example calendar", "platform": "local_calendar", "device_id": None})
        mock.activity_states[source] = {"entity_id": source, "state": "off", "attributes": {}}
        when = datetime.now(UTC) + timedelta(hours=2)
        mock.calendar_events[source] = [
            {"summary": "Example appointment", "start": {"dateTime": when.isoformat()}, "end": {"dateTime": (when + timedelta(hours=1)).isoformat()}}
        ]
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
            store = HouseholdStore(directory)
            house = store.load()
            house["surfaces"] = [{"id": "example_wall", "name": "Example wall", "profile": "wall", "person_id": None, "area_id": None, "audience": "everyone"}]
            house = store.save(house)
            app = create_app(settings)
            async with TestServer(app) as server, TestServer(build_app(str(server.make_url("")))) as ingress:
                inv = await collect_inventory(app[K_STATE].core)
                saved = empty(house["epoch"])
                choice = {"intent": "wanted", "sources": [source], "screens": ["example_wall"], "answers": {}, "permissions": {}}
                saved["choices"]["calendars"] = choice
                saved["verified"]["calendars"] = {"at": datetime.now(UTC).isoformat(), "signature": selection_signature(choice, inv)}
                store.write(store.readiness_path, saved)
                await asyncio.to_thread(exercise, str(ingress.make_url("/home_starter")))


if __name__ == "__main__":
    asyncio.run(main())
