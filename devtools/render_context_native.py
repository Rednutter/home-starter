"""Eight real native HA renders using synthetic context and a fixture-only clock.

Only the disposable Core at loopback:18123 is accepted. No household endpoints.
The generated dashboard remains fixed while owned state changes between examples.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp
from context_scenarios import scenarios
from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:18123"
PATH = "home-starter-context-fixture"
SHOTS = Path("screens/context-native")


async def prepare():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter import context
    from homestarter.household import empty_household
    from homestarter.surfaces import generate

    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": "Bearer " + credentials["token"]}
        async with session.get(BASE + "/api/config", headers=headers) as response:
            authorized = response.status == 200
        if not authorized:
            async with session.post(
                BASE + "/auth/login_flow", json={"client_id": BASE + "/", "handler": ["homeassistant", None], "redirect_uri": BASE + "/?auth_callback=1"}
            ) as response:
                flow = await response.json()
            async with session.post(
                BASE + "/auth/login_flow/" + flow["flow_id"],
                json={"client_id": BASE + "/", "username": credentials["username"], "password": credentials["password"]},
            ) as response:
                login = await response.json()
            assert login["type"] == "create_entry", "Disposable fixture login failed"
            async with session.post(
                BASE + "/auth/token", data={"grant_type": "authorization_code", "code": login["result"], "client_id": BASE + "/"}
            ) as response:
                credentials["token"] = (await response.json())["access_token"]
            Path("screens/v3-core-credentials.json").write_text(json.dumps(credentials))
            Path("screens/v3-core-token.txt").write_text(credentials["token"])
        headers = {"Authorization": "Bearer " + credentials["token"]}
        house = empty_household()
        surface = {"id": "context_fixture", "name": "Household context examples", "profile": "wall", "person_id": None, "area_id": None, "audience": "everyone"}
        house["surfaces"] = [surface]
        generated = generate(house, surface, [], [])
        entity = context.entity_id(surface["id"])
        config = generated["config"]
        # Test clock only: production keeps HA now(), examples vary a synthetic time.
        config["views"][0]["sections"][0]["cards"][1]["content"] = (
            "## {{ state_attr('" + entity + "', 'example_clock') }}\n{{ state_attr('" + entity + "', 'example_date') }}"
        )
        async with session.ws_connect(BASE.replace("http", "ws") + "/api/websocket") as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": credentials["token"]})
            assert (await ws.receive_json())["type"] == "auth_ok"
            number = 0

            async def command(kind, **data):
                nonlocal number
                number += 1
                await ws.send_json({"id": number, "type": kind, **data})
                while True:
                    result = await ws.receive_json()
                    if result.get("id") == number:
                        assert result.get("success"), "Native fixture command failed"
                        return result.get("result")

            dashboards = await command("lovelace/dashboards/list")
            if not any(d["url_path"] == PATH for d in dashboards):
                await command("lovelace/dashboards/create", url_path=PATH, title="Context examples", require_admin=True, show_in_sidebar=True)
            await command("lovelace/config/save", url_path=PATH, config=config)
            assert await command("lovelace/config", url_path=PATH, force=True) == config
    return credentials, entity


def exercise(credentials, entity):
    import urllib.request

    from homestarter import context

    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, color_scheme="dark")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE)
        page.get_by_label("Username", exact=True).fill(credentials["username"])
        page.get_by_label("Password", exact=True).fill(credentials["password"])
        page.get_by_role("button", name="Log in", exact=True).click()
        expect(page.get_by_role("button", name="Sidebar toggle", exact=True)).to_be_visible(timeout=30000)
        page.goto(BASE + "/" + PATH + "/home")
        expect(page.locator("hui-sections-view")).to_be_visible(timeout=30000)
        for example in scenarios():
            events, invalid = context.parse_events(example["events"], "synthetic-source", "Australia/Sydney")
            assert invalid == 0
            settings = context.empty()
            if example.get("rule"):
                settings["rules"] = [
                    {"id": "example", "text": "Required activity kit", "people": ["alex"], "start": "2026-06-01", "end": "2026-06-30", "weekdays": [0]}
                ]
                settings["events"][events[0]["key"]] = {
                    "people": ["alex"],
                    "travel_minutes": 16,
                    "buffer_minutes": 8,
                    "round_minutes": 5,
                    "routine_time": "08:05",
                }
            data = context.build(events, example["now"], "Australia/Sydney", settings, {"alex": "Alex"})
            if example.get("status"):
                data.update(
                    near=example["status"],
                    ahead="Upcoming calendar context unavailable" if "unavailable" in example["status"] else "Choose and verify a consolidated calendar",
                )
            actual_now = datetime.now(UTC)
            attrs = {k: data[k] for k in ("near", "ahead", "phase", "today_count", "ahead_count")}
            attrs.update(
                checked_at=actual_now.isoformat(),
                valid_until=(actual_now + timedelta(seconds=150)).isoformat(),
                example_clock=example["now"].strftime("%H:%M"),
                example_date=example["now"].strftime("%A %d %B") + " · Fictional example",
            )
            payload = json.dumps({"state": "current", "attributes": attrs}).encode()
            req = urllib.request.Request(  # noqa: S310 -- hardcoded disposable loopback Core
                BASE + "/api/states/" + entity, data=payload, headers={"Authorization": "Bearer " + credentials["token"], "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as response:  # noqa: S310 -- fixed disposable loopback Core
                assert response.status in (200, 201)
            marker = (
                example["status"]
                if example.get("status")
                else "Required activity kit"
                if example.get("rule")
                else "No more scheduled today"
                if example["id"] == "evening-finished"
                else "Afternoon appointment"
                if example["id"] == "quiet-morning"
                else "Evening rehearsal"
                if example["id"] == "daytime"
                else "Training"
                if example["id"] == "afternoon"
                else "School planning evening"
            )
            expect(page.locator("hui-markdown-card").filter(has_text=marker).first).to_be_visible(timeout=20000)
            assert page.locator("hui-error-card").count() == 0
            assert page.locator("hui-sections-view").evaluate("el => el.scrollWidth <= el.clientWidth")
            page.screenshot(path=str(SHOTS / (example["id"] + ".png")), animations="disabled")
            if example["id"] in ("busy-morning", "quiet-morning"):
                page.set_viewport_size({"width": 1280, "height": 720})
                page.screenshot(path=str(SHOTS / (example["id"] + "-1280.png")), animations="disabled")
                page.set_viewport_size({"width": 1920, "height": 1080})
            print(example["id"], "native HA rendering and state update: PASS")
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    credentials, entity = asyncio.run(prepare())
    exercise(credentials, entity)
