"""Bounded read-only compatibility checks, never playback authorisation.

Matching a server version or response shape never attests account enforcement,
playback ownership, transfer/progress safety or permission to install an adapter.
No credentials, private payloads or new access are returned in diagnostics.
"""

import asyncio
import re

REVIEWED = {"2.10.6", "2.10.7"}
READ_PROBES = (
    ("providers", {}),
    ("auth/users", {}),
    ("players/all", {}),
    ("music/artists/library_items", {"limit": 1, "offset": 0, "summary": False}),
)


def text(value):
    return isinstance(value, str) and 0 < len(value) <= 512


def public_version(value):
    return value if isinstance(value, str) and re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}(?:[a-zA-Z0-9.+-]{0,30})", value) else "unrecognised"


def provider_contract(rows):
    if not isinstance(rows, list) or len(rows) > 256:
        return None
    values = {}
    for row in rows:
        if not isinstance(row, dict) or not text(row.get("instance_id")) or row["instance_id"] in values:
            return None
        if not text(row.get("domain")) or not text(row.get("type")) or type(row.get("available")) is not bool:
            return None
        values[row["instance_id"]] = row
    return {key: row for key, row in values.items() if row["type"] == "music"}


def user_contract(rows):
    if not isinstance(rows, list) or len(rows) > 128:
        return None
    values = {}
    for row in rows:
        if not isinstance(row, dict) or not text(row.get("user_id")) or row["user_id"] in values:
            return None
        values[row["user_id"]] = row
    return values


def profile_state(user, providers):
    if not user:
        return "user_mapping_missing"
    if user.get("enabled", True) is not True:
        return "user_disabled"
    filters = user.get("provider_filter")
    if not isinstance(filters, list) or not filters or any(not text(key) for key in filters):
        return "source_mapping_missing"
    if len(filters) != len(set(filters)) or not set(filters) <= providers.keys():
        return "source_mapping_changed"
    return "ready" if any(providers[key]["available"] for key in filters) else "sources_unavailable"


def library_contract(page, providers):
    if isinstance(page, dict):
        page = page.get("items")
    if not isinstance(page, list) or len(page) > 1:
        return False
    for row in page:
        if not isinstance(row, dict) or row.get("media_type") != "artist" or any(not text(row.get(key)) for key in ("item_id", "provider", "uri", "name")):
            return False
        mappings = row.get("provider_mappings")
        if not isinstance(mappings, list) or not mappings:
            return False
        if any(not isinstance(m, dict) or m.get("provider_instance") not in providers or not text(m.get("item_id")) for m in mappings):
            return False
    return True


def players_contract(rows):
    return (
        isinstance(rows, list)
        and len(rows) <= 256
        and all(
            isinstance(row, dict)
            and text(row.get("player_id"))
            and type(row.get("available")) is bool
            and isinstance(row.get("supported_features"), list)
            and all(text(f) for f in row["supported_features"])
            for row in rows
        )
    )


async def assess_reads(command, endpoint, connection, bindings, *, timeout=2, inspect_unbound=False):
    """Probe only existing read commands with explicit profile→native-user IDs.

    Unknown release numbers can pass these limited data contracts. The caller must
    still recheck actual profile/source policy at each read. Mutations remain false.
    """
    version = public_version(endpoint.get("version")) if isinstance(endpoint, dict) else "unrecognised"
    report = {
        "protocol": 1,
        "server_version": version,
        "reviewed_version": version in REVIEWED,
        "features": {
            "profile_filter_contract": False,
            "catalogue_read_contract": False,
            "player_read_contract": False,
            "protected_spotify": False,
            "native_transfer": False,
        },
        "profiles": {},
        "checks": {},
        "playback_review_required": True,
        "authorizes_data_access": False,
        "authorizes_playback": False,
    }
    if (
        not isinstance(endpoint, dict)
        or not isinstance(connection, dict)
        or any(not text(endpoint.get(key)) or endpoint[key] != connection.get(key) for key in ("server_id", "app"))
    ):
        report["checks"]["connection"] = "identity_changed"
        return report
    schema = endpoint.get("schema_version")
    if schema is not None and (type(schema) is not int or not 1 <= schema <= 10000):
        report["checks"]["schema"] = "invalid"
        return report
    if (
        not isinstance(bindings, dict)
        or not bindings
        or any(not text(k) or not text(v) for k, v in bindings.items())
        or len(set(bindings.values())) != len(bindings)
    ):
        report["checks"]["profiles"] = "explicit_mapping_required"
        if not inspect_unbound:
            return report
        bindings = {}
    if type(timeout) not in {int, float} or not 0 < timeout <= 5:
        raise ValueError("Choose a bounded compatibility timeout.")
    report["checks"]["schema"] = "reported" if schema is not None else "unreported"

    async def probe(name, args):
        try:
            return await asyncio.wait_for(command(name, **args), timeout)
        except Exception:
            # Never include upstream exception text, addresses or raw payloads.
            return None

    providers_raw, users_raw, players_raw, library = await asyncio.gather(*(probe(name, args) for name, args in READ_PROBES))
    providers, users = provider_contract(providers_raw), user_contract(users_raw)
    report["checks"].update(
        providers="passed" if providers is not None else "unavailable_or_changed", users="passed" if users is not None else "unavailable_or_changed"
    )
    if providers is not None and users is not None:
        report["profiles"] = {profile: profile_state(users.get(identity), providers) for profile, identity in bindings.items()}
        report["features"]["profile_filter_contract"] = "ready" in report["profiles"].values()
        valid_library = library_contract(library, providers)
        report["checks"]["library"] = "passed" if valid_library else "unavailable_or_changed"
        report["features"]["catalogue_read_contract"] = valid_library and "ready" in report["profiles"].values()
    report["features"]["player_read_contract"] = players_contract(players_raw)
    return report


def legacy_bindings(profiles, users, providers):
    """Capture the existing unique-name policy only on a reviewed release.

    This never creates/renames users. Subsequent reads use the recorded IDs,
    so an update cannot silently substitute a different same-named user.
    """
    if user_contract(users) is None or not isinstance(providers, dict):
        return {}
    values = {}
    for profile in profiles:
        name = str(profile.get("name", "")).strip().casefold()
        matches = [u for u in users if name and str(u.get("display_name") or u.get("username") or "").strip().casefold() == name]
        if len(matches) == 1 and text(matches[0].get("user_id")) and profile_state(matches[0], providers) == "ready":
            values[profile["id"]] = matches[0]["user_id"]
    return values if len(set(values.values())) == len(values) else {}


def checkpoint_bindings(value, key, profile_ids):
    """Return a private identity checkpoint, never permissions or credentials."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"protocol", "binding", "profiles"} or type(value.get("protocol")) is not int or value["protocol"] != 1:
        raise ValueError("Music profile identity checkpoint needs review.")
    if value["binding"] != key:
        return None
    values = value["profiles"]
    if (
        not isinstance(values, dict)
        or not values
        or not set(values) <= set(profile_ids)
        or any(not text(k) or not text(v) for k, v in values.items())
        or len(set(values.values())) != len(values)
    ):
        raise ValueError("Music profile identity checkpoint needs review.")
    return dict(values)
