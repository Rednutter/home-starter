#!/usr/bin/env python3
"""Launch one persistent Chromium profile on the configured Wayland display."""

import json
import os
from pathlib import Path
from urllib.parse import urlparse

config = json.loads((Path.home() / ".config/home-starter/endpoint.json").read_text(encoding="utf-8"))
url = config["dashboard_url"]
parsed = urlparse(url)
if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or not parsed.path.startswith("/home-starter-"):
    raise ValueError("Choose the owned Home Starter wall dashboard.")
profile = Path.home() / ".local/share/home-starter/chromium"
profile.mkdir(parents=True, exist_ok=True, mode=0o700)
os.execv(  # noqa: S606 -- fixed Chromium binary, validated URL, no shell
    "/usr/bin/chromium",
    [
        "chromium",
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
    ],
)
