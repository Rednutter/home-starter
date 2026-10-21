#!/usr/bin/env python3
"""Hardware brightness only: no browser access, screenshots or household payloads."""

import json
import re
from pathlib import Path

PRESENTATION = Path.home() / ".local/share/home-starter/presentation.json"


def validate_presentation(value, now):
    if not isinstance(value, dict) or set(value) != {"mode", "expires_at"}:
        raise ValueError("Unsupported presentation signal.")
    if value["mode"] not in {"normal", "quiet", "attention", "offline"}:
        raise ValueError("Unsupported presentation mode.")
    stamp = value["expires_at"]
    if type(stamp) not in {int, float} or not 0 < stamp - now.timestamp() <= 150:
        raise ValueError("Expired or invalid presentation signal.")
    return value


def brightness_level(now, presentation=None):
    if now.hour >= 22 or now.hour < 6:
        return None  # Off wins. Never query DDC or wake the monitor overnight.
    base = 25 if now.hour >= 20 else 65 if now.hour >= 18 else 100
    try:
        mode = validate_presentation(presentation, now)["mode"]
    except (ValueError, TypeError):
        mode = "normal"
    if mode == "attention":
        return 100
    if mode == "quiet":
        return min(base, 25)
    if mode == "offline":
        return min(base, 40)
    return base


def monitor_bus(report, output):
    matches = []
    for block in re.split(r"(?m)^Display \d+", report):
        connector = re.search(r"DRM connector:\s+\S*-" + re.escape(output) + r"\s*$", block, re.M)
        bus = re.search(r"I2C bus:\s+/dev/i2c-(\d+)\s*$", block, re.M)
        if connector and bus:
            matches.append(bus[1])
    if len(matches) != 1:
        raise RuntimeError("No unique DDC monitor matches the physical wall output.")
    return matches[0]


def reconcile_brightness(output, target, execute, binary):
    if target is None:
        return None
    if type(target) is not int or not 0 <= target <= 100:
        raise ValueError("Brightness must be a percentage.")
    bus = monitor_bus(execute([binary, "detect", "--brief"]), output)
    prefix = [binary, "--bus", bus]

    def read():
        value = execute([*prefix, "getvcp", "10", "--terse"]).strip()
        match = re.fullmatch(r"VCP 10 C (\d+) (\d+)", value)
        if not match or not 0 <= int(match[1]) <= int(match[2]) or int(match[2]) <= 0:
            raise RuntimeError("Unsupported hardware brightness readback.")
        return int(match[1]), int(match[2])

    current, maximum = read()
    desired = round(target * maximum / 100)
    if current != desired:
        execute([*prefix, "setvcp", "10", str(desired)])
        current, confirmed_maximum = read()
        if current != desired or confirmed_maximum != maximum:
            raise RuntimeError("Monitor did not confirm requested brightness.")
    return round(current * 100 / maximum)


def apply(output, now, execute):
    target = brightness_level(now)
    if target is None:
        return None
    try:
        value = json.loads(PRESENTATION.read_text(encoding="utf-8"))
        target = brightness_level(now, value)
    except (OSError, ValueError):
        pass
    system = Path("/usr/bin/ddcutil")
    local = Path.home() / ".local/share/home-starter/ddcutil/usr/bin/ddcutil"
    binary = system if system.is_file() else local
    if not binary.is_file():
        raise RuntimeError("Hardware brightness utility unavailable.")
    return reconcile_brightness(output, target, execute, str(binary))
