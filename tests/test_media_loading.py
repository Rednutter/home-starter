import asyncio
import json

import pytest
from homestarter.catalogue_preview import MetadataPreview


@pytest.mark.asyncio
async def test_bootstrap_does_not_wait_for_library_and_reads_are_single_flight():
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def command(name, **args):
        calls.append(name)
        if name == "providers":
            return [{"instance_id": "source", "domain": "abc_radio_network", "type": "music", "available": True}]
        if name == "auth/users":
            return [{"display_name": "House", "user_id": "house", "provider_filter": ["source"]}]
        if name.endswith("/library_items"):
            entered.set()
            await finish.wait()
            return []
        if name == "music/browse":
            return []
        raise AssertionError(name)

    async def saved(path):
        return {"favorites": [], "recent": [], "browse": True}

    bridge = MetadataPreview(command, saved, None, {"epoch": 1, "people": []}, "panel")
    await bridge.prepare(defer_catalogue=True)
    assert calls == ["providers"]
    body = {"profile": "house", "generation": 1, "command": "music/artists/library_items", "args": {}}
    first = asyncio.create_task(bridge.read("browser", body))
    await entered.wait()
    second = asyncio.create_task(bridge.read("browser", body))
    radio = await bridge.read("browser", {**body, "command": "household/discovery", "args": {"category": "radio", "query": "", "limit": 24}})
    assert radio["items"] == [] and not first.done()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    assert not bridge.catalogue_task.cancelled()
    finish.set()
    assert await second == []
    assert sum(name.endswith("/library_items") for name in calls) == 3


@pytest.mark.asyncio
async def test_missing_mapping_does_not_start_catalogue_and_change_during_load_fails_closed():
    filters, calls = [], []
    entered, finish = asyncio.Event(), asyncio.Event()

    async def command(name, **args):
        calls.append(name)
        if name == "providers":
            return [{"instance_id": "source", "domain": "example", "type": "music", "available": True}]
        if name == "auth/users":
            return [{"display_name": "House", "user_id": "house", "provider_filter": list(filters)}]
        entered.set()
        await finish.wait()
        return []

    async def saved(path):
        return {"favorites": [], "recent": [], "browse": True}

    bridge = MetadataPreview(command, saved, None, {"epoch": 1, "people": []}, "panel")
    await bridge.prepare(defer_catalogue=True)
    body = {"profile": "house", "generation": 1, "command": "music/artists/library_items", "args": {}}
    with pytest.raises(PermissionError):
        await bridge.read("browser", body)
    assert not any(name.startswith("music/") for name in calls)
    filters.append("source")
    reading = asyncio.create_task(bridge.read("browser", body))
    await entered.wait()
    filters.clear()
    finish.set()
    with pytest.raises(PermissionError):
        await reading
    assert not bridge.offered


@pytest.mark.asyncio
async def test_discovery_pages_do_not_requery_or_issue_capabilities_for_hidden_rows():
    searches = []

    async def command(name, **args):
        if name == "auth/users":
            return [{"display_name": "House", "user_id": "house", "provider_filter": ["source"]}]
        assert name == "music/search"
        searches.append(name)
        return {
            "radios": [
                {
                    "provider": "source",
                    "item_id": str(n),
                    "uri": "source://radio/" + str(n),
                    "media_type": "radio",
                    "name": "Example " + str(n),
                    "provider_mappings": [{"provider_instance": "source", "provider_domain": "radiobrowser", "item_id": str(n), "available": True}],
                    "metadata": {"images": []},
                }
                for n in range(1000)
            ]
        }

    bridge = MetadataPreview(command, None, None, {"epoch": 1, "people": []}, "panel")
    bridge.providers = {"source": {"instance_id": "source", "domain": "radiobrowser", "available": True}}
    bridge.saved = {"house": {"favorites": [], "recent": []}}
    bridge.discovery_children = {"house": False}
    body = {"profile": "house", "generation": 1, "command": "household/discovery", "args": {"category": "radio", "query": "Example", "offset": 0, "limit": 24}}
    first = await bridge.read("browser", body)
    assert len(first["items"]) == 24 and first["total"] == 1000
    assert len(bridge.offered) == 24 and len(json.dumps(first)) < 50000
    second = await bridge.read("browser", {**body, "args": {**body["args"], "offset": 24}})
    assert len(second["items"]) == 24 and second["offset"] == 24
    assert {r["uri"] for r in first["items"]}.isdisjoint({r["uri"] for r in second["items"]})
    assert len(searches) == 1 and len(bridge.offered) == 48
    for args in [{"limit": 101}, {"limit": True}, {"offset": -1}, {"offset": True}]:
        with pytest.raises(PermissionError):
            await bridge.read("browser", {**body, "args": {**body["args"], **args}})
