"""Refresh the media script on unmodified owned touch dashboards only."""

import copy
from pathlib import Path

from .core import CoreError
from .surfaces import fingerprint


def update_media(config):
    result = copy.deepcopy(config)
    template = result.get("button_card_templates", {}).get("home_starter_page", {})
    body = template.get("custom_fields", {}).get("body")
    if not isinstance(body, str):
        return result
    start = body.find("// Calls use the signed-in HA ingress identity;")
    end = body.find("\nconst controls = focus.controls || [], players = music?.players || focus.players || [];", start)
    if start < 0 or end < 0:
        raise ValueError("The household media template needs compatibility review.")
    source = (Path(__file__).parent / "static" / "panel-music.js").read_text(encoding="utf-8")
    template["custom_fields"]["body"] = body[:start] + source.rstrip() + "\n" + body[end:]
    return result


async def refresh(core, store):
    records = store.read(store.publication_path, {})
    issues = []
    async with core.websocket() as ws:
        for url, record in records.items():
            try:
                current = await ws.command("lovelace/config", url_path=url, force=True)
                if fingerprint(current) != record.get("fingerprint"):
                    issues.append("Existing dashboard edits require review before updating media controls.")
                    continue
                updated = update_media(current)
                if updated == current:
                    continue
                await ws.command("lovelace/config/save", url_path=url, config=updated)
                readback = await ws.command("lovelace/config", url_path=url, force=True)
                if readback != updated:
                    raise ValueError("Media controls readback needs attention.")
                records[url] = {**record, "fingerprint": fingerprint(readback)}
                store.write(store.publication_path, records)
            except (CoreError, ValueError, KeyError, TypeError):
                issues.append("An owned dashboard's media controls need attention.")
    return issues
