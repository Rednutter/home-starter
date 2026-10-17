"""Remember who is connecting so native Spotify authentication can resume safely.

No OAuth material is handled here. A single new authenticated MA instance can be
bound to the requested household identity without asking the user to name it.
"""

import math
import time

from . import household_music, household_services
from .music_runtime import private_write


def path(store):
    return store.path.parent / "music-identity-auth.json"


def load(store, house):
    value = store.read(path(store), None)
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "epoch", "name", "before", "provider_id", "at"}
        or value["version"] != 1
        or value["name"] not in household_music.IDENTITIES
        or not isinstance(value["before"], list)
        or any(not isinstance(p, str) for p in value["before"])
        or value["provider_id"] is not None
        and not isinstance(value["provider_id"], str)
        or type(value["at"]) not in (int, float)
        or not math.isfinite(value["at"])
    ):
        raise ValueError("The pending music connection needs administrator review. Existing accounts are preserved.")
    return value if value["epoch"] == house["epoch"] else None


def decorate(store, house, providers):
    config = household_services.load(store, house)
    identities = {
        row["provider_id"]: name
        for row in config["media_identities"]
        for name in household_music.IDENTITIES
        if household_music.normalized(row["name"]) == household_music.normalized(name) and row["provider_id"]
    }
    return [{**p, **({"household_identity": identities[p["id"]]} if p["id"] in identities and p.get("domain") == "spotify" else {})} for p in providers]


def begin(store, house, providers, name):
    if name not in household_music.IDENTITIES:
        raise ValueError("Choose an intended household Spotify account.")
    pending = load(store, house)
    if pending and not pending["provider_id"] and 0 <= time.time() - pending["at"] <= 1800:
        if pending["name"] != name:
            raise ValueError("Finish the music account already being connected before starting another.")
        return pending
    value = {
        "version": 1,
        "epoch": house["epoch"],
        "name": name,
        "before": sorted(p["id"] for p in providers if p.get("domain") == "spotify"),
        "provider_id": None,
        "at": time.time(),
    }
    private_write(path(store), value)
    return value


def resume(store, house, providers):
    pending = load(store, house)
    if not pending or pending["provider_id"] or not 0 <= time.time() - pending["at"] <= 1800:
        return False
    existing = household_music.providers_by_identity(providers).get(pending["name"])
    candidates = (
        [existing]
        if existing and household_music.connected(existing)
        else [p for p in providers if p.get("domain") == "spotify" and household_music.connected(p) and p["id"] not in pending["before"]]
    )
    if len(candidates) > 1:
        raise ValueError("More than one new Spotify account appeared. Review the account mapping; no providers were renamed or removed.")
    if not candidates:
        return False
    name, provider = pending["name"], candidates[0]
    config = household_services.load(store, house)
    rows = [r for r in config["media_identities"] if household_music.normalized(r["name"]) == household_music.normalized(name)]
    if len(rows) > 1 or rows and rows[0]["provider_id"] not in {None, provider["id"]}:
        raise ValueError("Review the existing Spotify identity mapping before changing it.")
    if any(r["provider_id"] == provider["id"] and r not in rows for r in config["media_identities"]):
        raise ValueError("This Spotify account is already mapped to a different household identity.")
    if not rows:
        people = [p["id"] for p in house["people"] if household_music.normalized(p["name"]) == household_music.normalized(name)]
        personal = name in {"Grant", "Renae"}
        if personal and len(people) != 1:
            raise ValueError("Confirm the household person before connecting their Spotify account.")
        row = {
            "id": "spotify_" + household_music.normalized(name),
            "name": name,
            "service": "spotify",
            "scope": "personal" if personal else "shared",
            "people": people if personal else [],
            "provider_id": provider["id"],
        }
        config["media_identities"].append(row)
    else:
        rows[0]["provider_id"] = provider["id"]
    household_services.save(store, house, config)
    private_write(path(store), {**pending, "provider_id": provider["id"]})
    return True
