import asyncio

import pytest
from homestarter.discovery_seeds import RADIO_SEEDS, reviewed_evidence
from homestarter.media_discovery import MediaDiscovery
from homestarter.metadata_projection import approved_image, native_artwork_path


@pytest.mark.asyncio
async def test_landing_resolves_exact_local_identities_when_browse_fails():
    calls = []

    async def command(name, **args):
        calls.append((name, args))
        if name == "music/browse":
            await asyncio.sleep(2)
        seed = next(s for s in RADIO_SEEDS if s[0] == args["search_query"])

        def row(identity):
            return {
                "item_id": identity,
                "uri": "radio://radio/" + identity,
                "name": seed[0],
                "media_type": "radio",
                "provider_mappings": [{"provider_domain": "radiobrowser", "provider_instance": "radio", "item_id": identity}],
            }

        return {"radios": [row(seed[1]), row("unrelated-same-title")]}

    provider = {"radio": {"instance_id": "radio", "domain": "radiobrowser", "available": True}}
    result = await MediaDiscovery(command, provider, timeout=0.5, region={"name": "Albury-Wodonga"}).find("radio", "", ["radio"])
    assert {r["item_id"] for r in result["items"]} == {s[1] for s in RADIO_SEEDS}
    assert all(r["household_discovery"]["local"] for r in result["items"])
    assert result["sources"][0]["state"] == "partial"
    assert all(name in {"music/search", "music/browse"} for name, _ in calls)
    assert "language" not in next(r for r in result["items"] if r["item_id"] == RADIO_SEEDS[2][1])["household_discovery"]


def test_reviewed_locality_requires_exact_provider_and_region():
    identity = RADIO_SEEDS[0][1]
    row = {"provider_mappings": [{"provider_domain": "radiobrowser", "item_id": identity}]}
    assert reviewed_evidence(row, {"name": "Albury-Wodonga"})["local"]
    assert "local" not in reviewed_evidence(row, {"name": "Melbourne"})
    assert reviewed_evidence({"name": "Triple M The Border"}, {"name": "Albury"}) == {}
    assert reviewed_evidence({"provider_mappings": [{"provider_domain": "other", "item_id": identity}]}, {"name": "Albury"}) == {}


def test_catalogue_artwork_uses_exact_hosts_and_native_proxy_ids():
    for host in ["images.ctfassets.net", "is1-ssl.mzstatic.com", "www.abc.net.au"]:
        image = {"provider": "builtin", "path": "https://" + host + "/public-cover.jpg", "proxy_id": "a" * 64}
        assert native_artwork_path(image) == "/imageproxy/" + "a" * 64 + "?size=512"
        assert not native_artwork_path({**image, "proxy_id": "../private"})
        assert not approved_image({**image, "path": "https://" + host + ".example.invalid/image"})
        assert not approved_image({**image, "path": "https://user@" + host + "/image"})
        assert not approved_image({**image, "path": "http://" + host + "/image"})


@pytest.mark.asyncio
async def test_discovery_cache_is_bound_to_profile_policy_and_native_images(monkeypatch):
    from homestarter import catalogue_preview

    filters = ["radio"]
    searches = []
    clock = [0]
    monkeypatch.setattr(catalogue_preview.time, "monotonic", lambda: clock[0])

    async def command(name, **args):
        if name == "auth/users":
            return [{"display_name": name, "user_id": name, "provider_filter": filters} for name in ["House", "Example One"]]
        searches.append((name, args))
        if clock[0] >= 300:
            raise RuntimeError("Synthetic provider offline")
        return {
            "radios": [
                {
                    "uri": "radio://radio/one",
                    "provider": "radio",
                    "item_id": "one",
                    "name": "Example station",
                    "media_type": "radio",
                    "provider_mappings": [{"provider_instance": "radio", "provider_domain": "radiobrowser", "item_id": "one", "available": True}],
                    "metadata": {
                        "images": [{"type": "thumb", "provider": "builtin", "path": "https://images.ctfassets.net/example.jpg", "proxy_id": "a" * 64}]
                    },
                }
            ]
        }

    bridge = catalogue_preview.MetadataPreview(command, None, None, {"epoch": 1, "people": [{"id": "one", "name": "Example One"}]}, "panel")
    bridge.providers = {"radio": {"instance_id": "radio", "domain": "radiobrowser", "available": True}}
    bridge.saved = {p: {"favorites": [], "recent": []} for p in ["house", "one"]}
    bridge.discovery_children = {"house": False, "one": False}
    body = {"profile": "house", "generation": 1, "command": "household/discovery", "args": {"category": "radio", "query": "Example"}}
    first = await bridge.read("browser", body)
    old_image = first["items"][0]["metadata"]["images"][0]["path"].split("/")[-1]
    await bridge.read("browser", body)
    assert len(searches) == 1  # Fresh cache never reissues provider reads.
    clock[0] = 301
    cached = await bridge.read("browser", body)
    assert cached["items"] and cached["sources"][0]["state"] == "cached"
    personal = await bridge.read("browser", {**body, "profile": "one", "generation": 2})
    assert not personal["items"]  # Another person's cache is never a fallback.
    with pytest.raises(PermissionError):
        bridge.ledger.reference("browser", old_image, "unrelated-policy", ["radio"])
    filters.clear()
    with pytest.raises(PermissionError):
        await bridge.read("browser", body)
