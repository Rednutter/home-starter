from datetime import timedelta

import pytest
from homestarter.context import validate
from homestarter.wall_composer import compose, session, validate_policy
from wall_scenarios import SCENARIOS, ZONE, scenario


@pytest.mark.parametrize("name", SCENARIOS)
def test_twelve_scenarios_use_one_inspectable_wall_contract(name):
    case = scenario(name)
    assert case["model"]["version"] == 1
    assert case["model"]["day_state"]
    assert all("Finished" not in r["title"] for r in case["model"]["today_items"])


def test_explicit_routine_departure_and_movement_thresholds():
    morning = scenario("busy_school_morning")["model"]
    assert morning["day_state"] == "busy_morning"
    assert morning["next_movement"]["detail"] == "Leave by 08:30"
    assert len(morning["future_attention"]) <= 1
    assert scenario("pre_pickup")["model"]["day_state"] == "pre_activity"
    assert scenario("active_movement")["model"]["day_state"] == "active_movement"


def test_holiday_overrides_routines_without_title_guessing():
    case = scenario("pupil_free_weekday")
    assert case["model"]["day_state"] == "abnormal_schedule"
    assert "Normal school kit" not in str(case["model"])
    case["settings"]["events"].clear()
    unannotated = compose(case["view"], case["events"], case["settings"], case["people"], case["now"], ZONE)
    assert "Normal school kit" in str(unannotated)


def test_quiet_horizon_is_selective_and_completed_items_disappear():
    case = scenario("weekend_planning")
    assert case["model"]["day_state"] == "weekend"
    assert "Melbourne" in str(case["model"]["future_attention"])
    assert case["model"]["spans"]["upcoming"] == "expanded"
    case["settings"]["events"].clear()
    assert not compose(case["view"], case["events"], case["settings"], case["people"], case["now"], ZONE)["future_attention"]
    assert not scenario("evening_finished")["model"]["today_items"]


def test_transients_expire_and_takeover_restores_the_board():
    case = scenario("doorbell_takeover")
    assert case["model"]["display_session"]["camera"] == "camera.example_door"
    later = compose(case["view"], [], case["settings"], case["people"], case["now"] + timedelta(minutes=3), ZONE, case["signals"])
    assert not later["display_session"] and not later["household_exception"]
    content = session({"kind": "recipe", "title": "Dinner", "body": "Step one", "seconds": 30}, case["now"], [])
    board = compose(case["view"], [], case["settings"], {}, case["now"], ZONE, display_session=content)
    assert board["display_session"]
    assert board["valid_until"] > content["expires_at"]
    assert not compose(case["view"], [], case["settings"], {}, case["now"] + timedelta(seconds=31), ZONE, display_session=content)["display_session"]
    assert len(scenario("active_timer_media")["model"]["active_context"]) == 2


def test_sessions_reject_external_content_unselected_cameras_and_unbounded_lifetimes():
    now = scenario("completely_quiet")["now"]
    for content in (
        {"kind": "camera", "title": "Door", "camera": "camera.private"},
        {"kind": "answer", "title": "Answer", "seconds": 601},
        {"kind": "answer", "title": "Answer", "url": "https://example.com"},
    ):
        with pytest.raises(ValueError):
            session(content, now, [])


def test_configuration_remains_data_and_does_not_change_other_context_settings():
    value = {"rules": [], "events": {}, "wall": {"night_start": 23, "suppressed_dates": ["2026-10-20"]}}
    assert validate(value) == value
    for changes in ({"night_start": 4}, {"imminent_minutes": True}, {"suppressed_dates": ["Monday"]}, {"camera_links": {"event.door": "https://example.com"}}):
        with pytest.raises(ValueError):
            validate_policy(changes)


def test_overnight_is_low_information_and_critical_exceptions_override_sessions():
    case = scenario("completely_quiet")
    now = case["now"].replace(hour=23)
    content = session({"kind": "answer", "title": "Answer", "body": "Temporary"}, now, [])
    signals = [{"domain": "media_player", "entity_id": "media_player.fixture", "state": "playing", "name": "Kitchen"}]
    model = compose(case["view"], [], case["settings"], {}, now, ZONE, signals)
    assert model["day_state"] == "overnight" and not model["active_context"]
    signals.append({"domain": "binary_sensor", "entity_id": "binary_sensor.fixture", "state": "on", "level": 0, "name": "Smoke alarm"})
    model = compose(case["view"], [], case["settings"], {}, now, ZONE, signals, content)
    assert model["day_state"] == "exception" and not model["display_session"]
