#!/usr/bin/env python3
"""Read-only endpoint health; no HA credential, remote commands or media metadata."""

import hmac
import json
import os
import shutil
import subprocess
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

CONFIG = Path.home() / ".config/home-starter/endpoint.json"


def display_authenticated(config, tabs):
    expected = config.get("display_user_id")
    if not expected:
        return False
    for tab in tabs:
        if tab.get("type") != "page" or tab.get("url", "").split("?")[0] != config["dashboard_url"].split("?")[0]:
            continue
        address = tab.get("webSocketDebuggerUrl", "")
        if not address.startswith("ws://127.0.0.1:9222/devtools/page/"):
            continue
        # Read only connection/account booleans; never request token storage or page text.
        expression = (
            "(()=>{const h=document.querySelector('home-assistant')?.hass;return !!(h?.connected&&h.user?.id==="
            + json.dumps(expected)
            + "&&!h.user.is_admin)})()"
        )
        try:
            with connect(address, open_timeout=2, close_timeout=1, max_size=65536) as socket:
                socket.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}}))
                for _ in range(10):
                    reply = json.loads(socket.recv(timeout=2))
                    if reply.get("id") == 1:
                        return reply.get("result", {}).get("result", {}).get("value") is True
        except (OSError, ValueError, TimeoutError, WebSocketException):
            pass
    return False


def service(name):
    result = subprocess.run(  # noqa: S603 -- internal fixed service names only
        ["/usr/bin/systemctl", "--user", "is-active", name], capture_output=True, text=True, timeout=3
    )
    return result.stdout.strip() or "unknown"


def health(config):
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    uptime = float(Path("/proc/uptime").read_text().split()[0])
    storage = shutil.disk_usage(Path.home())
    temperature = float(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    browser_alive = False
    dashboard_open = False
    authenticated = False
    try:
        with urlopen("http://127.0.0.1:9222/json/list", timeout=2) as response:
            tabs = json.load(response)
        browser_alive = any(t.get("type") == "page" for t in tabs)
        dashboard_open = any(t.get("type") == "page" and t.get("url", "").split("?")[0] == config["dashboard_url"].split("?")[0] for t in tabs)
        authenticated = display_authenticated(config, tabs)
    except (OSError, ValueError):
        pass
    return {
        "version": 1,
        "online": True,
        "checked_at": datetime.now(UTC).isoformat(),
        "boot_id": boot,
        "last_boot": datetime.fromtimestamp(time.time() - uptime, UTC).isoformat(),
        "uptime_seconds": int(uptime),
        "cpu_temperature": round(temperature, 1),
        "load_1m": round(os.getloadavg()[0], 2),
        "storage_used_percent": round(storage.used * 100 / storage.total, 1),
        "storage_free_gb": round(storage.free / 1024**3, 1),
        "browser_alive": browser_alive,
        "dashboard_open": dashboard_open,
        "authenticated_display_verified": authenticated,
        "display_service": service("home-starter-display.service"),
        "audio_service": service("home-starter-audio.service"),
        "voice_service": service("home-starter-voice.service"),
        "updates_check": "needs_privileged_refresh",
    }


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    key = config["health_key"]
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("Configure a dedicated health key.")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/health" or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key):
                self.send_error(404)
                return
            try:
                body = json.dumps(health(config)).encode()
            except (OSError, ValueError, subprocess.TimeoutExpired):
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    ThreadingHTTPServer((config.get("health_bind", "0.0.0.0"), config.get("health_port", 8741)), Handler).serve_forever()


if __name__ == "__main__":
    main()
