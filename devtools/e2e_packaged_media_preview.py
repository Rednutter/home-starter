"""Render the packaged production adapter against fictional, isolated state."""

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "home_starter/server"))
from homestarter import media_preview  # noqa: E402
from homestarter import server as app_server  # noqa: E402
from test_media_preview import parent_for, preview_state  # noqa: E402


async def run(candidate, output_path=".runtime/packaged-preview-acceptance"):
    output = ROOT / output_path
    output.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".runtime", prefix="packaged-preview-test-") as temp, pytest.MonkeyPatch.context() as patch:
        state, surface, _ = preview_state.__wrapped__(Path(temp), patch)
        assets = Path(candidate).resolve() / "home_starter/server/homestarter/static/media-preview"
        patch.setattr(media_preview, "ASSET_ROOT", assets)
        state.media_preview = media_preview.PreviewService(state)
        original = state.media_preview.open

        async def open_fixture(caller, surface=None):
            identity, result = await original(caller, surface)
            # Synthetic pixel only, never a fabricated real artist portrait.
            pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=")
            state.media_preview.sessions[identity]["metadata"].art_read = AsyncMock(return_value=("image/png", pixel))
            return identity, result

        state.media_preview.open = open_fixture
        app = parent_for(state, surface)
        phase = {"state": "idle", "owner": None, "active": False, "revision": 0, "timer": 0}
        phase.update(members=["example-player"], group_pending=None, desired=None, second_occupied=False)
        commands = []

        async def view(caller, surface, person, folder=None, query=None):
            owned = phase["active"] and phase["owner"] == person
            room = {
                "entity_id": "media_player.example",
                "player_id": "example-player",
                "name": "Example room",
                "available": True,
                "single": True,
                "state": phase["state"],
                "features": ["pause", "next_previous", "volume_set", "play_media", "set_members"],
                "can_group_with": ["second-player"],
                "managed_group": len(phase["members"]) > 1,
            }
            second = {
                **room,
                "entity_id": "media_player.second",
                "player_id": "second-player",
                "name": "Second room",
                "managed_group": False,
                "can_group_with": ["example-player"],
                "single": len(phase["members"]) == 1,
                "group_parent": "example-player" if len(phase["members"]) > 1 else None,
                "state": phase["state"] if len(phase["members"]) > 1 else "playing" if phase["second_occupied"] else "idle",
            }
            return {
                "epoch": state.household.load()["epoch"],
                "person_id": person,
                "players": [room, second],
                "profiles": [{"id": "one", "name": "Example One"}],
                "default_destination": room["entity_id"],
                "sessions": [
                    {
                        "player_id": "example-player",
                        "owner": "House" if phase["active"] else None,
                        "owned": owned,
                        "can_add": owned,
                        "can_next": owned,
                        "can_edit": owned,
                        "source_scoped": True,
                        "revision": "r" + str(phase["revision"]),
                        "queue": [],
                    }
                ],
                "transport": [
                    {
                        "player_id": "example-player",
                        "title": "Example track",
                        "revision": "t" + str(phase["revision"]),
                        "actions": ["stop", "volume", "play" if phase["state"] == "paused" else "pause"],
                    }
                ]
                if phase["active"]
                else [],
                "session": {"title": "Example track", "player_id": "example-player"} if owned else None,
                "sleep": {"at": 1} if phase["timer"] else None,
                "grouping": {
                    "available": True,
                    "groups": [{"leader": "example-player", "members": phase["members"]}] if len(phase["members"]) > 1 else [],
                    "pending": phase["group_pending"],
                    "reason": "Review the native synchronised speaker group.",
                },
                "library": [],
                "favorites": [],
                "recent": [],
            }

        async def command(caller, surface, person, body):
            print("ACTION", body.get("action"), flush=True)
            assert body["epoch"] == state.household.load()["epoch"]
            if body["action"] in {"play", "pause", "stop", "volume"}:
                assert body["session"] == "t" + str(phase["revision"])
            commands.append({"profile": person, **body})
            if body["action"] == "play_item":
                phase.update(state="playing", owner=person, active=True)
            if body["action"] == "pause":
                phase["state"] = "paused"
            if body["action"] == "play":
                phase["state"] = "playing"
            if body["action"] == "stop":
                phase["state"] = "idle"
                phase["active"] = False
            if body["action"] == "sleep":
                phase["timer"] = body["value"]
            if body["action"] == "group_prepare":
                selected = body["settings"]["members"]
                assert "media_player.example" in selected
                phase["desired"] = ["example-player", *(["second-player"] if "media_player.second" in selected else [])]
                phase["group_pending"] = {
                    "leader": "example-player",
                    "phase": "prepared",
                    "confirmation": "fixture-group-confirmation",
                    "members": ["Example room", *(["Second room"] if len(phase["desired"]) > 1 else [])],
                    "occupied": ["Second room"] if phase["second_occupied"] else [],
                    "removed": ["Second room"] if len(phase["members"]) > len(phase["desired"]) else [],
                    "start": {"title": "Example track"} if body.get("item") else None,
                }
            if body["action"] == "group_cancel":
                phase["group_pending"] = None
            if body["action"] == "group_confirm":
                assert body["confirmation"] == phase["group_pending"]["confirmation"]
                if phase["group_pending"]["occupied"]:
                    assert body.get("value") == "replace"
                if phase["group_pending"].get("start"):
                    assert not phase["active"] and not phase["second_occupied"]
                    phase.update(state="playing", owner=person, active=True)
                phase["members"] = phase["desired"]
                phase["group_pending"] = None
                phase["second_occupied"] = False
            phase["revision"] += 1

        state.listening.view = AsyncMock(side_effect=view)
        state.listening.action = AsyncMock(side_effect=command)
        app.router.add_get("/media", app_server.media_app)
        app.router.add_get("/api/listening/{surface}", app_server.api_listening)
        app.router.add_post("/api/listening/{surface}", app_server.api_listening)
        async with TestServer(app) as server, async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            origin = str(server.make_url("")).rstrip("/")
            context = await browser.new_context(extra_http_headers={"X-Remote-User-Id": "example-admin"}, viewport={"width": 1440, "height": 1000})
            page = await context.new_page()
            page.set_default_timeout(10000)
            await page.add_init_script(
                "window.previewCspViolations=[]; document.addEventListener('securitypolicyviolation',e=>"
                "window.previewCspViolations.push({directive:e.effectiveDirective,blocked:e.blockedURI}));"
            )
            errors, external, posts, unexpected = [], [], [], []
            page.on("pageerror", lambda error: errors.append(str(error)))

            async def response_body(response):
                if response.url.endswith("/read"):
                    data = await response.json()
                    value = data.get("result")
                    print(
                        "RESULT",
                        response.request.post_data_json.get("command"),
                        response.status,
                        "items=" + str(len(value)) if isinstance(value, list) else type(value).__name__,
                        flush=True,
                    )

            page.on("response", response_body)
            page.on("response", lambda response: print("HTTP", response.status, response.url.removeprefix(origin)) if response.status >= 400 else None)

            async def guard(route):
                request = route.request
                if not request.url.startswith((origin + "/audio", origin + "/api/listening", origin + "/media")):
                    external.append(True)
                    await route.abort()
                    return
                if request.method == "POST":
                    body = request.post_data_json
                    if request.url.startswith(origin + "/audio/read"):
                        posts.append(body.get("command"))
                    if not request.url.startswith((origin + "/audio/read", origin + "/audio/select", origin + "/api/listening")):
                        unexpected.append(True)
                await route.continue_()

            await page.route("**/*", guard)
            loaded = await page.goto(origin + "/media#/artists")
            try:
                await expect(page.locator(".ed-card__title")).to_have_count(1, timeout=15000)
            except AssertionError:
                print(
                    json.dumps(
                        {
                            "entry_status": loaded.status,
                            "errors": errors,
                            "external_count": len(external),
                            "posts": posts,
                            "csp": await page.evaluate("window.previewCspViolations"),
                            "geometry": await page.locator(".native-library").evaluate(
                                "(e)=>({h:e.clientHeight,w:e.clientWidth,scroll:e.scrollHeight,html:e.innerHTML.slice(-1800)})"
                            ),
                            "body": (await page.locator("body").inner_text())[:1400],
                        }
                    )
                )
                raise
            await expect(page.get_by_text("Example artist", exact=True)).to_be_visible()
            await page.wait_for_function("document.querySelector('.ed-card img')?.naturalWidth > 0")
            for button in await page.locator(".ed-card button").all():
                await expect(button).to_be_disabled()
            await page.get_by_text("Example artist", exact=True).click()
            await expect(page.locator("#playbutton button").first).to_be_disabled()
            await page.screenshot(path=str(output / "detail-debug.png"))
            await page.get_by_text("Example album", exact=True).click()
            await page.get_by_text("Example track", exact=True).click()
            await expect(page.locator(".household-item-actions")).to_contain_text("Example track")
            print("STEP track selected", flush=True)
            # Repeated taps during selection are coalesced before any real action.
            play = page.get_by_role("button", name="Play selection", exact=True)
            await play.evaluate("(e)=>{e.click();e.click();}")
            print("STEP play tapped", flush=True)
            await expect(page.locator(".persistent-player")).to_contain_text("Example track")
            assert sum(c["action"] == "play_item" for c in commands) == 1
            await page.locator(".persistent-player").get_by_role("button", name="Pause", exact=True).click()
            await expect(page.locator(".persistent-player")).to_contain_text("paused")
            await page.get_by_role("button", name="Add to queue", exact=True).click()
            await expect(play).to_be_enabled()
            assert any(c["action"] == "queue_add" and c.get("session") for c in commands)
            await page.locator(".outputs").click()
            await page.get_by_label("Sleep timer", exact=True).select_option("900")
            await expect(page.get_by_label("Sleep timer", exact=True)).to_be_enabled()
            assert any(c["action"] == "sleep" and c["value"] == 900 for c in commands)
            second = page.get_by_role("checkbox", name="Second room", exact=False)
            count = len(commands)
            await second.check()
            await expect(second).to_be_checked()
            assert len(commands) == count

            # A delayed review response cannot be double-tapped or change profile.
            review_started, review_release = asyncio.Event(), asyncio.Event()

            async def delayed_review(route):
                if route.request.method == "POST" and route.request.post_data_json.get("action") == "group_prepare":
                    review_started.set()
                    await review_release.wait()
                await route.continue_()

            await page.route("**/api/listening/**", delayed_review)
            await page.get_by_role("button", name="Review speaker group", exact=True).click()
            await asyncio.wait_for(review_started.wait(), 5)
            await expect(page.locator("#preview-profile")).to_be_disabled()
            await expect(second).to_be_disabled()
            assert len(commands) == count
            review_release.set()
            await expect(page.get_by_role("region", name="Speaker group review")).to_be_visible()
            await page.unroute("**/api/listening/**", delayed_review)
            await page.get_by_role("button", name="Cancel group change", exact=True).click()
            await expect(page.get_by_role("region", name="Speaker group review")).to_have_count(0)
            await expect(second).not_to_be_checked()

            phase["second_occupied"] = True
            await second.check()
            await page.get_by_role("button", name="Review speaker group", exact=True).click()
            await expect(page.get_by_role("button", name="Confirm speaker group", exact=True)).to_be_disabled()
            await page.get_by_role("checkbox", name="Replace audio in these occupied speakers", exact=True).check()
            await expect(page.get_by_role("button", name="Confirm speaker group", exact=True)).to_be_enabled()
            group_geometry = []
            for size_name, width, height in [("phone", 390, 844), ("tablet", 1024, 768), ("desktop", 1440, 1000)]:
                await page.set_viewport_size({"width": width, "height": height})
                confirm_button = page.get_by_role("button", name="Confirm speaker group", exact=True)
                await confirm_button.scroll_into_view_if_needed()
                box = await confirm_button.bounding_box()
                panel = await page.locator(".household-drawer").bounding_box()
                assert box["height"] >= 44 and panel["x"] >= 0 and panel["x"] + panel["width"] <= width + 1
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
                group_geometry.append({"name": size_name, "button_height": box["height"], "panel_width": panel["width"]})
                await page.screenshot(path=str(output / ("group-review-" + size_name + ".png")))
            await page.get_by_role("button", name="Confirm speaker group", exact=True).evaluate("e=>{e.click();e.click();}")
            await expect(page.get_by_role("region", name="Speaker group review")).to_have_count(0)
            assert sum(c["action"] == "group_confirm" for c in commands) == 1
            assert phase["owner"] is None and phase["timer"] == 900
            await expect(second).to_be_checked()
            await second.uncheck()
            await page.get_by_role("button", name="Review speaker group", exact=True).click()
            await expect(page.get_by_role("region", name="Speaker group review")).to_contain_text("Speakers leaving: Second room")
            await page.get_by_role("button", name="Confirm speaker group", exact=True).click()
            await expect(page.get_by_role("region", name="Speaker group review")).to_have_count(0)
            assert phase["members"] == ["example-player"]
            assert sum(c["action"] == "play_item" for c in commands) == 1
            await page.get_by_role("button", name="Close speakers and queue", exact=True).click()

            await page.locator('.library-rail nav a[href="#/artists"]').click()
            await expect(page).to_have_url(origin + "/media#/artists")
            await expect(page.locator(".ed-card__title")).to_have_count(1)
            await page.locator("#preview-profile").select_option("one")
            await expect(page.locator(".ed-card__title")).to_have_count(0)
            await page.locator(".persistent-player").get_by_role("button", name="Resume", exact=True).click()
            await expect(page.locator(".persistent-player")).to_contain_text("playing")
            await page.locator(".persistent-player").get_by_role("button", name="Pause", exact=True).click()
            await expect(page.locator(".persistent-player")).to_contain_text("paused")
            assert phase["owner"] is None and phase["timer"] == 900
            await page.locator("#preview-profile").select_option("house")
            await expect(page.locator(".ed-card__title")).to_have_count(1)

            # Lost response after execution is inspected with GET, never replayed.
            async def uncertain(route):
                if route.request.method == "POST" and route.request.post_data_json.get("action") == "stop":
                    await command("example-admin", "shared", None, route.request.post_data_json)
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/api/listening/**", uncertain)
            await page.locator(".persistent-player").get_by_role("button", name="Stop", exact=True).click()
            await expect(page.get_by_role("status").filter(has_text="not been confirmed")).to_be_visible()
            await expect(page.locator(".persistent-player")).to_contain_text("idle")
            assert sum(c["action"] == "stop" for c in commands) == 1
            await page.unroute("**/api/listening/**", uncertain)
            assert [c["action"] for c in commands if c["profile"] == "one"] == ["play", "pause"]
            await page.locator('.library-rail nav a[href="#/artists"]').click()
            await expect(page.locator(".ed-card__title")).to_have_count(1)
            command_count = len(commands)
            await page.locator("#preview-profile").select_option("one")
            await expect(page.locator(".ed-card__title")).to_have_count(0)
            await page.locator("#preview-profile").select_option("house")
            await expect(page.locator(".ed-card__title")).to_have_count(1)
            assert len(commands) == command_count
            # Idle multi-room Play prepares a review; only confirmation requests one group start.
            await page.locator(".outputs").click()
            await second.check()
            await page.get_by_role("button", name="Close speakers and queue", exact=True).click()
            await page.locator('.library-rail nav a[href="#/artists"]').click()
            await page.get_by_text("Example artist", exact=True).click()
            await page.get_by_text("Example album", exact=True).click()
            await page.get_by_text("Example track", exact=True).click()
            play_count = sum(c["action"] == "play_item" for c in commands)
            await page.get_by_role("button", name="Play selection", exact=True).evaluate("e=>{e.click();e.click();}")
            await expect(page.get_by_role("button", name="Confirm group and play", exact=True)).to_be_visible()
            assert not phase["active"]
            assert sum(c["action"] == "play_item" for c in commands) == play_count
            await page.get_by_role("button", name="Cancel group change", exact=True).click()
            await expect(page.get_by_role("region", name="Speaker group review")).to_have_count(0)
            assert not phase["active"]
            await second.check()
            await page.get_by_role("button", name="Close speakers and queue", exact=True).click()
            await page.get_by_role("button", name="Play selection", exact=True).click()
            await expect(page.get_by_role("button", name="Confirm group and play", exact=True)).to_be_visible()
            await page.screenshot(path=str(output / "idle-start-review.png"))
            confirms = sum(c["action"] == "group_confirm" for c in commands)
            await page.get_by_role("button", name="Confirm group and play", exact=True).evaluate("e=>{e.click();e.click();}")
            await expect(page.get_by_role("region", name="Speaker group review")).to_have_count(0)
            assert phase["active"] and phase["members"] == ["example-player", "second-player"]
            assert sum(c["action"] == "group_confirm" for c in commands) == confirms + 1
            assert sum(c["action"] == "play_item" for c in commands) == play_count
            await page.get_by_role("button", name="Close speakers and queue", exact=True).click()
            await page.locator('.library-rail nav a[href="#/artists"]').click()
            geometry = []
            for name, width, height in [("desktop", 1440, 1000), ("tablet", 1024, 768), ("phone", 390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await expect(page.locator(".native-library [role=progressbar]").first).to_be_hidden()
                size = await page.evaluate("({w:innerWidth,h:innerHeight,sw:document.documentElement.scrollWidth,sh:document.documentElement.scrollHeight})")
                assert size["sw"] <= width + 1 and size["sh"] <= height + 1, size
                geometry.append({"name": name, **size})
                await page.screenshot(path=str(output / (name + ".png")))
            assert not external and not errors and not unexpected
            violations = await page.evaluate("window.previewCspViolations")
            assert not violations, violations
            assert not any(name.startswith(("players/", "player_queues/", "homestarter/")) for name in posts)
            state.music_runtime.control.assert_not_awaited()
            result = {
                "candidate": str(Path(candidate).name),
                "packaged_assets_and_art": True,
                "native_navigation_profile_isolation": True,
                "viewports": geometry,
                "group_review_viewports": group_geometry,
                "idle_group_start_review_cancel_confirm": True,
                "page_errors": errors,
                "external_requests": len(external),
                "mocked_household_actions": [c["action"] for c in commands],
                "native_control_requests": 0,
                "csp_violations": violations,
                "real_household_test": False,
            }
            (output / "result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result))
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate")
    parser.add_argument("--output", default=".runtime/packaged-preview-acceptance")
    args = parser.parse_args()
    asyncio.run(run(args.candidate, args.output))
