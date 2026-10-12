"""Small, versioned local household settings. No credentials or usage analytics."""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

PROFILES = {
    "phone": "Personal phone",
    "tablet": "Shared household tablet",
    "specialist": "Specialist fixed panel",
    "kitchen": "Kitchen display",
    "entry": "Entry / exit panel",
    "bedside": "Bedside device",
    "wall": "Non-touch wall display",
}
ID = re.compile(r"^[a-z][a-z0-9_-]{0,47}$")
ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def empty_household() -> dict[str, Any]:
    return {"version": 1, "revision": 0, "people": [], "surfaces": [], "preferences": {}, "overrides": {}, "activities": []}


def text(value: Any, maximum: int = 80) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= maximum and not any(ord(c) < 32 for c in value)


def validate_household(value: Any) -> dict[str, Any]:
    """Validate a complete replacement; unknown keys and unsafe overrides fail closed."""
    base = empty_household()
    if not isinstance(value, dict) or set(value) != set(base) or type(value["version"]) is not int or value["version"] != 1:
        raise ValueError("Unsupported household settings.")
    if type(value["revision"]) is not int or value["revision"] < 0:
        raise ValueError("Invalid household revision.")
    for kind in ("people", "surfaces", "activities"):
        items = value[kind]
        if not isinstance(items, list) or len(items) > 50:
            raise ValueError("Too many household items.")
        ids = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not ID.fullmatch(item["id"]) or not text(item.get("name")):
                raise ValueError("Each household item needs a short name and a stable ID.")
            ids.append(item["id"])
        if len(set(ids)) != len(ids):
            raise ValueError("Household IDs must be unique.")
    people = {p["id"] for p in value["people"]}
    for p in value["people"]:
        if set(p) != {"id", "name", "audience"} or p["audience"] not in ("everyone", "adult"):
            raise ValueError("Choose a household audience.")
    for s in value["surfaces"]:
        if set(s) != {"id", "name", "profile", "person_id", "area_id", "audience"}:
            raise ValueError("Unsupported screen settings.")
        if not isinstance(s["profile"], str) or s["profile"] not in PROFILES:
            raise ValueError("Choose a supported screen type.")
        if s["person_id"] is not None and (not isinstance(s["person_id"], str) or s["person_id"] not in people):
            raise ValueError("Choose a screen type and an existing person.")
        if s["audience"] not in ("everyone", "adult") or s["area_id"] is not None and not text(s["area_id"]):
            raise ValueError("Choose a screen room and audience.")
    paths = [s["id"].replace("_", "-") for s in value["surfaces"]]
    if len(paths) != len(set(paths)):
        raise ValueError("Screen IDs must resolve to different dashboard addresses.")
    prefs = value["preferences"]
    owners = people | {"surface:" + s["id"] for s in value["surfaces"]}
    if not isinstance(prefs, dict) or not set(prefs) <= owners:
        raise ValueError("Preferences must belong to a person or screen.")
    for pref in prefs.values():
        if not isinstance(pref, dict) or set(pref) != {"pin", "hide", "order"}:
            raise ValueError("Only Pin, Hide and Reorder are supported.")
        for items in pref.values():
            if not isinstance(items, list) or len(items) > 1000 or any(not text(i, 140) for i in items) or len(set(items)) != len(items):
                raise ValueError("Invalid preference list.")
    overrides = value["overrides"]
    if not isinstance(overrides, dict) or len(overrides) > 1000:
        raise ValueError("Invalid household names.")
    for entity_id, rule in overrides.items():
        if not ENTITY.fullmatch(entity_id) or not isinstance(rule, dict) or not set(rule) <= {"name", "include", "audience", "scope"}:
            raise ValueError("Only names, inclusion, audience and scope may be adjusted.")
        if "name" in rule and not text(rule["name"]):
            raise ValueError("Use a short household name.")
        if "include" in rule and type(rule["include"]) is not bool:
            raise ValueError("Invalid inclusion choice.")
        if "audience" in rule and rule["audience"] not in ("everyone", "adult", "admin"):
            raise ValueError("Invalid audience.")
        if "scope" in rule and rule["scope"] not in ("local", "floor", "whole_house", "personal"):
            raise ValueError("Invalid scope.")
    for a in value["activities"]:
        if set(a) != {"id", "name", "entity_id", "from_state", "to_state"} or not ENTITY.fullmatch(str(a["entity_id"])):
            raise ValueError("Choose an existing appliance status and its completion transition.")
        if any(not text(a[k], 60) or a[k] in ("unknown", "unavailable") for k in ("from_state", "to_state")) or a["from_state"] == a["to_state"]:
            raise ValueError("Completion needs two different, known states.")
    return copy.deepcopy(value)


class HouseholdStore:
    """Atomic file replacement. Failed/corrupt reads never silently reset user data."""

    def __init__(self, directory: str) -> None:
        self.path = Path(directory) / "household.json"
        self.activity_path = Path(directory) / "activity.json"
        self.publication_path = Path(directory) / "publications.json"

    @staticmethod
    def read(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return copy.deepcopy(default)

    @staticmethod
    def write(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def load(self) -> dict[str, Any]:
        return validate_household(self.read(self.path, empty_household()))

    def save(self, value: Any) -> dict[str, Any]:
        value = validate_household(value)
        if self.load()["revision"] != value["revision"]:
            raise ValueError("Settings changed elsewhere. Refresh before saving.")
        value["revision"] += 1
        self.write(self.path, value)
        return value
