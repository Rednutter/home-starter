from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homestarter.context import validate
from homestarter.wall_composer import compose, session, short_location, validate_policy
from wall_scenarios import SCENARIOS, ZONE, scenario


@pytest.mark.parametrize("name", SCENARIOS)
def test_scenarios_use_one_inspectable_wall_contract(name):
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


def quiet_week(hour=10):
    now = datetime(2026, 10, 18, hour, 0, tzinfo=ZoneInfo(ZONE))
    events = []
    for n, (day, time, title) in enumerate(
        ((1, 7, "Morning exercise"), (1, 8, "Work commitment"), (1, 17, "Practice match"), (2, 16, "Music lesson"), (4, 18, "Training"), (6, 9, "Weekend game"))
    ):
        start = (now + timedelta(days=day)).replace(hour=time)
        events.append(
            {
                "key": str(n),
                "title": title,
                "start": start,
                "end": start + timedelta(hours=1),
                "all_day": False,
                "location": "Example Club, 123 Example Street, Example Town 2000, Australia",
            }
        )
    return now, events, {"rules": [], "events": {}}, {"briefing": [], "issues": []}


def test_quiet_sunday_expands_tomorrow_and_unannotated_week_without_empty_days():
    now, events, settings, view = quiet_week()
    model = compose(view, events, settings, {}, now, ZONE)
    assert model["layout"] == "tomorrow"
    assert model["today_summary"] == "Quiet Sunday"
    assert len(model["tomorrow_items"]) == 3
    assert [g["label"] for g in model["ahead_groups"]] == ["Tuesday", "Thursday", "Weekend"]
    assert all(g["items"] for g in model["ahead_groups"])
    assert all(r["location"] == "Example Club" for r in model["tomorrow_items"])
    assert "Nothing urgent" not in str(model)


def test_quiet_horizon_evolves_without_inventing_monday_preparation():
    weights = []
    for hour, phase in ((10, "morning"), (15, "afternoon"), (19, "evening")):
        now, events, settings, view = quiet_week(hour)
        model = compose(view, events, settings, {}, now, ZONE)
        assert model["phase"] == phase and model["tomorrow_label"] == "Monday"
        assert not any(r["detail"] for r in model["tomorrow_items"])
        weights.append(model["weights"]["tomorrow"])
    assert weights == sorted(set(weights))


def test_quiet_today_and_tomorrow_reallocate_to_ahead_and_exception_clears():
    now, events, settings, view = quiet_week()
    events = [r for r in events if r["start"].date() > now.date() + timedelta(days=1)]
    ordinary = compose(view, events, settings, {}, now, ZONE)
    assert ordinary["layout"] == "ahead" and ordinary["ahead_groups"]
    signal = {"domain": "binary_sensor", "entity_id": "binary_sensor.fixture", "state": "on", "level": 0}
    assert compose(view, events, settings, {}, now, ZONE, [signal])["layout"] == "current"
    assert compose(view, events, settings, {}, now, ZONE, [dict(signal, state="off")])["layout"] == "ahead"


def test_remaining_today_commitment_outranks_tomorrow_without_a_departure_annotation():
    now, events, settings, view = quiet_week(12)
    today = {**events[-1], "key": "today", "start": now + timedelta(hours=2), "end": now + timedelta(hours=3)}
    model = compose(view, [today, *events], settings, {}, now, ZONE)
    assert model["layout"] == "today"
    assert model["today_items"][0]["id"] == "today" and model["tomorrow_items"]


def test_evening_preparation_uses_only_confirmed_next_day_rules_and_respects_exceptions():
    now, events, settings, view = quiet_week(19)
    settings["rules"] = [{"text": "Bring sports kit", "start": "2026-10-19", "end": "2026-10-19", "weekdays": [0], "people": ["example"]}]
    model = compose(view, events, settings, {"example": "Example"}, now, ZONE)
    assert model["tomorrow_preparation"] == [{"title": "Bring sports kit", "people": ["Example"]}]
    assert model["tomorrow_items"][0]["early_start"]
    assert not compose(view, events, settings, {}, now, ZONE)["tomorrow_preparation"]
    assert not compose(view, events, settings, {"example": "Example"}, now.replace(hour=10), ZONE)["tomorrow_preparation"]
    settings["wall"] = {"suppressed_dates": ["2026-10-19"]}
    assert not compose(view, events, settings, {"example": "Example"}, now, ZONE)["tomorrow_preparation"]
    settings.pop("wall")
    holiday = {**events[0], "key": "holiday", "all_day": True, "end": events[0]["start"] + timedelta(days=1)}
    settings["events"]["holiday"] = {"wall_role": "holiday"}
    assert not compose(view, [*events, holiday], settings, {"example": "Example"}, now, ZONE)["tomorrow_preparation"]


@pytest.mark.parametrize(
    "raw,title,expected",
    [
        ("Example Fitness Gym Exampleville (123 Example Street, Exampleville, Victoria 3000, Australia)", "Exercise", "Example Fitness · Exampleville"),
        ("Example Regional Private Hospital, 123 Example St, Exampleville 3000", "Work ERPH", "ERPH"),
        ("Example Diamonds FC, Exampleville VIC 3000, Australia", "Practice", "Example Diamonds"),
        ("123 Example Street, Exampleville 3000", "Appointment", ""),
        ("https://maps.example/123", "Appointment", ""),
    ],
)
def test_wall_locations_are_human_labels_without_postal_addresses(raw, title, expected):
    assert short_location(raw, title) == expected
