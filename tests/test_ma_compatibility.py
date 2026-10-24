import asyncio
import json
from copy import deepcopy

import pytest
from homestarter.ma_compatibility import READ_PROBES, assess_reads


def responses():
    return {
        "providers": [{"instance_id": "private-source-id", "domain": "example", "type": "music", "available": True}],
        "auth/users": [{"user_id": "private-user-id", "provider_filter": ["private-source-id"], "enabled": True}],
        "players/all": [{"player_id": "private-player-id", "available": True, "supported_features": ["pause", "future_feature"]}],
        "music/artists/library_items": [
            {
                "item_id": "one",
                "name": "Example artist",
                "provider": "library",
                "uri": "library://artist/one",
                "media_type": "artist",
                "provider_mappings": [{"provider_instance": "private-source-id", "item_id": "one"}],
            }
        ],
    }


async def run(data, version="2.10.7", **kwargs):
    calls = []

    async def command(name, **args):
        calls.append((name, args))
        return deepcopy(data[name])

    report = await assess_reads(
        command,
        {"server_id": "server", "app": "app", "version": version, "schema_version": 31},
        {"server_id": "server", "app": "app"},
        {"house": "private-user-id"},
        **kwargs,
    )
    assert {name for name, _ in calls} == {name for name, _ in READ_PROBES}
    assert not report["features"]["protected_spotify"] and not report["features"]["native_transfer"]
    assert not report["authorizes_data_access"] and not report["authorizes_playback"]
    output = json.dumps(report)
    assert all(value not in output for value in ["private-source-id", "private-user-id", "private-player-id", "Example artist"])
    return report


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["2.10.6", "2.10.7", "2.10.8", "3.0.0", "2.11.0b1"])
async def test_release_number_does_not_replace_read_contract_or_attest_playback(version):
    data = responses()
    data["providers"][0]["future_field"] = "ignored"
    report = await run(data, version)
    assert report["features"]["catalogue_read_contract"] and report["features"]["player_read_contract"]
    assert report["reviewed_version"] == (version in {"2.10.6", "2.10.7"})
    assert report["playback_review_required"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filters,state",
    [
        (None, "source_mapping_missing"),
        ([], "source_mapping_missing"),
        (["unknown"], "source_mapping_changed"),
        (["private-source-id", "private-source-id"], "source_mapping_changed"),
    ],
)
async def test_missing_or_empty_filters_never_mean_full_library(filters, state):
    data = responses()
    data["auth/users"][0]["provider_filter"] = filters
    report = await run(data)
    assert report["profiles"]["house"] == state
    assert not report["features"]["catalogue_read_contract"]


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["provider-shape", "duplicate-user", "library-provenance", "ignored-page-limit", "renamed-filters"])
async def test_changed_required_contracts_fail_closed(change):
    data = responses()
    if change == "provider-shape":
        data["providers"] = {"items": data["providers"]}
    elif change == "duplicate-user":
        data["auth/users"] *= 2
    elif change == "library-provenance":
        data["music/artists/library_items"][0]["provider_mappings"] = []
    elif change == "ignored-page-limit":
        data["music/artists/library_items"] *= 2
    else:
        data["auth/users"][0]["source_filters"] = data["auth/users"][0].pop("provider_filter")
    assert not (await run(data))["features"]["catalogue_read_contract"]


@pytest.mark.asyncio
async def test_timeout_failure_is_bounded_sanitised_and_independent():
    data = responses()
    calls = []

    async def command(name, **args):
        calls.append(name)
        if name == "providers":
            await asyncio.sleep(1)
        if name == "auth/users":
            raise RuntimeError("private upstream details")
        return data[name]

    report = await assess_reads(
        command,
        {"server_id": "server", "app": "app", "version": "private-version-value"},
        {"server_id": "server", "app": "app"},
        {"house": "private-user-id"},
        timeout=0.01,
    )
    assert len(calls) == 4
    assert not report["features"]["catalogue_read_contract"] and report["features"]["player_read_contract"]
    assert "private" not in json.dumps(report)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["server", "app", "schema", "binding"])
async def test_identity_schema_and_explicit_bindings_checked_before_network(change):
    endpoint = {"server_id": "server", "app": "app", "version": "2.10.8", "schema_version": 31}
    bindings = {"house": "one"}
    if change in {"server", "app"}:
        endpoint["server_id" if change == "server" else "app"] = "changed"
    elif change == "schema":
        endpoint["schema_version"] = True
    else:
        bindings = {"house": "one", "person": "one"}

    async def no_network(name, **args):
        raise AssertionError("Must not probe before identity validation")

    report = await assess_reads(no_network, endpoint, {"server_id": "server", "app": "app"}, bindings)
    assert not report["features"]["catalogue_read_contract"]
