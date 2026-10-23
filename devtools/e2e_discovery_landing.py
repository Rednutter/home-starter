"""Production discovery cards against isolated fictional MA adapters only."""

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
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "home_starter/server")]
from homestarter import media_preview  # noqa: E402
from homestarter import server as app_server  # noqa: E402
from homestarter.discovery_seeds import AUSTRALIAN_SEEDS, RADIO_SEEDS  # noqa: E402
from test_media_preview import parent_for, preview_state  # noqa: E402


async def run():
    output = ROOT / ".runtime/discovery-browser"
    output.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=ROOT / ".runtime") as temp, pytest.MonkeyPatch.context() as patch:
        state, surface, _ = preview_state.__wrapped__(Path(temp), patch)
        patch.setattr(media_preview, "ASSET_ROOT", ROOT / "home_starter/server/homestarter/static/media-preview")
        original = state.music_runtime.command
        state.filters.extend(["radio", "pod"])

        def record(identity, name, kind, provider):
            return {
                "item_id": identity,
                "uri": provider + "://" + kind + "/" + identity,
                "provider": provider,
                "name": name,
                "media_type": kind,
                "provider_mappings": [
                    {
                        "provider_instance": provider,
                        "provider_domain": "radiobrowser" if kind == "radio" else "itunes_podcasts",
                        "item_id": identity,
                        "available": True,
                    }
                ],
                "metadata": {
                    "explicit": False,
                    "description_language": "en",
                    "images": [{"type": "thumb", "provider": "builtin", "path": "https://is1-ssl.mzstatic.com/fictional-cover.png", "proxy_id": "a" * 64}],
                },
            }

        async def command(endpoint, connection, name, **args):
            if name == "providers":
                return [
                    *await original(endpoint, connection, name, **args),
                    *[
                        {"instance_id": key, "domain": domain, "type": "music", "available": True, "supported_features": ["search", "browse"]}
                        for key, domain in [("radio", "radiobrowser"), ("pod", "itunes_podcasts")]
                    ],
                ]
            if name == "music/browse" and args["path"].startswith("radio:"):
                raise RuntimeError("Synthetic directory browse failure")
            if name == "music/search":
                await asyncio.sleep(0.05)
                seed = next((s for s in (*RADIO_SEEDS, *AUSTRALIAN_SEEDS) if s[0] == args["search_query"]), None)
                return {"radios": [record(seed[1], "Example " + seed[0], "radio", "radio")] if seed else []}
            if name == "music/recommendations/items":
                return [record("one", "Example English show", "podcast", "pod"), record("two", "Second English show", "podcast", "pod")]
            return await original(endpoint, connection, name, **args)

        state.music_runtime.command = command

        async def view(caller, surface, person, folder=None, query=None):
            return {
                "epoch": state.household.load()["epoch"],
                "person_id": person,
                "browse": True,
                "players": [],
                "books": [],
                "channels": [{"id": "example-rain", "title": "Example rain", "category": "ambient"}],
                "library": [],
                "profiles": [],
            }

        state.listening.view = AsyncMock(side_effect=view)
        state.media_preview = media_preview.PreviewService(state)
        opened = state.media_preview.open

        async def open_fixture(caller, surface=None):
            identity, result = await opened(caller, surface)
            metadata = state.media_preview.sessions[identity]["metadata"]
            metadata.region = {"name": "Albury-Wodonga"}
            pixel = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a1ZkAAAAASUVORK5CYII=")
            metadata.art_read = AsyncMock(return_value=("image/png", pixel))
            return identity, result

        state.media_preview.open = open_fixture
        app = parent_for(state, surface)
        app.router.add_get("/api/listening/{surface}", app_server.api_listening)
        async with TestServer(app) as server, async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(extra_http_headers={"X-Remote-User-Id": "example-admin"}, viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(10000)
            errors, writes = [], []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: writes.append(request.url) if request.method == "POST" and not request.url.endswith("/read") else None)
            await page.goto(str(server.make_url("/audio/#/discover-radio")))
            await expect(page.locator(".discovery-grid .ed-card")).to_have_count(10)
            await expect(page.get_by_role("heading", name="Around the Border")).to_be_visible()
            await expect(page.get_by_role("heading", name="Across Australia")).to_be_visible()
            await expect(page.locator(".discovery-grid .ed-card__select").first).to_be_hidden()
            await page.wait_for_function("document.querySelector('.discovery-grid img')?.naturalWidth > 0")
            old_art = await page.locator(".discovery-grid img").first.get_attribute("src")
            await page.locator(".library-rail select").select_option("one")
            await expect(page.locator(".discovery-grid .ed-card")).to_have_count(10)
            assert await page.locator(".discovery-grid img").first.get_attribute("src") != old_art
            response = await page.request.get(old_art)
            assert response.status == 404
            await page.locator('.library-rail nav a[href="#/find-podcasts"]').click()
            await expect(page.locator(".discovery-grid .ed-card")).to_have_count(2)
            await expect(page.get_by_text("Example English show", exact=True)).to_be_visible()
            await page.locator('.library-rail nav a[href="#/ambient"]').click()
            await expect(page.get_by_text("Example rain", exact=True)).to_be_visible()
            await expect(page.locator(".discovery-grid .ed-card")).to_have_count(1)
            for width, height in [(1440, 1000), (1024, 768), (390, 844)]:
                await page.set_viewport_size({"width": width, "height": height})
                await page.locator('.library-rail nav a[href="#/discover-radio"]').click()
                await expect(page.locator(".discovery-grid .ed-card")).to_have_count(10)
                assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth+1 && document.documentElement.scrollHeight<=innerHeight+1")
                await page.screenshot(path=str(output / f"radio-{width}.png"))
            assert not errors and not writes, (errors, writes)
            state.music_runtime.control.assert_not_awaited()
            print(
                json.dumps(
                    {
                        "auto_radio": 10,
                        "auto_podcasts": 2,
                        "ambient_cards": 1,
                        "profile_art_revoked": True,
                        "viewports": [1440, 1024, 390],
                        "unexpected_writes": writes,
                        "page_errors": errors,
                        "physical_acceptance": False,
                    }
                )
            )
            await browser.close()


if __name__ == "__main__":
    asyncio.run(run())
