import asyncio

import pytest
from homestarter.media_discovery import MediaDiscovery, evidence_for, radio_rank


@pytest.mark.asyncio
async def test_discovery_sources_fail_independently_and_do_not_write():
    calls = []

    async def command(name, **args):
        calls.append(name)
        assert name == "music/search"
        if args["providers"] == ["slow"]:
            await asyncio.sleep(1)
        return {"radios": [{"name": "Example radio", "media_type": "radio", "country_code": "AU", "language": "en"}]}

    providers = {key: {"instance_id": key, "domain": "radiobrowser", "available": True} for key in ["fast", "slow", "forbidden"]}
    service = MediaDiscovery(command, providers, timeout=0.01)
    result = await service.find("radio", "example", ["fast", "slow"])
    assert len(result["items"]) == 1
    assert {s["state"] for s in result["sources"]} == {"ready", "unavailable"}
    assert calls == ["music/search", "music/search"]
    with pytest.raises(PermissionError):
        await service.find("radio", "example", [])
    assert not (await service.find("radio", "example", ["missing"]))["items"]


def test_radio_ranking_uses_explicit_evidence_only():
    rows = [
        {"name": name, "household_discovery": evidence}
        for name, evidence in [("Other", {}), ("English", {"language": "en"}), ("Australian", {"country": "AU"}), ("Local", {"local": True})]
    ]
    assert [r["name"] for r in sorted(rows, key=radio_rank)] == ["Local", "Australian", "English", "Other"]


@pytest.mark.asyncio
async def test_podcast_unknown_suitability_not_presented_to_children():
    async def command(name, **args):
        return {
            "podcasts": [
                {"media_type": "podcast", "name": "Unknown", "metadata": {}},
                {"media_type": "podcast", "name": "Example", "metadata": {"explicit": False, "description_language": "en"}},
            ]
        }

    service = MediaDiscovery(command, {"pod": {"instance_id": "pod", "domain": "itunes_podcasts", "available": True}})
    result = await service.find("podcast", "example", ["pod"], child=True)
    assert [r["name"] for r in result["items"]] == ["Example"]
    assert not result["personalised"]


@pytest.mark.asyncio
async def test_border_keyword_does_not_establish_locality():
    async def command(name, **args):
        return {"radio": [{"media_type": "radio", "name": "Triple M The Border"}]}

    providers = {"radio": {"instance_id": "radio", "domain": "radiobrowser", "available": True}}
    local = await MediaDiscovery(command, providers, region={"name": "Albury–Wodonga"}).find("radio", "Border", ["radio"])
    assert "local" not in local["items"][0]["household_discovery"]
    unknown = await MediaDiscovery(command, providers).find("radio", "Border", ["radio"])
    assert "local" not in unknown["items"][0]["household_discovery"]


def test_actual_region_language_popularity_fields_and_unknown_labels():
    region = {"id": "example-border", "search_terms": ["Albury", "Wodonga"]}
    row = {"uri": "radio://radio/example", "name": "Unrelated title", "countrycode": "AU", "state": "Albury NSW", "languagecodes": "eng", "clickcount": 12}
    evidence = evidence_for(row, region=region)
    assert evidence["local"] and evidence["language"] == "en"
    assert evidence["popularity"] == 12 and evidence["locality_basis"] == "directory-station-region-field"
    assert "local" not in evidence_for({**row, "state": "Victoria"}, region=region)
    assert "local" not in evidence_for({**row, "countrycode": "US"}, region=region)
    assert evidence_for({"name": "Albury English Popular"}, region=region)["label"] == "Region and language unverified"
    assert "popularity" not in evidence_for({"clickcount": float("nan")})
    assert "popularity" not in evidence_for({"clickcount": 10**1000})
    assert evidence_for({"metadata": {"languages": ["en-AU"], "popularity": 8}})["language"] == "en"
    assert evidence_for({"uri": row["uri"]}, region=region, curated={row["uri"]: {"region_id": "other", "verified": True}}).get("local") is None


@pytest.mark.asyncio
async def test_directory_fields_join_by_uuid_and_failure_retains_unverified_results():
    identity = "00000000-0000-4000-8000-000000000001"

    async def command(name, **args):
        return {"radio": [{"item_id": identity, "media_type": "radio", "name": "Example"}]}

    async def lookup(ids):
        assert ids == [identity]
        return {identity: {"countrycode": "AU", "state": "Albury NSW", "language": "english", "clickcount": 42}}

    providers = {"radio": {"instance_id": "radio", "domain": "radiobrowser", "available": True}}
    service = MediaDiscovery(command, providers, region={"search_terms": ["Albury"]}, directory_lookup=lookup)
    assert (await service.find("radio", "Example", ["radio"]))["items"][0]["household_discovery"]["local"]

    async def offline(ids):
        raise RuntimeError("Synthetic directory offline")

    service.directory_lookup = offline
    result = await service.find("radio", "Example", ["radio"])
    assert result["items"][0]["household_discovery"]["label"] == "Region and language unverified"


@pytest.mark.asyncio
async def test_general_trending_and_personal_saved_identity_are_distinct():
    async def command(name, **args):
        assert name == "music/recommendations/items" and args["item_id"] == "itunes-top-podcasts"
        return [
            {"uri": "pod://podcast/one", "name": "Example", "media_type": "podcast", "metadata": {"languages": ["en"]}},
            {"uri": "pod://podcast/two", "name": "Unknown", "media_type": "podcast", "metadata": {}},
        ]

    service = MediaDiscovery(command, {"pod": {"instance_id": "pod", "domain": "itunes_podcasts", "available": True}})
    general = await service.find("podcast", "", ["pod"])
    assert not general["personalised"]
    assert general["items"][1]["household_discovery"]["label"] == "Podcast language unverified"
    own = await service.find("podcast", "", ["pod"], saved={"recent": [{"kind": "podcast", "uri": "pod://podcast/two"}]})
    assert own["personalised"] and own["items"][0]["uri"] == "pod://podcast/two"
    unrelated = await service.find("podcast", "", ["pod"], saved={"recent": [{"kind": "podcast", "uri": "other://podcast/two"}]})
    assert not unrelated["personalised"]
