"""Provider-neutral ambient entries from already installed, reviewed free sources."""

import re
import time

from .listnr import ambient_group
from .music_runtime import digest


def native_entries(items, providers, server):
    known = {p["id"]: p["domain"] for p in providers if p.get("domain") in {"ambient_sounds", "rain_mood"} and p.get("available")}
    result = []
    for item in items:
        provider = item.get("provider")
        identity = item.get("item_id")
        if (
            provider not in known
            or item.get("media_type") != "sound_effect"
            or not isinstance(identity, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity)
        ):
            continue
        label = str(item.get("name") or "Ambient")
        group = ambient_group(label) or "nature"
        result.append(
            {
                "id": "ambient:" + digest([known[provider], identity])[:24],
                "provider": "music_assistant",
                "source": known[provider],
                "name": label,
                "category": "ambient",
                "subcategory": group,
                "kind": "sound_effect",
                "uri": item["uri"],
                "selected": True,
                "availability": "active",
                "local_rank": 0,
                "server": server,
                "last_discovered": time.time(),
            }
        )
    return result
