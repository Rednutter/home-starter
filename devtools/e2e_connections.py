"""Isolated browser acceptance for connection recovery and calendar source previews."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "home_starter/server/homestarter/static"
HTML = """<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="/styles.css"><main id="fixture"></main><script type="module">
import { connectionSetup } from '/connections.js';
const h = (tag, attrs={}, ...children) => {
 const node=document.createElement(tag);
 for (const [key,value] of Object.entries(attrs)) {
  if (typeof value === 'function') node[key]=value;
  else if (key === 'class') node.className=value;
  else if (key in node) node[key]=value;
  else node.setAttribute(key,value);
 }
 for (const child of children.flat(Infinity)) if (child!==false && child!=null) node.append(child);
 return node;
};
const api=async (url,options) => {const response=await fetch('/'+url,options); return response.json();};
const navigateHA=() => { fetch('/fixture/return',{method:'POST'}).then(()=>window.dispatchEvent(new Event('focus'))); };
document.getElementById('fixture').append(connectionSetup({h,api,navigateHA}));
</script>"""


def main():
    modes = {}
    authenticated = False
    revision = 0
    radio_selected = {"listnr:example"}
    local_consent = False

    def media_payload():
        return {
            "engine": {"policy": [], "autoplay": "similar"},
            "catalogue": {
                "epoch": 0,
                "ready": len(radio_selected),
                "selected": len(radio_selected),
                "discovered": 2,
                "local_lookup_allowed": local_consent,
                "local_lookup_state": "connected" if local_consent else "ready_for_consent",
                "items": [
                    {"id": "listnr:example", "name": "Example radio", "category": "radio", "selected": "listnr:example" in radio_selected},
                    {"id": "ambient:example", "name": "Example rain", "category": "ambient", "selected": "ambient:example" in radio_selected},
                ],
            },
        }

    def payload():
        rows = [
            {
                "id": f"calendar.fixture_{i}",
                "name": "Example feed",
                "mode": modes.get(f"calendar.fixture_{i}", "review"),
                "suggested": "context",
                "reason": "Preview before choosing.",
                "source": {"integration": "google", "account": "Example hub"},
            }
            for i in range(2)
        ]
        counts = {mode: sum(r["mode"] == mode for r in rows) for mode in ["review", "show", "context", "ignore"]}
        return {
            "calendars": {"version": 1, "epoch": 0, "revision": revision, "calendars": modes, "rows": rows, "counts": counts},
            "music": {"summary": "Music Assistant users: 6/6 configured", "connected": 3, "pending": 1, "spotify": []},
            "google": {
                "state": "connected" if authenticated else "ready_for_authentication",
                "detail": "Review calendars" if authenticated else "Sign in to Google",
                "route": "/fixture/return",
                "guide": ["Complete consent in the native service."],
                "redirect_uri": "https://my.home-assistant.io/redirect/oauth",
            },
            "checks": [],
        }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, body, mime="application/json"):
            content = body.encode() if isinstance(body, str) else json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            if self.path == "/":
                self.send(HTML, "text/html")
            elif self.path in {"/connections.js", "/media-setup.js", "/styles.css"}:
                self.send((STATIC / self.path[1:]).read_text(encoding="utf-8"), "text/javascript" if self.path.endswith("js") else "text/css")
            elif self.path == "/api/connections":
                self.send(payload())
            elif self.path == "/api/media":
                self.send(media_payload())
            else:
                self.send_error(404)

        def do_POST(self):
            nonlocal modes, revision, authenticated, radio_selected, local_consent
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
            if self.path == "/api/media":
                if body["action"] == "select":
                    radio_selected = set(body["selected"])
                elif body["action"] in {"allow_local_lookup", "disable_local_lookup"}:
                    local_consent = body["action"] == "allow_local_lookup"
                self.send(media_payload())
                return
            if self.path == "/api/connections/calendars":
                modes = body["calendars"]
                revision += 1
            if self.path == "/fixture/return":
                authenticated = True
            if self.path == "/api/connections/preview":
                title = "Example school session" if body["source"].endswith("0") else "Example work appointment"
                self.send({"events": [{"title": title, "start": "2026-11-02T09:00:00+11:00"}], "detail": "Preview only; not saved"})
            else:
                self.send(payload())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    shots = Path("screens/connection-acceptance")
    shots.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1200, "height": 900})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.get_by_text("Spotify: 3 connected · 1 pending", exact=True)).to_be_visible()
            # Ambiguous labels must be distinguishable without asking the user
            # to guess or manually open each feed first.
            expect(page.get_by_text("Example school session", exact=True)).to_be_visible()
            expect(page.get_by_text("Example work appointment", exact=True)).to_be_visible()
            page.get_by_role("button", name="Continue Google Calendar setup", exact=True).click()
            expect(page.get_by_text("Sign in to Google", exact=True)).to_have_count(0)
            for i, title in enumerate(["Example school session", "Example work appointment"], 1):
                page.get_by_role("button", name=f"Preview upcoming events for Example feed ({i} of 2)", exact=True).click()
                expect(page.get_by_text(title, exact=True)).to_be_visible()
            page.screenshot(path=str(shots / "desktop.png"), full_page=True)
            page.get_by_label("Visibility for Example feed (1 of 2)", exact=True).select_option("show")
            page.get_by_label("Visibility for Example feed (2 of 2)", exact=True).select_option("context")
            page.get_by_role("button", name="Save calendar choices", exact=True).click()
            expect(page.get_by_text("1 calendars shown at home · 1 context-only · 0 ignored", exact=True)).to_be_visible()
            page.reload()
            expect(page.get_by_label("Visibility for Example feed (1 of 2)", exact=True)).to_have_value("show")
            page.get_by_text("Music discovery, radio and ambient", exact=True).click()
            page.get_by_role("button", name="Check media", exact=True).click()
            expect(page.get_by_role("button", name="Allow local radio lookup", exact=True)).to_be_visible()
            assert not local_consent, "Ordinary setup must not imply location consent"
            page.get_by_role("button", name="Allow local radio lookup", exact=True).click()
            expect(page.get_by_role("button", name="Disable postcode lookup", exact=True)).to_be_visible()
            assert local_consent
            page.get_by_text("Ambient · 0 selected", exact=True).click()
            page.get_by_label("Example rain", exact=True).check()
            page.get_by_role("button", name="Save selected stations", exact=True).click()
            expect(page.get_by_text("2 of 2 selected stations ready. 2 stations discovered.", exact=True)).to_be_visible()
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(shots / "mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("Connection browser acceptance passed: calendar previews, auth return, media selection, explicit location consent, desktop/mobile.")


if __name__ == "__main__":
    main()
