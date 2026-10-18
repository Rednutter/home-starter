import json
from datetime import datetime
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
        ["/usr/bin/wlr-randr", "--output", "HDMI-A-1", "--on", "--transform", "180"],
        ["/usr/bin/wlopm", "--on", "HDMI-A-1"],
    ]
    with pytest.raises(RuntimeError, match="unavailable"):
        reconcile("missing", "off", execute)
    with pytest.raises(RuntimeError, match="did not confirm"):
        reconcile("HDMI-A-1", "off", lambda _: json.dumps([{"output": "HDMI-A-1", "power-mode": "on"}]))


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
