#!/usr/bin/env python3
"""Transparent cursor theme for the dedicated labwc/Wayland wall account only."""

import ctypes
import ctypes.util
import re
import struct
import subprocess
from pathlib import Path

THEME = "home-starter-hidden"
MARKER = "Home Starter dedicated wall cursor"


def transparent_cursor():
    # Xcursor image format, also used by Wayland cursor themes. One transparent
    # ARGB pixel, nominal size 24. No X server, cursor daemon or package required.
    return struct.pack("<17I", 0x72756358, 16, 0x10000, 1, 0xFFFD0002, 24, 28, 36, 0xFFFD0002, 24, 1, 1, 1, 0, 0, 0, 0)


class Image(ctypes.Structure):
    _fields_ = [(key, ctypes.c_uint32) for key in ("version", "size", "width", "height", "xhot", "yhot", "delay")] + [
        ("pixels", ctypes.POINTER(ctypes.c_uint32))
    ]


def validate_native(path):
    library = ctypes.CDLL(ctypes.util.find_library("Xcursor"))
    library.XcursorFilenameLoadImage.argtypes = [ctypes.c_char_p, ctypes.c_int]
    library.XcursorFilenameLoadImage.restype = ctypes.POINTER(Image)
    library.XcursorImageDestroy.argtypes = [ctypes.POINTER(Image)]
    image = library.XcursorFilenameLoadImage(str(path).encode(), 24)
    if not image:
        raise RuntimeError("The native cursor library rejected the transparent theme.")
    try:
        if image.contents.width != 1 or image.contents.height != 1 or image.contents.pixels[0] != 0:
            raise RuntimeError("Cursor must contain exactly one transparent pixel.")
    finally:
        library.XcursorImageDestroy(image)


def environment(value):
    keys = {"XCURSOR_THEME", "XCURSOR_SIZE"}
    kept = [line for line in value.splitlines() if line.partition("=")[0].strip() not in keys]
    return "\n".join([*kept, "XCURSOR_THEME=" + THEME, "XCURSOR_SIZE=24", ""])


def main():
    if subprocess.run(["pgrep", "-x", "labwc"], capture_output=True, check=False).returncode:  # noqa: S603,S607 -- fixed local session probe
        raise RuntimeError("This installer is only for an active labwc Wayland wall session.")
    home = Path.home()
    theme = home / ".local/share/icons" / THEME
    if theme.is_symlink() or theme.exists() and MARKER not in (theme / "index.theme").read_text():
        raise RuntimeError("Existing cursor theme is not owned by Home Starter.")
    cursors = theme / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    names = {"default", "left_ptr", "pointer", "hand2", "text", "xterm", "wait", "watch", "crosshair", "move", "not-allowed", "none"}
    for directory in Path("/usr/share/icons").glob("*/cursors"):
        names.update(p.name for p in directory.iterdir() if re.fullmatch(r"[A-Za-z0-9_.-]+", p.name))
    data = transparent_cursor()
    for name in sorted(names):
        (cursors / name).write_bytes(data)
    validate_native(cursors / "default")
    (theme / "index.theme").write_text("[Icon Theme]\nName=" + MARKER + "\nComment=Transparent Wayland kiosk cursors\n", encoding="utf-8")
    config = home / ".config/labwc/environment"
    config.parent.mkdir(parents=True, exist_ok=True)
    old = config.read_text(encoding="utf-8") if config.exists() else ""
    backup = config.with_name("environment.before-home-starter-cursor")
    if not backup.exists():
        backup.write_text(old, encoding="utf-8")
    config.write_text(environment(old), encoding="utf-8")
    drop = home / ".config/systemd/user/home-starter-display.service.d/cursor.conf"
    drop.parent.mkdir(parents=True, exist_ok=True)
    if drop.exists() and MARKER not in drop.read_text():
        raise RuntimeError("Existing cursor service override is not owned by Home Starter.")
    drop.write_text("# " + MARKER + "\n[Service]\nEnvironment=XCURSOR_THEME=" + THEME + "\nEnvironment=XCURSOR_SIZE=24\n", encoding="utf-8")
    # Chromium may consult GTK cursor preferences as well as its environment.
    previous = home / ".config/home-starter/cursor-theme.before"
    if not previous.exists():
        result = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "cursor-theme"], capture_output=True, text=True, check=True)  # noqa: S603,S607 -- fixed setting
        previous.parent.mkdir(parents=True, exist_ok=True)
        previous.write_text(result.stdout.strip(), encoding="utf-8")
    subprocess.run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", THEME], check=True)  # noqa: S603,S607 -- fixed setting
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)  # noqa: S603,S607 -- fixed user service
    print(f"Wayland cursor theme installed and natively validated: {len(names)} aliases. Reboot applies labwc environment; originals preserved.")


if __name__ == "__main__":
    main()
