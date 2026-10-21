"""Select one short-lived action from confirmed departures; no inferred travel."""

from datetime import datetime, timedelta
from math import ceil


def select(rows, school, local):
    candidates = {}
    for row in rows:
        if row.get("leave_at"):
            candidates[row["id"]] = dict(row)
    if school and school.get("date") == local.date().isoformat():
        grouped = {}
        for child in school.get("children", []):
            at = child.get("school_leave_at")
            if at:
                grouped.setdefault(at, []).append(child["name"])
        for at, names in grouped.items():
            candidates["school-" + at] = {"id": "school-" + at, "title": "School", "leave_at": at, "people": names, "school": True}
    eligible = []
    for row in candidates.values():
        try:
            at = datetime.fromisoformat(row["leave_at"])
            if at.tzinfo is None:
                continue
        except (ValueError, TypeError):
            continue
        minutes = (at - local).total_seconds() / 60
        if not -10 < minutes <= 15:
            continue
        overdue, immediate = minutes < 0, minutes <= 1
        school_run = row.get("school") or row.get("title") == "School"
        title = (
            ("School leave time passed" if school_run else "Leave time passed for " + row["title"])
            if overdue
            else ("School run now" if school_run else "Time to leave for " + row["title"])
            if immediate
            else ("School run" if school_run else "Leave for " + row["title"]) + f" in {ceil(minutes)} minutes"
        )
        eligible.append(
            (
                0 if overdue else 1 if immediate else 2,
                at,
                row["id"],
                {
                    "id": row["id"],
                    "kind": "departure",
                    "title": title,
                    "people": row.get("people", []),
                    "location": row.get("location", ""),
                    "starts_at": row.get("starts_at"),
                    "leave_at": at.isoformat(),
                    "action": "Leave time passed" if overdue else "Leave now" if immediate else "Leave " + at.strftime("%H:%M"),
                    "level": "overdue" if overdue else "immediate" if immediate else "soon",
                    "expires_at": (at + timedelta(minutes=10)).isoformat(),
                },
            )
        )
    for row in rows:
        if row.get("leave_at") or row.get("time") == "All day" or not row.get("starts_at"):
            continue
        try:
            at = datetime.fromisoformat(row["starts_at"])
            minutes = (at - local).total_seconds() / 60
        except (ValueError, TypeError):
            continue
        if not 0 <= minutes <= 5:
            continue
        preparation = row.get("wall_role") == "preparation"
        eligible.append(
            (
                3 if preparation else 4,
                at,
                row["id"],
                {
                    "id": row["id"],
                    "kind": "preparation" if preparation else "event",
                    "title": ("Prepare for " if preparation else "Starting soon: ") + row["title"],
                    "people": row.get("people", []),
                    "location": row.get("location", ""),
                    "action": "Starts " + at.strftime("%H:%M"),
                    "level": "soon",
                    "expires_at": at.isoformat(),
                },
            )
        )
    return min(eligible, key=lambda item: item[:3])[3] if eligible else None
