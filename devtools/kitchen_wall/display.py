#!/usr/bin/env python3
"""Persistent native HA kiosk with a local non-sensitive network fallback."""

import json
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import urlopen

OFFLINE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>Kitchen wall connection</title>
<style>body{margin:0;background:#0b151f;color:#f7f8fa;font:32px Arial,sans-serif;display:grid;place-content:center;
min-height:100vh;padding:0 8vw;box-sizing:border-box;cursor:none}
h1{font-size:52px;font-weight:400}
p{color:#c3cfdd;line-height:1.5;max-width:38ch}
time{font-size:64px;font-variant-numeric:tabular-nums}</style>
<time id="clock">
</time>
<h1>Waiting for Home Assistant</h1>
<p>The household board will return automatically. Old plans are hidden while disconnected.</p>
<script>function tick(){
document.getElementById('clock').textContent=new Date().toLocaleTimeString('en-AU',{hour:'2-digit',minute:'2-digit'});}
tick();setInterval(tick,1000);</script>
</html>"""


def navigate(url):
    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect

    try:
        with urlopen("http://127.0.0.1:9222/json/list", timeout=2) as response:
            tabs = json.load(response)
        for tab in tabs:
            address = tab.get("webSocketDebuggerUrl", "")
            if tab.get("type") != "page" or not address.startswith("ws://127.0.0.1:9222/devtools/page/"):
                continue
            with connect(address, open_timeout=2, close_timeout=1, max_size=65536) as socket:
                socket.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
                for _ in range(10):
                    if json.loads(socket.recv(timeout=2)).get("id") == 1:
                        return True
    except WebSocketException:
        return False
    return False


def reachable(origin):
    if urlparse(origin).scheme not in ("http", "https"):
        return False
    try:
        with urlopen(origin, timeout=3) as response:  # noqa: S310 -- HTTP(S) origin validated above, no credentials supplied.
            return response.status < 500
    except HTTPError as error:
        return error.code < 500
    except (OSError, ValueError, TimeoutError):
        return False


def recovery_target(available, offline, failures, dashboard, fallback):
    failures = 0 if available else failures + 1
    target = dashboard if available and offline else fallback if not available and not offline and failures >= 2 else None
    return target, failures


def fallback_visible(fallback):
    try:
        with urlopen("http://127.0.0.1:9222/json/list", timeout=2) as response:
            return any(t.get("type") == "page" and t.get("url") == fallback for t in json.load(response))
    except (OSError, ValueError, TimeoutError):
        return None


def main():
    config = json.loads((Path.home() / ".config/home-starter/endpoint.json").read_text(encoding="utf-8"))
    url = config["dashboard_url"]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or not parsed.path.startswith("/home-starter-"):
        raise ValueError("Choose the owned Home Starter wall dashboard.")
    origin = parsed.scheme + "://" + parsed.netloc
    profile = Path.home() / ".local/share/home-starter/chromium"
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    fallback = profile.parent / "offline.html"
    fallback.write_text(OFFLINE, encoding="utf-8")
    command = [
        "/usr/bin/chromium",
        "--password-store=basic",
        "--kiosk",
        "--no-first-run",
        "--noerrdialogs",
        "--disable-session-crashed-bubble",
        "--ozone-platform=wayland",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=9222",
        "--user-data-dir=" + str(profile),
        url,
    ]
    process = subprocess.Popen(command)  # noqa: S603 -- fixed Chromium binary, validated URL, no shell
    offline, failures = False, 0
    while process.poll() is None:
        time.sleep(10)
        observed = fallback_visible(fallback.as_uri())
        if observed is not None:
            offline = observed
        target, failures = recovery_target(reachable(origin), offline, failures, url, fallback.as_uri())
        if target:
            try:
                if navigate(target):
                    offline = target == fallback.as_uri()
            except (OSError, ValueError, TimeoutError):
                pass  # Keep the current screen; retry without leaking any account/browser content.
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
