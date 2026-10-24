"""Stateless media identity shared by household projection and native discovery."""

import hashlib
import json


def record_ids(row):
    uris = {row.get("uri")}
    for mapping in row.get("provider_mappings", []):
        if mapping.get("provider_instance") and mapping.get("item_id"):
            uris.add(mapping["provider_instance"] + "://" + row["media_type"] + "/" + str(mapping["item_id"]))
    return {hashlib.sha256(json.dumps(uri, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24] for uri in uris if isinstance(uri, str)}
