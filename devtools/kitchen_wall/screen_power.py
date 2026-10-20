#!/usr/bin/env python3
"""Keep the dedicated Wayland display asleep 22:00–06:00, independently of Chromium."""

import json
import os
import subprocess
import time
from datetime import datetime
from zoneinfo import ZoneInfo


def power_mode(now):
    return "off" if now.hour >= 22 or now.hour < 6 else "on"


def _reconcile(output, desired, execute, mode):
    def current():
        outputs = json.loads(execute(["/usr/bin/wlopm", "--json"]))
        match = next((r for r in outputs if r.get("output") == output), None)
        if match is None:
            # A standby hotplug may leave HDMI disabled and only NOOP-1 powered.
            # That is still a confirmed off state, not a missing power adapter.
            layout = json.loads(execute(["/usr/bin/wlr-randr", "--json"]))
            disabled = next((r for r in layout if r.get("name") == output), None)
            if disabled and disabled.get("enabled") is False:
                return "off"
        if not match or match.get("power-mode") not in {"on", "off"}:
            raise RuntimeError("Configured wall output is unavailable or has unknown power state.")
        return match["power-mode"]

    if current() != desired:
        if desired == "on":
            # labwc auto-enable is disabled to stop HDMI standby hotplug wakes.
            # Select a stable mode explicitly; do not reselect EDID-preferred 100 Hz.
            execute(["/usr/bin/wlr-randr", "--output", output, "--on", "--mode", mode, "--transform", "180"])
        execute(["/usr/bin/wlopm", "--" + desired, output])
    if current() != desired:
        raise RuntimeError("Wayland did not confirm the scheduled display power state.")


def reconcile(output, desired, execute, mode="1920x1080@60Hz", *, attempts=3, wait=time.sleep):
    # HDMI standby can disconnect/reconnect while an output-management request
    # is in flight. Re-read both adapters on each bounded attempt.
    for attempt in range(attempts):
        try:
            _reconcile(output, desired, execute, mode)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as error:
            if attempt == attempts - 1:
                raise RuntimeError(f"Wall display power {desired} failed after {attempts} attempts: {error}") from error
            wait(attempt + 1)


def main():
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/" + str(os.getuid()))
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")
    desired = power_mode(datetime.now(ZoneInfo(os.environ.get("WALL_TIMEZONE", "Australia/Sydney"))))

    def execute(command):
        return subprocess.run(command, capture_output=True, text=True, check=True, timeout=3).stdout  # noqa: S603 -- fixed display utilities and separate arguments

    reconcile(os.environ.get("WALL_OUTPUT", "HDMI-A-1"), desired, execute, os.environ.get("WALL_MODE", "1920x1080@60Hz"))
    print("Wall display power verified: " + desired)


if __name__ == "__main__":
    main()
