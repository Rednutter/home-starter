import json

import pytest
from homestarter.metadata_projection import project
from homestarter.playlist_visibility import PlaylistVisibilityStore, identities


def playlist(identity="one", source="source-a"):
    return {
        "media_type": "playlist",
        "item_id": identity,
        "uri": source + "://playlist/" + identity,
        "provider": source,
        "name": "Same title",
        "provider_mappings": [{"provider_domain": "spotify", "provider_instance": source, "item_id": identity}],
    }


def test_disposable_store_explicit_modes_exact_identity_and_revision(tmp_path):
    store = PlaylistVisibilityStore(tmp_path)
    assert store.load()["revision"] == 0 and not store.path.exists()
    args = dict(owner="one", visibility="mine", shared_with=[], people=["one", "two"], expected_revision=0, actor="one")
    with pytest.raises(PermissionError):
        store.assign(playlist(), **args)
    data = store.assign(playlist(), **args, administrator=True)
    assert identities(playlist()) == identities(playlist(source="source-b"))
    assert identities(playlist()) != identities(playlist("two"))
    rows = [playlist(), playlist(source="source-b"), playlist("two")]
    assert len(project(rows, "playlists", "one", ["source-a", "source-b"], playlist_rules=data["rules"])[0]) == 1
    assert not project(rows, "playlists", "house", ["source-a"], playlist_rules=data["rules"])[0]
    assert not project(rows, "playlists", "two", ["source-a"], playlist_rules=data["rules"])[0]
    with pytest.raises(ValueError):
        store.assign(playlist(), **args, administrator=True)
    data = store.assign(playlist(), **{**args, "visibility": "selected", "shared_with": ["two"], "expected_revision": 1}, administrator=True)
    assert len(project(rows, "playlists", "two", ["source-a"], playlist_rules=data["rules"])[0]) == 1
    assert not project(rows, "playlists", "house", ["source-a"], playlist_rules=data["rules"])[0]
    data = store.assign(playlist(), **{**args, "visibility": "house", "expected_revision": 2}, administrator=True)
    assert len(project(rows, "playlists", "house", ["source-a"], playlist_rules=data["rules"])[0]) == 1
    with pytest.raises(PermissionError):
        project(rows, "playlists", "house", [], playlist_rules=data["rules"])
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.assign(playlist(), **{**args, "visibility": "selected", "expected_revision": 3}, administrator=True)
    assert store.path.read_bytes() == before
    store.path.write_text(json.dumps({"version": 99}))
    with pytest.raises(ValueError):
        store.load()
    assert json.loads(store.path.read_text())["version"] == 99


def test_conflicting_identity_rules_fail_closed_even_with_saved_reference():
    row = playlist()
    row["provider_mappings"].append({"provider_domain": "other", "provider_instance": "source-b", "item_id": "two"})
    rules = {"spotify:playlist:one": {"owner": "one", "visibility": "house"}, "other:playlist:two": {"owner": "two", "visibility": "mine"}}
    from homestarter.metadata_projection import record_ids

    assert not project([row], "playlists", "house", ["source-a", "source-b"], playlist_rules=rules, saved=record_ids(row))[0]
