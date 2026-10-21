import json
from datetime import UTC, datetime, timedelta

import pytest
from homestarter import context
from homestarter.household_services import endpoint_presentation
from kitchen_wall.brightness import brightness_level, monitor_bus, reconcile_brightness, validate_presentation

REPORT = """Display 1
   I2C bus: /dev/i2c-20
   DRM connector: card1-HDMI-A-1
   Monitor: Example
"""


@pytest.mark.parametrize("hour,expected", [(5, None), (6, 100), (17, 100), (18, 65), (20, 25), (21, 25), (22, None)])
def test_brightness_boundaries_and_power_precedence(hour, expected):
    now = datetime(2026, 10, 22, hour, tzinfo=UTC)
    assert brightness_level(now) == expected
    if expected is None:
        assert brightness_level(now, {"mode": "attention", "expires_at": now.timestamp() + 60}) is None


def test_fresh_content_and_expiry_without_household_payloads():
    now = datetime(2026, 10, 22, 20, tzinfo=UTC)
    fresh = {"mode": "attention", "expires_at": now.timestamp() + 30}
    assert brightness_level(now, fresh) == 100
    assert brightness_level(now + timedelta(seconds=31), fresh) == 25
    assert brightness_level(now, {**fresh, "expires_at": now.timestamp() + 1000}) == 25
    for value in ({**fresh, "events": ["private"]}, {"mode": "shell", "expires_at": fresh["expires_at"]}, {**fresh, "expires_at": True}):
        with pytest.raises(ValueError):
            validate_presentation(value, now)


def test_ddc_matches_only_physical_output_and_verifies_hardware():
    assert monitor_bus(REPORT, "HDMI-A-1") == "20"
    for value in ("", REPORT + REPORT):
        with pytest.raises(RuntimeError):
            monitor_bus(value, "HDMI-A-1")
    calls = []
    current = 25

    def execute(command):
        nonlocal current
        calls.append(command)
        if "detect" in command:
            return REPORT
        assert command[1:3] == ["--bus", "20"]
        if "setvcp" in command:
            current = int(command[-1])
            return ""
        return f"VCP 10 C {current} 100"

    assert reconcile_brightness("HDMI-A-1", 100, execute, "/usr/bin/ddcutil") == 100
    assert sum("setvcp" in c for c in calls) == 1
    reconcile_brightness("HDMI-A-1", 100, execute, "/usr/bin/ddcutil")
    assert sum("setvcp" in c for c in calls) == 1
    calls.clear()
    assert reconcile_brightness("HDMI-A-1", None, execute, "/usr/bin/ddcutil") is None
    assert calls == []


def test_ddc_failure_cannot_claim_brightness_success():
    values = iter([REPORT, "VCP 10 C 25 100", "", "VCP 10 C 25 100"])
    with pytest.raises(RuntimeError, match="confirm"):
        reconcile_brightness("HDMI-A-1", 100, lambda _: next(values), "/usr/bin/ddcutil")


def test_endpoint_projection_requires_owned_fresh_context_and_expires_with_action():
    now = datetime(2026, 10, 22, 7, tzinfo=UTC)
    endpoint, house = {"surface_id": "wall"}, {"epoch": 3}
    attrs = {
        "home_starter_context": {"surface": "wall", "epoch": 3},
        "checked_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=100)).isoformat(),
        "wall": {"focus": {"night": False}, "priority": {"expires_at": (now + timedelta(seconds=20)).isoformat(), "title": "Private"}},
    }
    states = {context.entity_id("wall"): {"attributes": attrs}}
    signal = endpoint_presentation(endpoint, house, states, now)
    assert signal == {"mode": "attention", "expires_at": (now + timedelta(seconds=20)).timestamp()}
    assert "Private" not in json.dumps(signal)
    assert endpoint_presentation(endpoint, house, states, now + timedelta(seconds=21))["mode"] == "normal"
    attrs["wall"] = {"focus": {"night": True}}
    assert endpoint_presentation(endpoint, house, states, now)["mode"] == "quiet"
    attrs["home_starter_context"]["epoch"] = 2
    assert endpoint_presentation(endpoint, house, states, now)["mode"] == "offline"
    attrs["home_starter_context"]["epoch"] = 3
    attrs["valid_until"] = (now - timedelta(seconds=1)).isoformat()
    assert endpoint_presentation(endpoint, house, states, now)["mode"] == "offline"


def test_presentation_http_is_authenticated_bounded_and_enum_only(monkeypatch, tmp_path):
    import http.client
    import sys
    import threading
    from http.server import ThreadingHTTPServer
    from types import SimpleNamespace

    from kitchen_wall import brightness, health

    monkeypatch.setitem(sys.modules, "brightness", brightness)
    target = tmp_path / "presentation.json"
    monkeypatch.setattr(brightness, "PRESENTATION", target)
    commands = []
    monkeypatch.setattr(health.subprocess, "run", lambda command, **kwargs: commands.append(command) or SimpleNamespace(returncode=0))
    key = "synthetic-local-health-key-for-tests-only"
    server = ThreadingHTTPServer(("127.0.0.1", 0), health.handler({"health_key": key}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(value, auth=key, path="/presentation"):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        connection.request("POST", path, body=json.dumps(value), headers={"Authorization": "Bearer " + auth, "Content-Type": "application/json"})
        response = connection.getresponse()
        status = response.status
        response.read()
        connection.close()
        return status

    try:
        value = {"mode": "attention", "expires_at": datetime.now(UTC).timestamp() + 30}
        assert post(value, auth="incorrect") == 404
        assert post(value, path="/execute") == 404
        assert not target.exists() and not commands
        assert post({**value, "command": "anything"}) == 400
        assert post({"mode": "attention", "expires_at": 0}) == 400
        assert post({"mode": ["attention"], "expires_at": value["expires_at"]}) == 400
        assert post({**value, "events": "x" * 300}) == 400
        assert not target.exists() and not commands
        assert post(value) == 204
        assert json.loads(target.read_text()) == value
        assert commands == [["/usr/bin/systemctl", "--user", "start", "--no-block", "home-starter-screen-power.service"]]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
