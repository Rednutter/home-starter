"""Isolated responsive Media UI acceptance; synthetic loopback service only."""

import argparse
import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "home_starter/server/homestarter/static"
PREFIX = "/api/hassio_ingress/fixture-media/"
PLAYER = {
    "entity_id": "media_player.fixture",
    "player_id": "fixture",
    "name": "Example room",
    "available": True,
    "single": True,
    "state": "idle",
    "features": [],
}
BASE_VIEW = {
    "epoch": 1,
    "profiles": [{"id": "one", "name": "Example adult"}, {"id": "two", "name": "Example child"}],
    "players": [PLAYER],
    "default_destination": PLAYER["entity_id"],
    "browse": True,
    "library": [{"id": "selection", "title": "Example <img onerror=bad> music", "kind": "track", "folder": False}],
    "favorites": [],
    "shared": [],
    "recent": [],
    "books": [],
    "channels": [{"id": "rain", "title": "Rain", "kind": "sound_effect", "category": "ambient", "folder": False}],
    "discovery": False,
    "discovery_issue": "Music discovery is temporarily unavailable.",
    "audiobooks": {"state": "not_connected", "message": "Your audiobook library is not connected yet."},
    "session": None,
    "delayed": None,
    "sleep": None,
}


def main(*, preview=False):
    view_base = copy.deepcopy(BASE_VIEW)
    if preview:
        view_base["library"][0]["title"] = "Example evening mix"
    calls = []
    allowed = True
    shared = False
    joined = False
    queued_count = 0
    revision_counter = 0
    owned = False
    confirmation = None
    station_recipe = None
    station_preview = None
    station_notice = None
    station_enabled = True
    bound = False
    search_entered, search_release, search_finished = threading.Event(), threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, value, content_type="application/json", status=200):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except ConnectionError:
                return  # A profile switch deliberately aborts its old metadata request.

        def do_GET(self):
            url = urlsplit(self.path)
            path = url.path.removeprefix(PREFIX)
            if path == "media":
                page = (STATIC / "media.html").read_text(encoding="utf-8").replace("<!--BASE-->", f'<base href="{PREFIX}">')
                if preview:
                    page = page.replace(
                        "<body>",
                        '<body><aside style="padding:10px;text-align:center;background:#34485b;color:white">'
                        "Local preview · Fictional data · No household connection</aside>",
                    )
                return self.reply(page.encode(), "text/html")
            if path.startswith("static/"):
                name = path[7:]
                if name not in {"media-app.js", "media-app.css", "media.webmanifest", "routes.js", "icon.svg"}:
                    return self.reply({}, status=404)
                mime = "text/javascript" if name.endswith(".js") else "text/css" if name.endswith(".css") else "application/json"
                return self.reply((STATIC / name).read_bytes(), mime)
            if path == "api/listening":
                return self.reply(
                    {"surfaces": [{"id": "panel", "name": "Example display", "person_id": "two" if bound else None}]}
                    if allowed
                    else {"error": "Sign in through Home Assistant."},
                    status=200 if allowed else 403,
                )
            if path == "api/listening/panel":
                if not allowed:
                    return self.reply({"error": "Sign in through Home Assistant."}, status=403)
                view = copy.deepcopy(view_base)
                person = parse_qs(url.query).get("person", [None])[0]
                if bound and person != "two":
                    return self.reply({"error": "This screen has a fixed listening profile."}, status=403)
                view["bound_profile"] = "two" if bound else None
                if bound:
                    view["profiles"] = [p for p in view["profiles"] if p["id"] == "two"]
                if parse_qs(url.query).get("query"):
                    view["search"] = {
                        "coverage": "Assigned catalogue sources only.",
                        "incomplete": True,
                        "issue": "One source is unavailable; other matches remain available.",
                        "sources": [],
                    }
                if parse_qs(url.query).get("query") == ["slow"]:
                    search_entered.set()
                    search_release.wait(4)
                view["person_id"] = person
                view["stations"] = {
                    "recipes": [station_recipe] if station_recipe and person == "one" else [],
                    "can_preview": station_enabled,
                    "issue": "Preview only; station playback is not connected.",
                    "coverage": "Synthetic single-source preview, not whole-catalogue access.",
                    "preview": station_preview if person == "one" else None,
                    "notice": station_notice if person == "one" else None,
                }
                if person == "two":
                    view["browse"] = False
                    view["library"] = []
                if person is None:
                    view["audiobooks"] = {"state": "choose_listener", "message": "Choose who is listening."}
                if shared:
                    view["players"][0].update(state="paused", features=["play_media"])
                    if view["library"]:
                        view["library"][0]["queueable"] = True
                    view["sessions"] = [
                        {
                            "player_id": PLAYER["player_id"],
                            "owner": "Example adult" if owned else "Other household member",
                            "owned": owned,
                            "joined": joined,
                            "can_join": not joined and not owned,
                            "can_add": joined or owned,
                            "can_next": joined or owned,
                            "can_edit": owned,
                            "can_takeover": not owned,
                            "revision": "queue-" + str(revision_counter),
                            "queue": [
                                {"title": "Existing <img onerror=bad> song", "current": True},
                                *({"title": "Added song", "current": False} for _ in range(queued_count)),
                            ],
                        }
                    ]
                    for i, row in enumerate(view["sessions"][0]["queue"]):
                        row.update(entry="fixture-row-" + str(i), remove=i > 0, up=i > 1, down=0 < i < queued_count)
                    view["takeover"] = confirmation
                result = self.reply(view)
                if parse_qs(url.query).get("query") == ["slow"]:
                    search_finished.set()
                return result
            self.reply({}, status=404)

        def do_POST(self):
            nonlocal joined, queued_count, revision_counter, owned, confirmation, station_recipe, station_preview, station_notice
            if urlsplit(self.path).path != PREFIX + "api/listening/panel":
                return self.reply({}, status=404)
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append({"body": body, "person": parse_qs(urlsplit(self.path).query).get("person", [None])[0]})
            action = body["action"]
            if action == "station_save":
                station_recipe = {"id": "fixture-station", **body["settings"]}
            elif action in {"station_preview", "station_refine"}:
                station_preview = {
                    "id": "fixture-preview",
                    "station": "fixture-station",
                    "state": "partial",
                    "coverage": "Synthetic configured source only.",
                    "partial_sources": False,
                    "items": [{"entry": "fixture-selection", "title": "Preview <img onerror=bad> track"}],
                }
            elif action == "station_feedback":
                station_notice = "Preview feedback saved; no playback changed."
            if action in {"queue_join", "queue_add", "queue_next", "queue_move", "queue_remove", "queue_takeover_prepare", "queue_takeover"}:
                if body.get("session") != "queue-" + str(revision_counter):
                    return self.reply({"error": "This listening session changed. Refresh, then join it again or choose another speaker."}, status=409)
                if action == "queue_join":
                    joined = True
                elif action == "queue_takeover_prepare":
                    confirmation = {"player_id": PLAYER["player_id"], "revision": "queue-" + str(revision_counter), "confirmation": "fixture-review"}
                else:
                    if action in {"queue_add", "queue_next"}:
                        queued_count += 1
                    elif action == "queue_remove":
                        queued_count -= 1
                    elif action == "queue_takeover":
                        assert body["confirmation"] == confirmation["confirmation"]
                        owned, joined, confirmation = True, False, None
                    revision_counter += 1
            self.do_GET()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        if preview:
            print(f"PREVIEW_URL=http://127.0.0.1:{server.server_port}{PREFIX}media", flush=True)
            thread.join()
            return
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width, height in [(1440, 900), (820, 1180), (390, 844)]:
                shared, joined, queued_count, revision_counter, owned, confirmation = False, False, 0, 0, False, None
                station_recipe, station_preview, station_notice, station_enabled = None, None, None, True
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error, failures=errors: failures.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}{PREFIX}media")
                expect(page.get_by_role("heading", name="House’s listening", exact=True)).to_be_visible()
                expect(page.get_by_text("Music discovery is temporarily unavailable.", exact=True)).to_be_visible()
                assert page.get_by_role("button", name="Surprise Me", exact=True).count() == 0
                assert page.locator("#library img").count() == 0
                assert "null" not in page.locator("body").inner_text()
                assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")
                previews = Path(".runtime/media-app-preview")
                previews.mkdir(parents=True, exist_ok=True)
                search_box = page.get_by_role("searchbox", name="Search household audio")
                assert search_box.bounding_box()["y"] < height
                assert search_box.bounding_box()["y"] < page.locator("#playing").bounding_box()["y"]
                for node in page.get_by_role("button").all():
                    if node.is_visible():
                        assert node.bounding_box()["height"] >= 44
                child_button = page.get_by_role("button", name="Example child", exact=True)
                child_button.focus()
                expect(child_button).to_be_in_viewport()
                page.screenshot(path=str(previews / f"synthetic-{width}.png"), full_page=True)
                before = len(calls)
                page.locator(".playback-options summary").click()
                page.get_by_role("combobox", name="Playback start", exact=True).select_option("300")
                expect(page.locator(".playback-options summary")).to_have_text("Starts in 5 minutes")
                expect(page.get_by_role("button", name="Start later", exact=True).first).to_be_visible()
                assert len(calls) == before
                page.get_by_role("combobox", name="Playback start", exact=True).select_option("0")
                expect(page.locator(".playback-options summary")).to_be_focused()
                expect(page.get_by_role("button", name="Play", exact=True).first).to_be_visible()
                page.get_by_role("button", name="Example child’s books", exact=True).click()
                expect(page.get_by_role("heading", name="Example child’s listening", exact=True)).to_be_visible()
                expect(page.get_by_text("Your audiobook library is not connected yet.", exact=True)).to_be_visible()
                assert len(calls) == before  # profile selection is never playback
                assert page.get_by_role("searchbox").count() == 0
                assert page.get_by_role("button", name="Create station recipe", exact=True).count() == 0
                page.get_by_role("button", name="Example adult", exact=True).click()
                expect(page.get_by_role("heading", name="Example adult’s listening", exact=True)).to_be_visible()
                page.get_by_role("searchbox", name="Search household audio").fill("example")
                search_button = page.get_by_role("button", name="Search", exact=True)
                search_button.focus()
                page.keyboard.press("Enter")
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                expect(search_button).to_be_focused()
                expect(page.get_by_role("heading", name="Search results", exact=True)).to_be_visible()
                expect(page.get_by_role("heading", name="Tracks", exact=True)).to_be_visible()
                assert page.locator("#library > section").first.get_by_role("heading", name="Tracks", exact=True).count() == 1
                page.screenshot(path=str(previews / f"synthetic-search-{width}.png"), full_page=True)
                page.locator(".search-health summary").click()
                expect(page.get_by_text("Assigned catalogue sources only.", exact=True)).to_be_visible()
                page.locator(".search-health summary").click()
                page.get_by_role("button", name="Play", exact=True).first.click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "play_item"
                assert calls[-1]["body"]["epoch"] == 1
                assert calls[-1]["person"] == "one"
                before = len(calls)
                page.get_by_role("button", name="Create station recipe", exact=True).click()
                page.get_by_role("textbox", name="Station name", exact=True).fill("Example station")
                page.get_by_role("textbox", name="Station seeds", exact=True).fill("Example artist")
                assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")
                page.get_by_role("button", name="Save station recipe", exact=True).click()
                expect(page.get_by_role("button", name="Preview new session", exact=True)).to_be_visible()
                assert calls[-1]["body"]["action"] == "station_save" and len(calls) == before + 1
                page.get_by_role("button", name="Preview new session", exact=True).click()
                expect(page.get_by_text("Preview <img onerror=bad> track", exact=True)).to_be_visible()
                assert page.locator("#library img").count() == 0
                page.get_by_role("combobox", name="Station feedback scope", exact=True).select_option("station")
                page.get_by_role("button", name="Never in previews", exact=True).click()
                expect(page.get_by_text("Preview feedback saved; no playback changed.", exact=True)).to_be_visible()
                assert calls[-1]["body"]["action"] == "station_feedback" and calls[-1]["body"]["settings"] == {"scope": "station"}
                page.get_by_role("button", name="Regenerate this preview", exact=True).click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "station_refine"
                assert all(call["body"]["action"].startswith("station_") for call in calls[before:])
                station_enabled = False
                page.get_by_role("button", name="All collections", exact=True).click()
                expect(page.get_by_role("button", name="Preview new session", exact=True)).to_be_disabled()
                shared = True
                page.get_by_role("button", name="All collections", exact=True).click()
                expect(page.get_by_text("Other household member owns this queue", exact=True)).to_be_visible()
                expect(page.get_by_role("button", name="Play", exact=True).first).to_be_disabled()
                assert page.locator("#playing img").count() == 0
                page.get_by_role("button", name="Join listening", exact=True).click()
                expect(page.get_by_role("button", name="Leave listening", exact=True)).to_be_visible()
                assert calls[-1]["body"]["action"] == "queue_join"
                assert calls[-1]["body"]["session"] == "queue-0"
                assert page.get_by_role("button", name="Stop", exact=True).count() == 0
                page.get_by_role("button", name="Add to queue", exact=True).click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "queue_add" and queued_count == 1
                queued_count += 1  # simulate a native/other-profile edit after the displayed snapshot
                revision_counter += 1
                page.get_by_role("button", name="Add to queue", exact=True).click()
                expect(page.get_by_role("status")).to_contain_text("This listening session changed.")
                before = len(calls)
                page.get_by_role("button", name="Retry", exact=True).click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert len(calls) == before  # retry refreshes; never repeats an uncertain append
                page.get_by_role("button", name="Play Next", exact=True).click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "queue_next"
                page.get_by_role("button", name="Review takeover", exact=True).click()
                expect(page.get_by_role("heading", name="Confirm queue takeover", exact=True)).to_be_visible()
                assert calls[-1]["body"]["action"] == "queue_takeover_prepare" and not owned
                page.get_by_role("button", name="Confirm takeover", exact=True).click()
                expect(page.get_by_text("Example adult owns this queue", exact=True)).to_be_visible()
                assert calls[-1]["body"]["confirmation"] == "fixture-review"
                page.get_by_role("button", name="Down", exact=True).nth(1).click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "queue_move" and calls[-1]["body"]["value"] == 1
                page.get_by_role("button", name="Remove", exact=True).last.click()
                page.wait_for_function("document.getElementById('notice').textContent === ''")
                assert calls[-1]["body"]["action"] == "queue_remove"
                search_entered.clear()
                search_release.clear()
                search_finished.clear()
                page.get_by_role("searchbox", name="Search household audio").fill("slow")
                page.get_by_role("button", name="Search", exact=True).click()
                assert search_entered.wait(2)
                expect(page.get_by_role("status")).to_contain_text("Searching your audio")
                expect(page.locator(".workspace")).to_have_attribute("aria-busy", "true")
                expect(page.get_by_role("button", name="Search", exact=True)).to_be_disabled()
                page.get_by_role("button", name="Example child", exact=True).click()
                expect(page.get_by_role("heading", name="Example child’s listening", exact=True)).to_be_visible()
                search_release.set()
                assert search_finished.wait(2)
                expect(page.get_by_role("heading", name="Example child’s listening", exact=True)).to_be_visible()
                assert "Example <img onerror=bad> music" not in page.locator("#library").inner_text()
                assert page.locator("body").evaluate("e=>e.scrollWidth<=innerWidth")
                move_calls = []
                move_view = copy.deepcopy(BASE_VIEW)
                move_view.update(
                    person_id="one",
                    session={"player_id": "fixture", "title": "Example queue"},
                    transfer={"source_entity": PLAYER["entity_id"], "targets": [{"entity_id": "media_player.other", "name": "Example other room"}]},
                )
                move_view["players"].append({**PLAYER, "entity_id": "media_player.other", "player_id": "other", "name": "Example other room"})

                def transfer_response(route, _request, *, move_calls=move_calls, move_view=move_view):
                    if route.request.method == "POST":
                        body = route.request.post_data_json
                        move_calls.append(body)
                        model = move_view["transfer"]
                        if body["action"] == "transfer_prepare":
                            model["plan"] = {
                                "source_entity": PLAYER["entity_id"],
                                "target_entity": "media_player.other",
                                "target_name": "Example other room",
                                "confirmation": "fixture-confirmation",
                            }
                        elif body["action"] == "transfer_confirm":
                            model["pending"] = True
                            model["notice"] = "The move is not confirmed. Check both speakers."
                            for p in move_view["players"]:
                                p["transfer_pending"] = True
                        elif body["action"] == "transfer_recheck":
                            model.update(pending=False, plan=None, targets=[], notice="Queue moved.")
                            move_view["session"]["player_id"] = "other"
                            move_view["default_destination"] = "media_player.other"
                            for p in move_view["players"]:
                                p["transfer_pending"] = False
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(move_view))

                page.route("**/api/listening/panel?*", transfer_response)
                page.get_by_role("button", name="Example adult", exact=True).click()
                page.get_by_role("button", name="Move to Example other room", exact=True).click()
                expect(page.get_by_role("heading", name="Confirm playback move", exact=True)).to_be_visible()
                page.screenshot(path=str(previews / f"synthetic-transfer-review-{width}.png"), full_page=True)
                assert move_calls[-1]["action"] == "transfer_prepare" and move_calls[-1]["target"] == "media_player.other"
                page.get_by_role("button", name="Confirm move", exact=True).click()
                expect(page.get_by_role("button", name="Check move", exact=True)).to_be_visible()
                assert [r["action"] for r in move_calls] == ["transfer_prepare", "transfer_confirm"]
                page.get_by_role("button", name="Check move", exact=True).click()
                expect(page.get_by_role("combobox", name="Choose a speaker", exact=True)).to_have_value("media_player.other")
                assert [r["action"] for r in move_calls] == ["transfer_prepare", "transfer_confirm", "transfer_recheck"]
                assert not errors, errors
                context.close()
            shared = False
            bound = True
            context = browser.new_context()
            context.add_init_script("try{localStorage.setItem('homeStarter.media.profile:panel','house')}catch{}")
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}{PREFIX}media")
            expect(page.get_by_role("heading", name="Example child’s listening", exact=True)).to_be_visible()
            assert page.get_by_role("button", name="House", exact=True).count() == 0
            assert page.get_by_role("button", name="Example adult", exact=True).count() == 0
            context.close()
            bound = False
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}{PREFIX}media")
            expect(page.get_by_role("heading", name="House’s listening", exact=True)).to_be_visible()
            allowed = False
            page.get_by_role("button", name="All collections", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("Sign in through Home Assistant.")
            assert "Example child" not in page.locator("body").inner_text()
            assert not page.locator("#access").inner_text()
            context.close()
            context = browser.new_context()
            page = context.new_page()
            page.goto(f"http://127.0.0.1:{server.server_port}{PREFIX}media")
            expect(page.get_by_role("status")).to_contain_text("Sign in through Home Assistant.")
            assert "Example child" not in page.locator("body").inner_text()
            assert not page.locator("#profile").inner_text()
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print(
        "Media app synthetic acceptance passed: desktop/tablet/phone, profiles, protected queue/join/add/stale refresh, "
        "no automatic playback, escaping and auth failures."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="Keep a fictional, loopback-only browser preview running; no HA access.")
    main(preview=parser.parse_args().preview)
