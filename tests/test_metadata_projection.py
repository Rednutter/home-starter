import pytest
from homestarter.metadata_projection import ArtworkLedger, fingerprint, project


def item(key="one", kind="artist", source="source-a", name="Example artist"):
    return {
        "item_id": key,
        "provider": source,
        "uri": source + "://" + kind + "/" + key,
        "media_type": kind,
        "name": name,
        "provider_mappings": [{"provider_instance": source, "provider_domain": "spotify", "item_id": key, "url": "private-reference"}],
        "metadata": {"images": [{"type": "thumb", "provider": "builtin", "path": "https://i.scdn.co/image/example"}]},
        "owner": "not-a-person-binding",
        "secret": "never-public",  # pragma: allowlist secret -- synthetic forbidden-field sentinel
    }


def test_real_models_require_sources_and_personal_attribution():
    row = item()
    values, _ = project([row], "artists", "house", ["source-a"])
    assert len(values) == 1 and "secret" not in values[0] and "owner" not in values[0]
    assert "url" not in values[0]["provider_mappings"][0]
    assert project([row], "artists", "person-one", ["source-a"])[0] == []
    saved = [fingerprint(row["uri"])[:24]]
    assert len(project([row], "artists", "person-one", ["source-a"], saved=saved)[0]) == 1
    assert project([row], "artists", "house", ["source-b"])[0] == []
    with pytest.raises(PermissionError):
        project([row], "artists", "house", [])


def test_playlist_visibility_is_explicit_and_unknown_owner_stays_unassigned():
    row = item(kind="playlist")
    assert project([row], "playlists", "house", ["source-a"])[1] == 1
    rules = {row["uri"]: {"owner": "person-one", "visibility": "mine", "shared_with": ["person-two"]}}
    assert len(project([row], "playlists", "person-one", ["source-a"], saved=[fingerprint(row["uri"])[:24]], playlist_rules=rules)[0]) == 1
    assert project([row], "playlists", "house", ["source-a"], playlist_rules=rules)[0] == []


def test_artwork_registry_rejects_arbitrary_urls_old_profile_and_revoked_policy():
    ledger = ArtworkLedger()
    ledger.select("browser", "person-one", 1, "policy-one")
    model = ledger.register("browser", item())
    identity = model["metadata"]["images"][0]["path"].split("/")[-1]
    assert ledger.reference("browser", identity, "policy-one", ["source-a"])["provider"] == "builtin"
    for key, policy, sources in [("https://internal.example/", "policy-one", ["source-a"]), (identity, "revoked", ["source-a"]), (identity, "policy-one", [])]:
        with pytest.raises(PermissionError):
            ledger.reference("browser", key, policy, sources)
    ledger.select("browser", "person-two", 2, "policy-two")
    with pytest.raises(PermissionError):
        ledger.reference("browser", identity, "policy-two", ["source-a"])
    with pytest.raises(PermissionError):
        ledger.select("browser", "person-one", 1, "policy-one")


def test_distinct_same_named_items_are_not_deduplicated_by_title():
    rows, _ = project([item("one"), item("two")], "artists", "house", ["source-a"])
    assert len(rows) == 2


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "https://169.254.169.254/",
        "file:///etc/passwd",
        "https://unknown.example/image.png",
        "https://user:example@example.com/image/one",  # pragma: allowlist secret -- deliberately invalid synthetic userinfo
    ],
)
def test_poisoned_or_unreviewed_native_image_reference_uses_empty_fallback(url):
    ledger = ArtworkLedger()
    ledger.select("browser", "house", 1, "policy")
    model = item()
    model["metadata"]["images"][0]["path"] = url
    public = ledger.register("browser", model)
    assert public["metadata"]["images"] == []
    assert ledger.images == {}


@pytest.mark.asyncio
async def test_bridge_rejects_native_writes_and_profile_switch_during_artwork():
    import asyncio

    from homestarter.catalogue_preview import MetadataPreview

    calls, began, finish = [], asyncio.Event(), asyncio.Event()
    filters = ["source-a"]

    async def command(name, **args):
        calls.append((name, args))
        assert name == "auth/users"
        return [
            {"display_name": "House", "user_id": "house-user", "provider_filter": filters},
            {"display_name": "Example One", "user_id": "one-user", "provider_filter": filters},
        ]

    async def art(reference):
        began.set()
        await finish.wait()
        return "image/png", b"synthetic-image"

    house = {"epoch": 1, "people": [{"id": "one", "name": "Example One"}]}
    bridge = MetadataPreview(command, None, art, house, "panel")
    bridge.providers = {"source-a": {"available": True, "domain": "spotify"}}
    bridge.rows["artists"] = [item()]
    bridge.saved = {"house": {"favorites": [], "recent": []}, "one": {"favorites": [], "recent": []}}
    body = {"profile": "house", "generation": 1, "command": "music/artists/library_items", "args": {}}
    values = await bridge.read("browser", body)
    identity = values[0]["metadata"]["images"][0]["path"].split("/")[-1]
    task = asyncio.create_task(bridge.artwork("browser", identity))
    await asyncio.wait_for(began.wait(), 2)
    assert await bridge.read("browser", {**body, "profile": "one", "generation": 2}) == []
    finish.set()
    with pytest.raises(PermissionError):
        await task
    for name in ["player_queues/play_media", "players/cmd/volume_set", "auth/user/update"]:
        with pytest.raises(PermissionError):
            await bridge.read("browser", {**body, "profile": "one", "generation": 3, "command": name})
    assert all(name == "auth/users" for name, _ in calls)
    filters.clear()
    with pytest.raises(PermissionError):
        await bridge.read("browser", {**body, "profile": "one", "generation": 4})


def test_native_back_keeps_same_profile_art_but_policy_and_profile_changes_revoke_it():
    from homestarter.metadata_projection import native_artwork_path

    ledger = ArtworkLedger()
    ledger.select("browser", "house", 1, "policy")
    model = ledger.register("browser", item())
    identity = model["metadata"]["images"][0]["path"].split("/")[-1]
    ledger.select("browser", "house", 2, "policy")
    assert ledger.reference("browser", identity, "policy", ["source-a"])
    ledger.select("browser", "house", 3, "new-policy")
    with pytest.raises(PermissionError):
        ledger.reference("browser", identity, "new-policy", ["source-a"])
    image = {**item()["metadata"]["images"][0], "proxy_id": "a" * 64}
    assert native_artwork_path(image) == "/imageproxy/" + "a" * 64 + "?size=512"
    assert native_artwork_path({**image, "proxy_id": "../arbitrary"}) is None
    assert native_artwork_path({**image, "path": "https://127.0.0.1/private"}) is None
