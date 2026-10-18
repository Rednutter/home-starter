"""Read dated native classes only; subjects never imply clothing or equipment."""

from datetime import date


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
