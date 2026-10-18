"""Read dated native classes only; subjects never imply clothing or equipment."""

from datetime import date, datetime


def attendance(children, explicit_people, local):
    """Summarise dated native periods once per start time, never invent school days."""
    groups = {}
    for child in children:
        if not child["periods"] or child["person"] in explicit_people:
            continue
        start = min(datetime.fromisoformat(p["start"]) for p in child["periods"]).astimezone(local.tzinfo)
        end = max(datetime.fromisoformat(p["end"]) for p in child["periods"])
        if end <= local:
            continue
        key = start.isoformat()
        row = groups.setdefault(
            key,
            {
                "id": "school-attendance-" + key,
                "kind": "school_attendance",
                "title": "School",
                "people": [],
                "person_ids": [],
                "sources": [],
                "date": start.date().isoformat(),
                "starts_at": key,
                "ends_at": end.isoformat(),
                "day_offset": (start.date() - local.date()).days,
                "day_label": start.strftime("%A"),
                "time": start.strftime("%I:%M").lstrip("0") + (" pm" if start.hour >= 12 else ""),
            },
        )
        row["ends_at"] = max(datetime.fromisoformat(row["ends_at"]), end).isoformat()
        row["people"].append(child["name"])
        row["person_ids"].append(child["person"])
        row["sources"].extend(child["sources"])
    return list(groups.values())


def select(sources, people, roles, focus, local, suppressed=False):
    """A mapped native timetable is authoritative for its dated classes, not kit."""
    day = date.fromisoformat(focus["date"])
    if suppressed or focus.get("restrained") or not (focus["preview"] or local.hour < 12):
        return None
    children = []
    for person, name in people.items():
        if roles.get(person) != "child":
            continue
        feeds = [s for s in sources if s["person"] == person]
        periods = []
        seen = set()
        for feed in feeds:
            for event in feed["events"]:
                if event["all_day"] or event["start"].date() != day:
                    continue
                key = (event["start"], event["end"], event["title"])
                if key in seen:
                    continue
                seen.add(key)
                periods.append({"subject": event["title"], "start": event["start"].isoformat(), "end": event["end"].isoformat(), "source": feed["source"]})
        periods.sort(key=lambda r: r["start"])
        if day.weekday() >= 5 and not periods:
            continue
        children.append(
            {
                "person": person,
                "name": name,
                "periods": periods,
                "sources": [{"kind": "ha_calendar", "entity": f["source"], "label": f["label"]} for f in feeds],
                "status": "available" if periods else "no_classes" if feeds else "not_configured",
                "fallback": "School tomorrow" if focus["preview"] else "School today",
            }
        )
    return {"label": focus["label"] + " at school", "date": focus["date"], "children": children} if children else None
