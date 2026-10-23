"""Fictional loopback regression for polling, action locks and stale responses."""

import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from e2e_media_app import BASE_VIEW, PLAYER, PREFIX, STATIC
from playwright.sync_api import Error, expect, sync_playwright


def main():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path.removeprefix(PREFIX)
            if path == "media":
                content = (STATIC / "media.html").read_text().replace("<!--BASE-->", f'<base href="{PREFIX}">').encode()
                mime = "text/html"
            elif path.startswith("static/") and path[7:] in {"media-app.js", "media-app.css", "media.webmanifest", "routes.js", "icon.svg"}:
                content = (STATIC / path[7:]).read_bytes()
                mime = "text/javascript" if path.endswith(".js") else "text/css"
            else:
                content, mime = b'{"surfaces":[{"id":"panel","name":"Example screen","person_id":null}]}', "application/json"
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.end_headers()
            self.wfile.write(content)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    held, posts = [], []
    mode = {"hold": False, "post_hold": False, "failure": False, "occupied": False, "unauthorised": False}

    def view(url):
        data = copy.deepcopy(BASE_VIEW)
        data["person_id"] = parse_qs(urlsplit(url).query).get("person", [None])[0]
        data["players"].append({**PLAYER, "entity_id": "media_player.other", "player_id": "other", "name": "Example other room"})
        return data

    def reply(route, data, status=200):
        try:
            route.fulfill(status=status, content_type="application/json", body=json.dumps(data))
        except Error:
            pass  # Aborted stale GETs must never be replayed.

    def api(route):
        request = route.request
        data = view(request.url)
        if request.method == "POST":
            body = request.post_data_json
            posts.append(body)
            if mode["post_hold"]:
                held.append((route, data))
            elif mode["occupied"] and body["action"] == "play_item":
                reply(route, {"error": "This speaker session changed. Choose another speaker."}, 409)
            else:
                reply(route, data)
        elif mode["unauthorised"]:
            reply(route, {"error": "Sign in through Home Assistant."}, 403)
        elif mode["failure"]:
            reply(route, {"error": "The source is temporarily unavailable."}, 503)
        elif mode["hold"]:
            held.append((route, data))
        else:
            reply(route, data)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.add_init_script("""const interval=window.setInterval.bind(window),timeout=window.setTimeout.bind(window);
window.setInterval=(fn,ms,...args)=>ms===7000 ? (window.pollMedia=fn,0):interval(fn,ms,...args);
window.setTimeout=(fn,ms,...args)=>timeout(fn,ms===12000 ? 1200:ms,...args);""")
            page.route("**/api/listening/panel*", api)
            page.goto(f"http://127.0.0.1:{server.server_port}{PREFIX}media")
            choices = page.get_by_role("button", name="All collections", exact=True)
            expect(choices).to_be_enabled()
            mode["hold"] = True
            page.evaluate("window.pollMedia()")
            page.wait_for_timeout(100)
            expect(choices).to_be_enabled()
            expect(page.locator(".workspace")).to_have_attribute("aria-busy", "false")
            assert len(held) == 1
            for _ in range(3):
                page.evaluate("window.pollMedia()")
            assert len(held) == 1  # No overlapping polls.
            expect(page.get_by_role("status")).to_contain_text("Refresh took too long", timeout=3000)
            expect(choices).to_be_enabled()
            for stale in held:
                reply(*stale)
            held.clear()

            mode.update(hold=False, failure=True)
            page.evaluate("window.pollMedia()")
            expect(page.get_by_role("status")).to_contain_text("temporarily unavailable")
            expect(choices).to_be_enabled()
            mode.update(failure=False, hold=True)
            page.evaluate("window.pollMedia()")
            page.wait_for_timeout(100)
            stale = held.pop()
            mode["hold"] = False
            page.get_by_role("button", name="Example child", exact=True).click()
            expect(page.locator("#profile h1")).to_contain_text("Example child")
            reply(*stale)
            expect(page.locator("#profile h1")).to_contain_text("Example child")
            page.get_by_role("button", name="Example adult", exact=True).click()
            expect(choices).to_be_enabled()

            # A response arriving during typing must not replace the edited input.
            mode["hold"] = True
            page.locator("body").click(position={"x": 2, "y": 2})
            page.evaluate("window.pollMedia()")
            page.wait_for_timeout(100)
            search = page.get_by_role("searchbox", name="Search household audio")
            search.fill("Unsubmitted draft")
            mode["hold"] = False
            reply(*held.pop())
            expect(search).to_have_value("Unsubmitted draft")
            expect(search).to_be_focused()
            page.locator("body").click(position={"x": 2, "y": 2})

            # An action interrupts a read; double taps and keyboard submit cannot abort it.
            mode.update(hold=True, post_hold=True)
            page.evaluate("window.pollMedia()")
            page.wait_for_timeout(100)
            stale = held.pop()
            page.get_by_role("button", name="Save", exact=True).first.click()
            page.wait_for_timeout(100)
            assert len(posts) == 1
            page.get_by_role("button", name="Save", exact=True).first.dispatch_event("click")
            page.get_by_role("button", name="Example child", exact=True).dispatch_event("click")
            page.locator("form.search").dispatch_event("submit")
            page.evaluate("window.pollMedia()")
            assert len(posts) == 1
            expect(page.locator("#profile h1")).to_contain_text("Example adult")
            reply(*stale)
            expect(choices).to_be_disabled()
            mode.update(hold=False, post_hold=False)
            reply(*held.pop())
            expect(choices).to_be_enabled()

            # A room change wins over an older poll response.
            mode["hold"] = True
            page.locator("body").click(position={"x": 2, "y": 2})
            page.evaluate("window.pollMedia()")
            page.wait_for_timeout(100)
            stale = held.pop()
            mode["hold"] = False
            page.get_by_role("combobox", name="Choose a speaker").select_option("media_player.other")
            expect(choices).to_be_enabled()
            reply(*stale)
            expect(page.get_by_role("combobox", name="Choose a speaker")).to_have_value("media_player.other")

            # Last-known idle UI does not override a fresh server ownership rejection.
            mode["occupied"] = True
            before = len(posts)
            page.get_by_role("button", name="Play", exact=True).first.click()
            expect(page.get_by_role("status")).to_contain_text("session changed")
            assert len(posts) == before + 1
            mode.update(occupied=False, unauthorised=True)
            page.locator("body").click(position={"x": 2, "y": 2})
            page.evaluate("window.pollMedia()")
            expect(page.get_by_role("status")).to_contain_text("Sign in")
            assert not page.locator("#profile").inner_text()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("Media refresh checks passed: no poll lock, timeout/failure, stale profile/room reads, action race/repeated taps, ownership rejection and auth loss.")


if __name__ == "__main__":
    main()
