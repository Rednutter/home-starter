#!/usr/bin/env python3
"""Home Starter: preserve merged labwc settings and prevent standby HDMI wakes."""

import os
import signal
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET


def prevent_auto_wake(source):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))  # noqa: S314 -- trusted local compositor settings
    root = ET.fromstring(source or "<labwc_config/>", parser=parser)  # noqa: S314 -- trusted local compositor settings
    if root.tag != "labwc_config":
        raise ValueError("Unrecognised labwc configuration; preserve it.")
    core = root.find("core")
    if core is None:
        core = ET.SubElement(root, "core")
    auto = core.find("autoEnableOutputs")
    if auto is None:
        auto = ET.SubElement(core, "autoEnableOutputs")
    auto.text = "no"
    return ET.tostring(root, encoding="unicode") + "\n"


def standard_drm_environment(source):
    """Use wlroots atomic DRM instead of labwc-pi's forced optional backend."""
    key = "WLR_DRM_FORCE_LIBLIFTOFF"
    lines = source.splitlines()
    matches = [index for index, line in enumerate(lines) if line.strip().startswith(key + "=")]
    if len(matches) > 1:
        raise ValueError("Ambiguous graphics backend settings; preserve them for review.")
    setting = key + "=0"
    if matches:
        lines[matches[0]] = setting
    else:
        lines.append(setting)
    return "\n".join(lines) + "\n"


def main():
    pid = subprocess.check_output(["pgrep", "-u", str(os.getuid()), "-x", "labwc"], text=True).strip()  # noqa: S603,S607 -- fixed own-user compositor probe
    if not pid.isdecimal():
        raise RuntimeError("Expected one dedicated labwc session.")
    args = Path("/proc", pid, "cmdline").read_bytes().split(b"\0")
    if not any(arg in (b"-m", b"--merge-config") for arg in args):
        raise RuntimeError("Merged labwc configuration is required; preserve the existing session.")
    config = Path.home() / ".config/labwc/rc.xml"
    before = config.read_text() if config.exists() else ""
    backup = config.with_name("rc.xml.before-home-starter-power")
    if not backup.exists():
        backup.write_text(before)
    config.write_text(prevent_auto_wake(before))
    environment = config.with_name("environment")
    original = environment.read_text() if environment.exists() else ""
    environment_backup = environment.with_name("environment.before-home-starter-drm")
    if not environment_backup.exists():
        environment_backup.write_text(original)
    environment.write_text(standard_drm_environment(original))
    os.kill(int(pid), signal.SIGHUP)
    print(
        "HDMI standby reconnect wake disabled; original labwc configuration preserved. "
        "Standard DRM backend prepared; restart the graphics session to activate it."
    )


if __name__ == "__main__":
    main()
