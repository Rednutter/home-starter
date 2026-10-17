"""Reconcile managed LiSTNR radio through MA controllers, keeping library IDs."""

import asyncio
import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .spotify_leases import write_private_json


class RadioImporter:
    def __init__(self, mass):
        self.mass = mass
        self.path = Path(mass.storage_path) / "home-starter-radio.json"
        self.records = json.loads(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(self.records, dict):
            raise ValueError("Managed radio state needs review.")
        self.lock = asyncio.Lock()

    def install(self):
        ctrl = self.mass.music.radio
        original = ctrl._get_library_item_by_match

        async def match(item):
            description = getattr(getattr(item, "metadata", None), "description", "") or ""
            if any(line.startswith("Home Starter source: listnr:") for line in description.splitlines()):
                for mapping in item.provider_mappings:
                    existing = await ctrl.get_library_item_by_prov_id(mapping.item_id, mapping.provider_instance)
                    if existing:
                        return int(existing.item_id)
                return None  # Never merge two managed stations solely by display name.
            return await original(item)

        ctrl._get_library_item_by_match = match

    async def upsert(self, station: dict) -> dict:
        from music_assistant_models.enums import MediaType
        from music_assistant_models.media_items import ProviderMapping

        identity, url = station.get("id"), station.get("url")
        parsed = urlsplit(url or "")
        if (
            not isinstance(identity, str)
            or not identity.startswith("listnr:")
            or parsed.scheme != "https"
            or not (parsed.hostname or "").endswith(".scastream.com.au")
        ):
            raise ValueError("Choose a validated public LiSTNR station.")
        if parsed.username or parsed.password or set(parse_qs(parsed.query)) - {"dist"} or not station.get("name"):
            raise ValueError("Radio delivery sessions cannot be stored as station URLs.")
        async with self.lock:
            builtin = self.mass.get_provider("builtin")
            ctrl = self.mass.music.radio
            record = self.records.get(identity, {})
            marker = "Home Starter source: " + identity

            def owned(item):
                return marker in (item.metadata.description or "").splitlines()

            existing = None
            if record.get("library_id"):
                existing = await ctrl.get_library_item_by_prov_id(str(record["library_id"]), "library")
                if existing and not owned(existing):
                    existing = None  # Reused DB ID after a rebuild must never update unrelated radio.
            if existing is None:
                existing = await ctrl.get_library_item_by_prov_id(url, builtin.instance_id)
            if existing is None:
                offset = 0
                while True:
                    batch = await ctrl.library_items(limit=500, offset=offset, summary=False)
                    matches = [r for r in batch if owned(r)]
                    if matches:
                        existing = matches[0]
                        break
                    if len(batch) < 500:
                        break
                    offset += len(batch)
            previous_url = record.get("url")
            if not previous_url and existing and owned(existing):
                previous_url = next((m.item_id for m in existing.provider_mappings if m.provider_instance == builtin.instance_id and m.item_id != url), None)
            if existing:
                # Add the replacement mapping before builtin sync can see a new URL.
                mapping = ProviderMapping(item_id=url, provider_domain="builtin", provider_instance=builtin.instance_id, available=True)
                await ctrl.add_provider_mappings(existing.item_id, [mapping])
            fresh = await builtin.add_radio(url, station["name"], station.get("artwork"))
            if existing:
                update = copy.deepcopy(existing)
                update.name = fresh.name
                update.sort_name = fresh.sort_name
                update.metadata.images = fresh.metadata.images
                update.provider_mappings = {*existing.provider_mappings, *fresh.provider_mappings}
            else:
                update = fresh
            if marker not in (update.metadata.description or ""):
                update.metadata.description = ((update.metadata.description or "") + "\n" + marker).strip()
            item = await ctrl.update_item_in_library(existing.item_id, update, overwrite=True) if existing else await ctrl.add_item_to_library(update)
            # Persist identity before retiring the old URL; reruns recover partial work.
            self.records[identity] = {
                "library_id": item.item_id,
                "url": url,
                "previous_url": previous_url if previous_url != url else record.get("previous_url"),
            }
            write_private_json(self.path, self.records)
            old = self.records[identity].get("previous_url")
            if old and old != url:
                await builtin.library_remove(old, MediaType.RADIO)  # builtin's local URL list only; no network account.
                await ctrl.remove_provider_mapping(item.item_id, builtin.instance_id, old)
                self.records[identity].pop("previous_url", None)
                write_private_json(self.path, self.records)
            return {"state": "connected", "uri": item.uri, "library_id": item.item_id, "identity": identity}
