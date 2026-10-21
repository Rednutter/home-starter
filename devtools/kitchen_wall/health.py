#!/usr/bin/env python3
"""Endpoint health and bounded brightness hints; no HA credential or household payloads."""

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

CONFIG = Path.home() / ".config/home-starter/endpoint.json"


def display_authenticated(config, tabs):
    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect

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


def voice_status():
    """Keep only connection/mute booleans from the loopback peripheral snapshot."""
    from websockets.exceptions import WebSocketException
    from websockets.sync.client import connect

    try:
        with connect("ws://127.0.0.1:6055", open_timeout=2, close_timeout=1, max_size=65536) as socket:
            value = json.loads(socket.recv(timeout=2))
        if value.get("event") == "snapshot":
            data = value.get("data", {})
            if type(data.get("ha_connected")) is bool and type(data.get("muted")) is bool:
                return data["ha_connected"], data["muted"]
    except (OSError, ValueError, TimeoutError, WebSocketException):
        pass
    return False, True


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
    voice_connected, voice_muted = voice_status()
    return {
        "brightness_control": True,
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
        "voice_connected": voice_connected,
        "voice_muted": voice_muted,
        "updates_check": "needs_privileged_refresh",
    }


def handler(config):
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

        def do_POST(self):
            if self.path != "/presentation" or not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + key):
                self.send_error(404)
                return
            try:
                from brightness import PRESENTATION, validate_presentation

                self.connection.settimeout(3)
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 256:
                    raise ValueError("Unsupported signal size")
                value = validate_presentation(json.loads(self.rfile.read(length)), datetime.now(UTC))
                # Only a short-lived enum and expiry are accepted. No calendar or browser data.
                from tempfile import NamedTemporaryFile

                with NamedTemporaryFile(mode="w", dir=PRESENTATION.parent, delete=False) as stream:
                    json.dump(value, stream)
                    temporary = Path(stream.name)
                temporary.replace(PRESENTATION)
                subprocess.run(
                    ["/usr/bin/systemctl", "--user", "start", "--no-block", "home-starter-screen-power.service"],
                    check=True,
                    timeout=3,
                    capture_output=True,
                )  # noqa: S603 -- fixed scheduled policy, never arbitrary commands or brightness values
            except (OSError, ValueError, TypeError, subprocess.SubprocessError):
                self.send_error(400)
                return
            self.send_response(204)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def log_message(self, *_args):
            pass

    return Handler


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    ThreadingHTTPServer((config.get("health_bind", "0.0.0.0"), config.get("health_port", 8741)), handler(config)).serve_forever()


if __name__ == "__main__":
    main()
