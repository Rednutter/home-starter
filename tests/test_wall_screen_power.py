import json
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from kitchen_wall.install_screen_power import prevent_auto_wake
from kitchen_wall.screen_power import power_mode, reconcile


@pytest.mark.parametrize("hour,minute,mode", [(21, 59, "on"), (22, 0, "off"), (23, 59, "off"), (0, 0, "off"), (5, 59, "off"), (6, 0, "on")])
def test_screen_power_boundaries(hour, minute, mode):
    assert power_mode(datetime(2026, 10, 18, hour, minute, tzinfo=ZoneInfo("Australia/Sydney"))) == mode


@pytest.mark.parametrize("day", [3, 4])
def test_dst_keeps_local_wall_hours(day):
    for hour, expected in ((5, "off"), (6, "on"), (22, "off")):
        assert power_mode(datetime(2026, 10, day, hour, tzinfo=ZoneInfo("Australia/Sydney"))) == expected


def test_power_recovery_is_idempotent_and_confirms_real_output_state():
    mode, changes = "on", []

    def execute(command):
        nonlocal mode
        if command[-1] == "--json":
            return json.dumps([{"output": "HDMI-A-1", "power-mode": mode}])
        changes.append(command)
        if command[0] == "/usr/bin/wlr-randr":
            return ""
        mode = command[1][2:]
        return ""

    reconcile("HDMI-A-1", "off", execute)
    reconcile("HDMI-A-1", "off", execute)
    reconcile("HDMI-A-1", "on", execute)
    assert changes == [
        ["/usr/bin/wlopm", "--off", "HDMI-A-1"],
        ["/usr/bin/wlr-randr", "--output", "HDMI-A-1", "--on", "--mode", "1920x1080@60Hz", "--transform", "180"],
        ["/usr/bin/wlopm", "--on", "HDMI-A-1"],
    ]
    with pytest.raises(RuntimeError, match="unavailable"):
        reconcile("missing", "off", execute, wait=lambda _: None)
    with pytest.raises(RuntimeError, match="did not confirm"):
        reconcile("HDMI-A-1", "off", lambda _: json.dumps([{"output": "HDMI-A-1", "power-mode": "on"}]), wait=lambda _: None)


def test_standby_hotplug_guard_preserves_existing_compositor_configuration():
    from xml.etree import ElementTree as ET

    revised = prevent_auto_wake("<labwc_config><core><gap>4</gap></core><theme><name>existing</name></theme></labwc_config>")
    root = ET.fromstring(revised)  # noqa: S314 -- synthetic local XML fixture
    assert root.findtext("core/autoEnableOutputs") == "no"
    assert root.findtext("core/gap") == "4" and root.findtext("theme/name") == "existing"
    assert prevent_auto_wake(revised) == revised
    assert "autoEnableOutputs" in prevent_auto_wake("")


def test_disabled_hdmi_is_off_and_explicit_morning_wake_restores_it():
    enabled = False

    def execute(command):
        nonlocal enabled
        if command == ["/usr/bin/wlopm", "--json"]:
            return json.dumps([{"output": "HDMI-A-1", "power-mode": "on"}] if enabled else [{"output": "NOOP-1", "power-mode": "on"}])
        if command == ["/usr/bin/wlr-randr", "--json"]:
            return json.dumps([{"name": "HDMI-A-1", "enabled": enabled}])
        assert command[0] in {"/usr/bin/wlr-randr", "/usr/bin/wlopm"}
        enabled = True
        return ""

    reconcile("HDMI-A-1", "off", execute)
    assert not enabled
    reconcile("HDMI-A-1", "on", execute)
    assert enabled


def test_wake_retries_a_stale_output_configuration_and_rechecks_physical_output():
    enabled, calls, waits = False, [], []

    def execute(command):
        nonlocal enabled
        calls.append(command)
        if command == ["/usr/bin/wlopm", "--json"]:
            return json.dumps([{"output": "HDMI-A-1" if enabled else "NOOP-1", "power-mode": "on"}])
        if command == ["/usr/bin/wlr-randr", "--json"]:
            return json.dumps([{"name": "HDMI-A-1", "enabled": enabled}])
        if command[0] == "/usr/bin/wlr-randr":
            assert command[command.index("--mode") + 1] == "1920x1080@60Hz"
            if not waits:
                raise subprocess.CalledProcessError(1, command, stderr="failed to apply configuration")
            enabled = True
        return ""

    reconcile("HDMI-A-1", "on", execute, wait=waits.append)
    assert enabled and waits == [1]
    assert calls.count(["/usr/bin/wlr-randr", "--json"]) == 2


def test_permanent_wake_failure_is_bounded_and_never_confuses_headless_with_hdmi():
    wake_calls, waits = [], []

    def execute(command):
        if command == ["/usr/bin/wlopm", "--json"]:
            return json.dumps([{"output": "NOOP-1", "power-mode": "on"}])
        if command == ["/usr/bin/wlr-randr", "--json"]:
            return json.dumps([{"name": "HDMI-A-1", "enabled": False}])
        wake_calls.append(command)
        raise subprocess.CalledProcessError(1, command)

    with pytest.raises(RuntimeError, match="on failed after 3 attempts"):
        reconcile("HDMI-A-1", "on", execute, wait=waits.append)
    assert len(wake_calls) == 3 and waits == [1, 2]
    assert all(command[0] == "/usr/bin/wlr-randr" for command in wake_calls)


def test_startup_pins_wake_mode_without_forcing_overnight_power_on():
    service = Path(__file__).parents[1] / "devtools/kitchen_wall/home-starter-display.service"
    line = next(line for line in service.read_text().splitlines() if line.startswith("ExecStartPre=") and "wlr-randr" in line)
    command = shlex.split(line.partition("=")[2])
    assert command[command.index("--mode") + 1] == "1920x1080@60Hz"
    assert command[command.index("--transform") + 1] == "180"
    assert "--on" not in command
