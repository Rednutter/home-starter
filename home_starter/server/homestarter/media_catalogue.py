"""Declarative household radio/ambient selections and recoverable MA imports."""

import asyncio
import time
from pathlib import Path

from . import household_services, postal_region
from .ambient_catalogue import native_entries
from .listnr import CatalogueError, LiSTNR, distance, regional_score
from .music_runtime import MusicRuntimeError, private_write


class MediaCatalogue:
    def __init__(self, runtime, core, store, resolver=None):
        self.runtime, self.core, self.store = runtime, core, store
        self.resolver = resolver or LiSTNR()
        self.path = Path(store.path).parent / "media-catalogue.json"
        self.lock = asyncio.Lock()
        self.next_check = 0

    def load(self):
        value = self.store.read(self.path, None)
        house = self.store.load()
        if value is None or isinstance(value, dict) and value.get("epoch") != house["epoch"]:
            return {
                "version": 1,
                "epoch": house["epoch"],
                "items": {},
                "defaults_chosen": False,
                "selection_mode": "defaults",
                "local_lookup_allowed": False,
                "local_lookup_state": "ready_for_consent",
                "discovered_at": 0,
                "issue": None,
            }
        if not isinstance(value, dict) or value.get("version") != 1 or not isinstance(value.get("items"), dict):
            raise MusicRuntimeError("The saved radio catalogue needs checking. Existing stations are preserved.")
        return value

    def save(self, value):
        private_write(self.path, value)

    async def consent(self, allowed):
        if type(allowed) is not bool:
            raise ValueError("Choose whether approximate postcode lookup is allowed.")
        async with self.lock:
            data = self.load()
            data.update(local_lookup_allowed=allowed, local_lookup_state="preparing" if allowed else "intentionally_skipped", discovered_at=0)
            self.save(data)

    async def sync(self, selected=None, force=False):
        async with self.lock:
            data = self.load()
            house = self.store.load()
            region = household_services.load(self.store, house)["region"]
            if force or time.time() - data["discovered_at"] > 86400 or not data["items"]:
                try:
                    rows = await self.resolver.discover()
                    home = await self.core.config()  # Local ranking only; home coordinates never leave HA.
                    nearby = set()
                    if data.get("local_lookup_allowed") and region:
                        try:
                            code = await postal_region.postcode(region["country_code"], home, region["search_terms"])
                            nearby = await self.resolver.nearby(code)
                            data["local_lookup_state"] = "connected" if nearby else "connected_but_incomplete"
                        except (CatalogueError, ValueError, OSError):
                            data["local_lookup_state"] = "needs_attention"
                    found = set()
                    for row in rows:
                        found.add(row["id"])
                        old = data["items"].get(row["id"], {})
                        km = distance(row, home)
                        row["local_rank"] = max(0, 300 - km) * 100 + regional_score(row, region) if km is not None and region else regional_score(row, region)
                        if row["id"] in nearby:
                            row["local_rank"] += 100000
                        data["items"][row["id"]] = {**old, **row, "selected": old.get("selected", False)}
                    for identity in data["items"].keys() - found:
                        if data["items"][identity]["provider"] == "listnr":
                            data["items"][identity]["availability"] = "upstream_missing"
                    data.update(discovered_at=time.time(), issue=None)
                except (CatalogueError, OSError, ValueError):
                    data["issue"] = "Catalogue discovery is unavailable. Saved stations are preserved."
            if selected is not None:
                if not isinstance(selected, list) or len(selected) > 50 or len(set(selected)) != len(selected) or set(selected) - data["items"].keys():
                    raise ValueError("Choose stations from the discovered catalogue.")
                for row in data["items"].values():
                    row["selected"] = row["id"] in selected
                data["defaults_chosen"] = True
                data["selection_mode"] = "manual"
            if data.get("selection_mode", "defaults") == "defaults" and data["items"] and not data["issue"]:
                for row in data["items"].values():
                    if row["provider"] == "listnr":
                        row["selected"] = False
                local = sorted(
                    (r for r in data["items"].values() if r["category"] == "radio" and r["local_rank"] >= 1000), key=lambda r: (-r["local_rank"], r["id"])
                )
                for row in local[:6]:
                    row["selected"] = True
                for group in ("rain", "noise", "sleep", "focus", "nature"):
                    ambient = sorted((r for r in data["items"].values() if r["category"] == "ambient" and r["subcategory"] == group), key=lambda r: r["id"])
                    if ambient:
                        ambient[0]["selected"] = True
                data["defaults_chosen"] = True
            self.save(data)  # Selections survive partial import, MA reconnect and process restart.
            connection = self.runtime.connection()
            endpoint = await self.runtime.endpoint() if connection else None
            if connection:
                try:
                    snapshot = await self.runtime.snapshot()
                    sounds = await self.runtime.command(endpoint, connection, "music/sound_effects")
                    entries = native_entries(sounds, snapshot.get("providers", []), connection["server_id"])
                    found = {r["id"] for r in entries}
                    for row in entries:
                        row["selected"] = data["items"].get(row["id"], {}).get("selected", data.get("selection_mode", "defaults") == "defaults")
                        data["items"][row["id"]] = row
                    for identity in data["items"].keys() - found:
                        if data["items"][identity]["provider"] == "music_assistant":
                            data["items"][identity]["availability"] = "temporarily_unavailable"
                    self.save(data)
                except MusicRuntimeError:
                    data["issue"] = "Native ambient sources could not be refreshed. Saved choices are preserved."
            for identity, row in data["items"].items():
                if row["provider"] != "listnr" or not row["selected"] or row["availability"] == "upstream_missing":
                    continue
                if (
                    not force
                    and row.get("server") == (connection or {}).get("server_id")
                    and row.get("uri")
                    and time.time() - row.get("last_validated", 0) < 300
                ):
                    continue
                try:
                    resolution = await self.resolver.validate(await self.resolver.resolve(identity))
                    if connection is None:
                        raise MusicRuntimeError("Connect Music Assistant first.")
                    imported = await self.runtime.control(
                        endpoint,
                        connection,
                        "homestarter/radio_upsert",
                        station={"id": identity, "name": row["name"], "url": resolution["url"], "artwork": row.get("artwork")},
                    )
                    if imported.get("state") != "connected":
                        raise MusicRuntimeError("Radio import could not be confirmed.")
                    row.update(
                        uri=imported["uri"],
                        server=connection["server_id"],
                        stream_url=resolution["url"],
                        stream_format=resolution["format"],
                        codec=resolution["codec"],
                        bitrate=resolution["bitrate"],
                        last_resolved=resolution["resolved_at"],
                        last_validated=resolution["validated_at"],
                        availability="active",
                        issue=None,
                    )
                except CatalogueError as exc:
                    row.update(availability=str(exc), issue="This station is unavailable. Other stations remain available.")
                except (MusicRuntimeError, OSError, ValueError, TypeError, KeyError):
                    row.update(availability="connected_but_incomplete", issue="This station could not be imported. Retry media setup.")
                self.save(data)
            return self.view(data, admin=True)

    def view(self, data=None, admin=False):
        data = data or self.load()
        result = {
            "epoch": data["epoch"],
            "issue": data["issue"],
            "discovered": len(data["items"]),
            "selected": sum(r["selected"] for r in data["items"].values()),
            "ready": sum(r["selected"] and r.get("uri") is not None and r["availability"] == "active" for r in data["items"].values()),
            "items": [],
            "local_lookup_allowed": data.get("local_lookup_allowed", False),
            "local_lookup_state": data.get("local_lookup_state", "ready_for_consent"),
        }
        for row in sorted(data["items"].values(), key=lambda r: (-r.get("local_rank", 0), r["name"])):
            if not admin and (not row["selected"] or not row.get("uri") or row["availability"] != "active"):
                continue
            fields = ("id", "name", "category", "subcategory", "kind", "artwork", "availability", "selected", "local_rank", "uri")
            result["items"].append({k: row.get(k) for k in fields} if not admin else dict(row))
        return result

    def item(self, identity):
        row = self.load()["items"].get(identity)
        if not row or not row["selected"] or not row.get("uri") or row["availability"] != "active":
            raise ValueError("Choose an available household station.")
        return row

    def choose(self, category, group=None):
        rows = [r for r in self.view()["items"] if r["category"] == category and (not group or r["subcategory"] == group)]
        if not rows:
            raise ValueError("No matching household station is ready. Retry media setup.")
        return sorted(rows, key=lambda r: (r.get("kind") != "sound_effect", -r.get("local_rank", 0), r["name"]))[0]

    async def tick(self):
        if time.monotonic() < self.next_check or not self.runtime.connection():
            return
        self.next_check = time.monotonic() + 300
        await self.sync()
