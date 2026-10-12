"""Simulated Home Assistant ingress for local development and tests.

Mimics the parts of Home Assistant Core + Supervisor ingress that matter to
Home Starter:

* serves the app at ``/api/hassio_ingress/<token>/...`` on the "HA origin",
  forwarding to the app with the prefix stripped, and adds
  ``X-Ingress-Path``, ``X-Hass-Source: core.ingress`` and the
  ``X-Remote-User-*`` headers (homeassistant/components/hassio/ingress.py and
  supervisor/api/ingress.py);
* serves a stand-in for the HA frontend on every other path. Like the real
  app panel (frontend src/panels/app/ha-panel-app.ts) it embeds the app in an
  iframe and handles ``{type: "home-assistant/navigate", path}`` messages from
  that iframe by routing inside the SPA. ``/app/<slug>`` for Music Assistant
  shows a fake Music Assistant page, so "Open Music Assistant" can be followed
  end to end.

    python devtools/ingress_proxy.py --app http://127.0.0.1:8099 --port 8124
"""

from __future__ import annotations

import argparse
import html

import aiohttp
from aiohttp import web

INGRESS_TOKEN = "Xk3mN8pQ2rT5vW9yB1dF4hJ7lN0pS3uW6zA9cE2g"
HOP_HEADERS = {"host", "content-length", "transfer-encoding", "connection", "content-encoding"}

SHELL = """<!doctype html>
<html><head><meta charset="utf-8"><title>Home Assistant (simulated)</title>
<style>
 body{margin:0;font-family:system-ui,sans-serif;display:grid;grid-template-columns:220px 1fr;height:100vh}
 nav{background:#1c1f24;color:#eee;padding:12px;font-size:14px} nav a{color:#9cd2ff;display:block;margin:6px 0}
 #route{font:12px monospace;color:#aaa;margin-top:16px;word-break:break-all}
 main{position:relative} iframe{border:0;width:100%;height:100%} .page{padding:24px}
 @media (max-width: 600px){ body{grid-template-columns:1fr} nav{display:none} }
</style></head>
<body><nav><b>Home Assistant</b><br><small>simulated frontend</small>
<a href="/home_starter">Home Starter</a><div id="route"></div><div id="navlog"></div></nav>
<main id="main"></main>
<script>
const INGRESS = "__INGRESS__";
const PANELS = {"/home_starter": INGRESS + "/", "/app/8a7b9c1d_home_starter": INGRESS + "/"};
window.__navigations = [];
function render() {
  const path = location.pathname + location.search;
  document.getElementById("route").textContent = "route: " + path;
  const main = document.getElementById("main");
  const appMatch = location.pathname.match(/^\\/app\\/([A-Za-z0-9_-]+)/);
  if (PANELS[location.pathname]) {
    main.innerHTML = '<iframe id="panel" title="Home Starter"></iframe>';
    document.getElementById("panel").src = PANELS[location.pathname];
  } else if (appMatch) {
    main.innerHTML = '<div class="page" id="ma-page"><h1>' + appMatch[1] + '</h1><p>App ingress panel (simulated). ' +
      (appMatch[1].endsWith("music_assistant") ? 'Music Assistant web UI would load here.' : '') + '</p></div>';
  } else {
    main.innerHTML = '<div class="page" id="ha-page"><h1>Home Assistant page</h1><p id="ha-path"></p></div>';
    document.getElementById("ha-path").textContent = path;
  }
}
window.addEventListener("message", (event) => {
  const frame = document.getElementById("panel");
  if (!frame || event.source !== frame.contentWindow) return;
  const { type, ...data } = event.data || {};
  if (type === "home-assistant/navigate") {
    window.__navigations.push({ via: "message", path: data.path });
    document.getElementById("navlog").textContent = "last navigate: " + data.path;
    history.pushState(null, "", data.path);
    render();
  }
});
window.addEventListener("popstate", render);
render();
</script></body></html>"""


def build_app(app_url: str, *, token: str = INGRESS_TOKEN, user_id: str = "a1b2c3d4e5f6", ignore_messages: bool = False) -> web.Application:
    app_url = app_url.rstrip("/")
    prefix = f"/api/hassio_ingress/{token}"
    session_holder: dict[str, aiohttp.ClientSession] = {}

    async def on_startup(app: web.Application) -> None:
        session_holder["s"] = aiohttp.ClientSession(auto_decompress=False)

    async def on_cleanup(app: web.Application) -> None:
        await session_holder["s"].close()

    async def ingress(request: web.Request) -> web.StreamResponse:
        tail = request.match_info.get("tail", "")
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        for k in list(headers):
            if k.lower().startswith("x-remote-user"):
                headers.pop(k)  # clients can't spoof these through ingress
        headers.update(
            {
                "X-Ingress-Path": prefix,
                "X-Hass-Source": "core.ingress",
                "X-Remote-User-Id": user_id,
                "X-Remote-User-Name": "fixture_admin",
                "X-Remote-User-Display-Name": "Fixture administrator",
                "X-Forwarded-For": request.remote or "",
            }
        )
        url = f"{app_url}/{tail}"
        if request.query_string:
            url += f"?{request.query_string}"
        async with session_holder["s"].request(request.method, url, headers=headers, data=await request.read()) as upstream:
            body = await upstream.read()
            out = {k: v for k, v in upstream.headers.items() if k.lower() not in HOP_HEADERS}
            return web.Response(body=body, status=upstream.status, headers=out)

    async def shell(request: web.Request) -> web.Response:
        page = SHELL.replace("__INGRESS__", html.escape(prefix))
        if ignore_messages:  # behave like an old frontend without the message handler
            page = page.replace('if (type === "home-assistant/navigate")', "if (false)")
        return web.Response(text=page, content_type="text/html")

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_route("*", prefix + "/{tail:.*}", ingress)
    app.router.add_route("*", prefix, ingress)
    app.router.add_get("/{tail:.*}", shell)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app", default="http://127.0.0.1:8099")
    parser.add_argument("--port", type=int, default=8124)
    parser.add_argument("--old-frontend", action="store_true", help="ignore navigate messages (pre-2026.2 behaviour)")
    args = parser.parse_args()
    web.run_app(build_app(args.app, ignore_messages=args.old_frontend), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
