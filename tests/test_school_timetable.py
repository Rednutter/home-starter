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


def test_late_evening_keeps_monday_school_cards_and_timeline_until_midnight():
    case = scenario("school_sunday")
    evening = render(case)
    for hour, minute in ((22, 9), (23, 59)):
        case["now"] = case["now"].replace(hour=hour, minute=minute)
        late = render(case)
        assert late["baseline_state"] == "overnight" and late["phase"] == "night"
        assert late["focus"]["preview"] and not late["focus"].get("restrained")
        assert late["school"] == evening["school"] and len(late["school"]["children"]) == 3
        assert late["timeline"] == evening["timeline"]
        assert late["focus"]["night"] and not late["week"] and not late["cards"]
    case["now"] = case["now"].replace(hour=0, minute=30) + timedelta(days=1)
    overnight = render(case)
    assert overnight["focus"]["night"] and not overnight["focus"]["preview"]
    assert overnight["school"]["date"] == evening["school"]["date"]
    assert [(c["person"], c["periods"]) for c in overnight["school"]["children"]] == [(c["person"], c["periods"]) for c in evening["school"]["children"]]
    assert overnight["timeline"]["label"] == "Today" and not overnight["week"]


def test_night_boundaries_keep_people_and_morning_restores_full_detail():
    case = scenario("school_sunday")
    for hour, minute, expected in ((20, 59, False), (21, 0, True), (23, 59, True)):
        case["now"] = case["now"].replace(hour=hour, minute=minute)
        model = render(case)
        assert model["focus"]["night"] is expected
        assert len(model["school"]["children"]) == 3 and model["timeline"]["items"]
    case["now"] = case["now"] + timedelta(days=1)
    for hour, minute, expected in ((0, 0, True), (4, 59, True), (5, 0, False)):
        case["now"] = case["now"].replace(hour=hour, minute=minute)
        model = render(case)
        assert model["focus"]["night"] is expected
        assert model["focus"]["date"] == "2026-10-19" and len(model["school"]["children"]) == 3


def test_explicit_dated_school_information_then_subjects_then_configured_rules():
    case = scenario("school_sunday")
    dated = scenario("canonical_evening")["events"][0]
    case["events"].insert(0, dated)
    case["settings"]["events"][dated["key"]]["wall_role"] = "school"
    case["settings"]["rules"] = [
        {"id": "hat", "text": "Explicit hat rule", "people": ["example_child"], "start": "2026-10-19", "end": "2026-10-19", "weekdays": [0]}
    ]
    model = render(case)
    child = model["school"]["children"][0]
    assert child["dated"][0]["title"] == "School" and child["periods"] and child["rules"] == ["Explicit hat rule"]
    assert dated["key"] in {r["id"] for r in model["timeline"]["items"]}
    assert len([r for r in model["timeline"]["items"] if r["title"] == "School"]) == 1
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


def test_timeline_groups_school_attendance_and_keeps_every_dated_commitment():
    case = scenario("school_sunday")
    model = render(case)
    attendance = [r for r in model["timeline"]["items"] if r.get("kind") == "school_attendance"]
    assert len(attendance) == 1
    row = attendance[0]
    assert row["title"] == "School" and row["time"] == "9:00"
    assert row["people"] == list(case["people"].values())
    assert row["person_ids"] == list(case["people"])
    assert len(row["sources"]) == 3 and not row.get("leave_at")
    expected = {e["key"] for e in case["events"] if e["start"].date().isoformat() == model["focus"]["date"]}
    assert expected <= {r["id"] for r in model["timeline"]["items"]}
    assert not any(p["subject"] == r["title"] for c in model["school"]["children"] for p in c["periods"] for r in model["timeline"]["items"])
    stamps = [r.get("leave_at") or r["starts_at"] for r in model["timeline"]["items"]]
    assert stamps == sorted(stamps)


def test_attendance_keeps_distinct_times_and_never_invents_missing_school():
    from homestarter.school_timetable import attendance

    case = scenario("school_sunday")
    case["view"]["school_sources"][1]["events"] = []
    for period in case["view"]["school_sources"][2]["events"]:
        period["start"] += timedelta(minutes=20)
        period["end"] += timedelta(minutes=20)
    model = render(case)
    rows = [r for r in model["timeline"]["items"] if r.get("kind") == "school_attendance"]
    assert [r["time"] for r in rows] == ["9:00", "9:20"]
    assert sum(len(r["people"]) for r in rows) == 2
    children = model["school"]["children"]
    assert not attendance(children, set(), case["now"] + timedelta(days=2))
    assert len(attendance(children, {children[0]["person"]}, case["now"])) == 1
