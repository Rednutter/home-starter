"""Fictional native subjects; never infer kit, year levels or feed ownership."""

from datetime import timedelta

from homestarter.wall_composer import compose
from wall_scenarios import ZONE, scenario


def render(case):
    return compose(case["view"], case["events"], case["settings"], case["people"], case["now"], ZONE, case["signals"])


def test_native_period_order_and_provenance_survive_sunday_to_monday():
    sunday, monday = scenario("school_sunday"), scenario("school_monday")
    sunday["view"]["school_sources"][0]["events"].reverse()
    evening, morning = render(sunday), render(monday)
    assert evening["school"]["label"] == "Tomorrow at school"
    assert morning["school"]["label"] == "Today at school"
    for child in evening["school"]["children"]:
        assert [p["subject"] for p in child["periods"]] == ["Form", "Science", "Science", "English", "Maths", "PE", "Library"]
        assert child["sources"][0]["kind"] == "ha_calendar"
        assert child["periods"][0]["source"] == child["sources"][0]["entity"]
    assert [c["periods"] for c in evening["school"]["children"]] == [c["periods"] for c in morning["school"]["children"]]
    assert not any(word in str(evening["school"]).lower() for word in ("uniform", "bag", "instrument", "swimmers", "year 8"))


def test_missing_data_fails_safely_without_using_another_child_or_day():
    case = scenario("school_sunday")
    first = case["view"]["school_sources"][0]
    first["events"] = [{**e, "start": e["start"] + timedelta(days=1)} for e in first["events"]]
    case["view"]["school_sources"] = [first]
    school = render(case)["school"]
    assert all(not c["periods"] and c["fallback"] == "School tomorrow" for c in school["children"])
    assert [c["status"] for c in school["children"]] == ["no_classes", "not_configured", "not_configured"]


def test_explicit_dated_school_information_then_subjects_then_configured_rules():
    case = scenario("school_sunday")
    dated = case["events"][0]
    case["settings"]["events"][dated["key"]]["wall_role"] = "school"
    case["settings"]["rules"] = [
        {"id": "hat", "text": "Explicit hat rule", "people": ["example_child"], "start": "2026-10-19", "end": "2026-10-19", "weekdays": [0]}
    ]
    model = render(case)
    child = model["school"]["children"][0]
    assert child["dated"][0]["title"] == "School" and child["periods"] and child["rules"] == ["Explicit hat rule"]
    assert dated["key"] not in {r["id"] for r in model["timeline"]["items"]}
    assert not model["cards"]
    assert len(model["week"]) == 5 and model["week"][0]["label"] == "Tuesday"
    ids = [r["id"] for panel in (model["timeline"], model["secondary"], *model["week"]) for r in panel["items"]]
    assert len(ids) == len(set(ids))


def test_explicit_routine_exception_and_unconfirmed_people_suppress_school():
    case = scenario("school_sunday")
    case["settings"]["wall"] = {"suppressed_dates": ["2026-10-19"]}
    assert render(case)["school"] is None
    case = scenario("school_sunday")
    case["view"]["person_roles"] = dict.fromkeys(case["people"], "adult")
    assert render(case)["school"] is None
    case = scenario("school_sunday")
    assert all("year" not in c for c in render(case)["school"]["children"])
