"""Explicit service relationships and endpoint health; no service passwords in views."""

from __future__ import annotations

import copy
import ipaddress
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import aiohttp

from .household import ID, text
from .music_runtime import digest, number, private_write


def path(store, name="household-services.json"):
    return store.path.parent / name


def empty(epoch):
    return {
        "version": 1,
        "epoch": epoch,
        "revision": 0,
        "person_links": {},
        "media_identities": [],
        "calendar_hub": None,
        "calendars": [],
        "libraries": [],
        "endpoints": [],
        "directory": [],
        "region": None,
    }


def setup_options(house, inventory, states, music):
    """Admin-only choices: names/IDs, never provider values or calendar events."""
    return {
        "people": [{k: p[k] for k in ("id", "name", "audience")} for p in house["people"]],
        "google": [{"id": e["entry_id"], "name": e["title"], "state": e["state"]} for e in inventory["integrations"] if e["domain"] == "google"],
        "calendars": [
            {"id": s["entity_id"], "name": s.get("attributes", {}).get("friendly_name") or s["entity_id"]}
            for s in states
            if s["entity_id"].startswith("calendar.")
        ],
        "providers": [{k: p[k] for k in ("id", "name", "domain", "status")} for p in (music or {}).get("providers", [])],
        "music_path": (music or {}).get("open_path"),
    }


def check_new_bindings(value, previous, options):
    """Reject fabricated choices; retain existing mappings during service outages."""
    if value["calendar_hub"] and value["calendar_hub"] != previous["calendar_hub"] and value["calendar_hub"] not in {e["id"] for e in options["google"]}:
        raise ValueError("Refresh and choose an existing Google integration.")
    calendars = {r["id"] for r in options["calendars"]} | {r["entity_id"] for r in previous["calendars"]}
    if any(r["entity_id"] not in calendars for r in value["calendars"]):
        raise ValueError("Refresh and choose an existing calendar entity.")
    providers = {p["id"]: p for p in options["providers"]}
    for key, domains in [("media_identities", {"spotify"}), ("libraries", {"audiobookshelf", "audible", "storytel"})]:
        old = {r["id"]: r["provider_id"] for r in previous[key]}
        for row in value[key]:
            provider = row["provider_id"]
            if provider and provider != old.get(row["id"]) and providers.get(provider, {}).get("domain") not in domains:
                raise ValueError("Refresh and choose a matching Music Assistant provider.")


def validate(value, house):
    if (
        not isinstance(value, dict)
        or set(value) != set(empty(house["epoch"]))
        or type(value["version"]) is not int
        or value["version"] != 1
        or type(value["epoch"]) is not int
        or value["epoch"] != house["epoch"]
    ):
        raise ValueError("Unsupported household services configuration. Existing settings are preserved.")
    if type(value["revision"]) is not int or value["revision"] < 0:
        raise ValueError("Refresh household services before saving.")
    people = {p["id"] for p in house["people"]}

    def members(ids):
        return isinstance(ids, list) and all(isinstance(i, str) for i in ids) and len(ids) == len(set(ids)) and set(ids) <= people

    links = value["person_links"]
    if not isinstance(links, dict) or not set(links) <= people or any(not isinstance(n, str) or not ID.fullmatch(n) for n in links.values()):
        raise ValueError("Link configured people to explicit native Person IDs.")
    identities = value["media_identities"]
    if not isinstance(identities, list) or len(identities) > 30:
        raise ValueError("Review service identities.")
    ids = set()
    for row in identities:
        if not isinstance(row, dict) or set(row) != {"id", "name", "service", "scope", "people", "provider_id"}:
            raise ValueError("Unsupported service identity fields. Credentials belong in Music Assistant.")
        if not isinstance(row["id"], str) or not ID.fullmatch(row["id"]) or row["id"] in ids or not text(row["name"], 80):
            raise ValueError("Use distinct service identity IDs and names.")
        ids.add(row["id"])
        if row["service"] != "spotify" or row["scope"] not in {"personal", "shared"} or not members(row["people"]):
            raise ValueError("Keep Spotify accounts separate from people and destinations.")
        if row["scope"] == "personal" and (len(row["people"]) != 1 or next(p for p in house["people"] if p["id"] == row["people"][0])["audience"] != "adult"):
            raise ValueError("Personal Spotify identities require one configured adult. Children use shared identities.")
        if row["provider_id"] is not None and not text(row["provider_id"], 160):
            raise ValueError("Choose a real provider instance or leave login pending.")
    bound = [r["provider_id"] for r in identities if r["provider_id"]]
    if len(bound) != len(set(bound)):
        raise ValueError("Separate service identities cannot share one provider instance.")
    if value["calendar_hub"] is not None and not text(value["calendar_hub"], 100):
        raise ValueError("Choose one native Google integration as the calendar hub.")
    if not isinstance(value["calendars"], list) or len(value["calendars"]) > 100:
        raise ValueError("Review calendar mappings.")
    calendars = set()
    for row in value["calendars"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"entity_id", "category", "people"}
            or not isinstance(row["entity_id"], str)
            or not re.fullmatch(r"calendar\.[a-z0-9_]+", row["entity_id"])
        ):
            raise ValueError("Map native calendar entities without copying events into settings.")
        if (
            row["entity_id"] in calendars
            or row["category"] not in {"household", "person", "school", "timetable", "sport", "work", "other"}
            or not members(row["people"])
        ):
            raise ValueError("Use distinct calendar mappings and explicit household members.")
        if row["category"] == "timetable" and len(row["people"]) != 1:
            raise ValueError("Map a school timetable to exactly one child.")
        calendars.add(row["entity_id"])
    if not isinstance(value["libraries"], list) or len(value["libraries"]) > 30:
        raise ValueError("Review audiobook libraries.")
    for row in value["libraries"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "name", "provider_id", "people", "progress_mode"}
            or not text(row["id"], 64)
            or not text(row["name"], 80)
        ):
            raise ValueError("Use explicit audiobook library records without credentials.")
        if not members(row["people"]) or row["progress_mode"] != "listener_local" or row["provider_id"] is not None and not text(row["provider_id"], 160):
            raise ValueError("Keep audiobook progress separate from Spotify identity.")
    if not isinstance(value["endpoints"], list) or len(value["endpoints"]) > 30:
        raise ValueError("Review endpoint configuration.")
    endpoints = set()
    for row in value["endpoints"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"id", "name", "health_url", "surface_id", "player_id", "voice_entity"}
            or not isinstance(row["id"], str)
            or not ID.fullmatch(row["id"])
            or row["id"] in endpoints
        ):
            raise ValueError("Use distinct endpoint records.")
        endpoints.add(row["id"])
        if not isinstance(row["health_url"], str):
            raise ValueError("Use a local endpoint health URL.")
        url = urlparse(row["health_url"])
        try:
            local = ipaddress.ip_address(url.hostname or "").is_private
        except ValueError:
            local = bool(url.hostname and url.hostname.endswith(".local"))
        if url.scheme != "http" or not local or url.username or url.password or url.path != "/health" or url.query or url.fragment or not text(row["name"], 80):
            raise ValueError("Use the dedicated local endpoint health address without credentials in its URL.")
        if row["surface_id"] not in {s["id"] for s in house["surfaces"]} or any(
            row[k] is not None and not text(row[k], 160) for k in ["player_id", "voice_entity"]
        ):
            raise ValueError("Link the endpoint to its actual display, player and voice entity.")
    if not isinstance(value["directory"], list) or len(value["directory"]) > 50:
        raise ValueError("Review household extensions.")
    numbers = set()
    for row in value["directory"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"extension", "name", "person_id", "endpoint_ids"}
            or not isinstance(row["extension"], str)
            or not re.fullmatch(r"[1-9][0-9]{2,5}", row["extension"])
            or row["extension"] in numbers
        ):
            raise ValueError("Use unique internal extensions.")
        numbers.add(row["extension"])
        if (
            not text(row["name"], 80)
            or row["person_id"] is not None
            and row["person_id"] not in people
            or not isinstance(row["endpoint_ids"], list)
            or any(not isinstance(i, str) for i in row["endpoint_ids"])
            or not set(row["endpoint_ids"]) <= endpoints
        ):
            raise ValueError("Phone extensions, people and endpoint devices are separate relationships.")
    region = value["region"]
    if region is not None and (
        not isinstance(region, dict)
        or set(region) != {"name", "country_code", "search_terms"}
        or not text(region["name"], 100)
        or not isinstance(region["country_code"], str)
        or not re.fullmatch("[A-Z]{2}", region["country_code"])
        or not isinstance(region["search_terms"], list)
        or len(region["search_terms"]) > 12
        or any(not text(t, 80) for t in region["search_terms"])
    ):
        raise ValueError("Use a configured household region for radio discovery.")
    return copy.deepcopy(value)


def load(store, house):
    value = store.read(path(store), None)
    if value is None:
        return empty(house["epoch"])
    if not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1:
        raise ValueError("Unsupported household services configuration. Existing settings are preserved.")
    if type(value.get("epoch")) is int and value["epoch"] != house["epoch"]:
        return empty(house["epoch"])
    return validate(value, house)


def save(store, house, body):
    current = load(store, house)
    if body.get("revision") != current["revision"]:
        raise ValueError("Household services changed. Refresh before saving.")
    value = validate(body, house)
    if value != current:
        value["revision"] += 1
        private_write(path(store), value)
    return value


def connections(store):
    value = store.read(path(store, "endpoint-connections.json"), {})
    if not isinstance(value, dict) or any(not isinstance(k, str) or not isinstance(v, str) or len(v) < 32 for k, v in value.items()):
        raise ValueError("Endpoint credentials need checking; existing data is preserved.")
    return value


def bind(store, config, identifier, key):
    if identifier not in {e["id"] for e in config["endpoints"]} or not isinstance(key, str) or not 32 <= len(key) <= 256 or any(ord(c) < 33 for c in key):
        raise ValueError("Choose a configured endpoint and its dedicated health key.")
    keys = connections(store)
    keys[identifier] = key
    private_write(path(store, "endpoint-connections.json"), keys)


def endpoint_entity(identifier):
    return "sensor.home_starter_endpoint_" + digest(identifier)[:12]


async def poll_endpoints(session, core, store):
    house = store.load()
    config = load(store, house)
    if not config["endpoints"]:
        return
    keys = connections(store)
    states = {s["entity_id"]: s for s in await core.states()}
    for endpoint in config["endpoints"]:
        if endpoint["id"] not in keys:
            continue
        now = datetime.now(UTC)
        owner = {"id": endpoint["id"], "epoch": house["epoch"]}
        entity = endpoint_entity(endpoint["id"])
        old = states.get(entity)
        if old and (old.get("attributes", {}).get("home_starter_endpoint") or {}).get("id") != endpoint["id"]:
            raise ValueError("Endpoint health address is already owned by another source.")
        attrs = {
            "friendly_name": endpoint["name"] + " health",
            "home_starter_endpoint": owner,
            "checked_at": now.isoformat(),
            "valid_until": (now + timedelta(seconds=75)).isoformat(),
        }
        online = False
        try:
            async with session.get(
                endpoint["health_url"],
                headers={"Authorization": "Bearer " + keys[endpoint["id"]]},
                timeout=aiohttp.ClientTimeout(total=4),
                allow_redirects=False,
            ) as response:
                if response.status != 200 or response.content_type != "application/json":
                    raise ValueError("Endpoint unavailable")
                raw = await response.content.read(16385)
                if len(raw) > 16384:
                    raise ValueError("Unsupported health response")
                import json

                value = json.loads(raw)
            stamp = datetime.fromisoformat(value["checked_at"])
            if value.get("version") != 1 or value.get("online") is not True or not timedelta(seconds=-5) <= datetime.now(UTC) - stamp <= timedelta(seconds=45):
                raise ValueError("Stale endpoint feedback")
            for field in ["browser_alive", "dashboard_open", "authenticated_display_verified"]:
                if type(value.get(field)) is not bool:
                    raise ValueError("Unsupported health status")
                attrs[field] = value[field]
            for field in ["voice_connected", "voice_muted"]:
                if field in value:
                    if type(value[field]) is not bool:
                        raise ValueError("Unsupported voice status")
                    attrs[field] = value[field]
            for field in ["cpu_temperature", "load_1m", "storage_used_percent", "storage_free_gb", "uptime_seconds"]:
                if not number(value.get(field)) or value[field] < 0:
                    raise ValueError("Unsupported health metric")
                attrs[field] = value[field]
            for field in ["display_service", "audio_service", "voice_service", "updates_check", "last_boot"]:
                if not text(value.get(field), 100):
                    raise ValueError("Unsupported health status")
                attrs[field] = value[field]
            online = True
        except (aiohttp.ClientError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            attrs["issue"] = "Device offline or health feedback unavailable"
        await core.context_state(entity, {"state": "online" if online else "offline", "attributes": attrs})


def status(config, integrations, states, music):
    rows = []
    entries = {e["entry_id"]: e for e in integrations}
    providers = {p["id"]: p for p in (music or {}).get("providers", [])}
    google = entries.get(config["calendar_hub"], {})
    observed = {s["entity_id"]: s for s in states}
    missing_calendars = [
        r["entity_id"] for r in config["calendars"] if observed.get(r["entity_id"], {}).get("state", "unavailable") in {"unavailable", "unknown"}
    ]
    rows.append(
        {
            "name": "Calendar hub",
            "status": "Ready"
            if google.get("domain") == "google" and google.get("state") == "loaded" and config["calendars"] and not missing_calendars
            else "Needs login"
            if not google
            else "Needs setup",
            "detail": str(len(config["calendars"]))
            + " mapped calendars; one Google integration"
            + ("; missing/unavailable calendars need checking" if missing_calendars else ""),
            "route": "/config/integrations/integration/google",
        }
    )
    for identity in config["media_identities"]:
        provider = providers.get(identity["provider_id"], {})
        ready = provider.get("domain") == "spotify" and provider.get("available") and provider.get("enabled")
        rows.append(
            {
                "name": identity["name"] + " · Spotify",
                "status": "Needs verification" if ready else "Needs login" if not provider else "Provider unavailable",
                "detail": identity["scope"].capitalize() + " service identity; independent of speaker destination",
                "route": "#music",
            }
        )
    for kind, domains in [
        ("Radio", {"radiobrowser", "abc_radio_network"}),
        ("Podcasts", {"itunes_podcasts", "podcastfeed", "podcast_index", "gpodder", "audiobookshelf"}),
        ("Audiobooks", {"audiobookshelf", "audible", "storytel"}),
        ("Ambient sounds", {"ambient_sounds", "rainymood"}),
    ]:
        available = any(p.get("domain") in domains and p.get("available") and p.get("enabled") for p in providers.values())
        rows.append(
            {
                "name": kind,
                "status": "Ready" if available else "Needs setup",
                "detail": "Provider available; playback paths require their own checks"
                if available
                else "Connect a supported library/source in Music Assistant",
                "route": "#music",
            }
        )
    now = datetime.now(UTC)
    for endpoint in config["endpoints"]:
        state = observed.get(endpoint_entity(endpoint["id"]), {})
        attrs = state.get("attributes", {})
        try:
            fresh = datetime.fromisoformat(attrs["valid_until"]) > now and attrs["home_starter_endpoint"] == {"id": endpoint["id"], "epoch": config["epoch"]}
        except (ValueError, KeyError, TypeError):
            fresh = False
        rows.append(
            {
                "name": endpoint["name"],
                "status": ("Microphone muted" if attrs.get("voice_muted", True) else "Ready")
                if fresh
                and state.get("state") == "online"
                and attrs.get("browser_alive")
                and attrs.get("dashboard_open")
                and attrs.get("authenticated_display_verified")
                and attrs.get("audio_service") == "active"
                and attrs.get("voice_service") == "active"
                and attrs.get("voice_connected") is True
                and str(endpoint.get("player_id") or "").startswith("media_player.")
                and observed.get(endpoint["player_id"], {}).get("state", "unavailable") not in {"unknown", "unavailable"}
                and str(endpoint.get("voice_entity") or "").startswith("assist_satellite.")
                and observed.get(endpoint["voice_entity"], {}).get("state", "unavailable") not in {"unknown", "unavailable"}
                else "Device offline"
                if not fresh or state.get("state") == "offline"
                else "Needs login"
                if not attrs.get("authenticated_display_verified")
                else "Needs setup",
                "detail": "Browser: "
                + str(attrs.get("display_service", "unknown"))
                + " · audio: "
                + str(attrs.get("audio_service", "unknown"))
                + " · voice: "
                + str(attrs.get("voice_service", "unknown"))
                + (" · microphone muted" if attrs.get("voice_muted", True) else " · microphone enabled")
                + "; native player and satellite bindings required",
                "route": "#surfaces",
            }
        )
    rows.append(
        {
            "name": "Internal calling",
            "status": "Needs setup",
            "detail": str(len(config["directory"])) + " planned extensions; PBX installation is not registration/call proof",
            "route": "/config/integrations/integration/sip_core",
        }
    )
    return rows
