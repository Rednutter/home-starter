"""Explicit household playlist sharing; no provider writes or owner inference."""

from __future__ import annotations

import copy
import threading

from .household import HouseholdStore


def identities(row):
    """Account-independent upstream identity, never a title or display owner."""
    keys = set()
    for mapping in row.get("provider_mappings", []):
        namespace = mapping.get("catalogue_namespace") or mapping.get("provider_domain") or mapping.get("provider_instance")
        if namespace and mapping.get("item_id"):
            keys.add(str(namespace) + ":playlist:" + str(mapping["item_id"]))
    if not keys and row.get("uri"):
        keys.add("uri:" + row["uri"])
    return keys


def rule_for(row, rules):
    found = [rules[key] for key in identities(row) if key in rules]
    # Conflicting aliases must be reconciled explicitly, never union access.
    if found and all(rule == found[0] for rule in found):
        return found[0]
    return None


def visible(rule, profile):
    if not rule:
        return False
    mode = rule.get("visibility")
    return rule.get("owner") == profile or mode == "house" or mode == "selected" and profile in rule.get("shared_with", [])


class PlaylistVisibilityStore:
    """Separate versioned document using the existing atomic persistence helper.

    No production route wires writes. Missing files stay missing on read. A
    revision prevents stale local writers; no cross-process atomicity is claimed.
    """

    def __init__(self, directory):
        root = HouseholdStore(str(directory)).path.parent
        self.path = root / "playlist-visibility.json"
        self.lock = threading.Lock()

    def load(self):
        value = HouseholdStore.read(self.path, {"version": 1, "revision": 0, "rules": {}})
        if not isinstance(value, dict) or value.get("version") != 1 or type(value.get("revision")) is not int or not isinstance(value.get("rules"), dict):
            raise ValueError("Playlist visibility needs recovery; existing data is preserved.")
        return value

    def assign(self, row, *, owner, visibility, shared_with, people, expected_revision, actor, administrator=False):
        if not administrator:
            raise PermissionError("Only an explicitly authorised administrator can change playlist sharing.")
        known = set(people) | {"house"}
        if row.get("media_type") != "playlist" or owner not in known or visibility not in {"mine", "selected", "house"}:
            raise ValueError("Choose an explicit owner and visibility.")
        if not isinstance(shared_with, list) or not set(shared_with) <= known - {"house", owner}:
            raise ValueError("Choose current household people.")
        if visibility != "selected" and shared_with or visibility == "selected" and not shared_with:
            raise ValueError("Selected sharing requires selected people; other modes have no selected people.")
        if not isinstance(actor, str) or actor not in known:
            raise ValueError("Record the confirming household identity.")
        keys = identities(row)
        if not keys:
            raise ValueError("A verified upstream playlist identity is required.")
        with self.lock:
            current = self.load()
            if current["revision"] != expected_revision:
                raise ValueError("Playlist sharing changed; review the current selection.")
            updated = copy.deepcopy(current)
            rule = {
                "owner": owner,
                "visibility": visibility,
                "shared_with": sorted(set(shared_with)),
                "provenance": "explicit-household-choice",
                "confirmed_by": actor,
            }
            for key in keys:
                updated["rules"][key] = rule
            updated["revision"] += 1
            HouseholdStore.write(self.path, updated)
            return updated
