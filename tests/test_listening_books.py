"""Synthetic routing contracts, never evidence of commissioned ABS accounts."""

from copy import deepcopy

import pytest
from homestarter import listening_books as books
from homestarter.household_music import collection_access, reconcile, source_access
from homestarter.music_runtime import MusicRuntimeError


def setup():
    house = {"people": [{"id": p, "name": "Example " + p} for p in ("one", "two")]}
    config = {"libraries": [{"people": [p], "provider_id": "books_" + p} for p in ("one", "two")]}
    providers = [{"id": "books_" + p, "domain": "audiobookshelf", "available": True} for p in ("one", "two")]
    providers.append({"id": "radio", "domain": "radiobrowser", "available": True})
    users = [{"user_id": "user_" + p, "display_name": "Example " + p, "provider_filter": ["radio", "books_" + p]} for p in ("one", "two")]
    return house, config, providers, users


def test_two_people_resolve_same_logical_book_to_exclusive_native_instances():
    args = setup()
    value = {
        "media_type": "audiobook",
        "uri": "library://audiobook/same-book",
        "provider_mappings": [{"provider_instance": "books_" + p, "item_id": "same-book"} for p in ("one", "two")],
    }
    for person in ("one", "two"):
        selected = books.route(*args, person, "2.10.7")
        assert selected == {"user_id": "user_" + person, "provider_id": "books_" + person}
        uri = books.native_uri(value, selected)
        assert uri == "books_" + person + "://audiobook/same-book"
        assert books.confirms(value, uri)


@pytest.mark.parametrize(
    "failure",
    [
        "house",
        "missing_map",
        "empty_map",
        "shared_map",
        "removed_source",
        "empty_filter",
        "deleted_filter",
        "other_unrestricted",
        "other_shared",
        "wrong_user",
        "disabled",
        "unreviewed",
        "duplicate_user",
        "extra_progress",
    ],
)
def test_route_fails_closed_without_changing_any_mapping(failure):
    house, config, providers, users = setup()
    person, version = "one", "2.10.7"
    if failure == "house":
        person = None
    elif failure == "missing_map":
        config["libraries"] = []
    elif failure == "empty_map":
        config["libraries"][0]["provider_id"] = None
    elif failure == "shared_map":
        config["libraries"][0]["people"].append("two")
    elif failure == "removed_source":
        providers.pop(0)
    elif failure == "empty_filter":
        users[0]["provider_filter"] = []
    elif failure == "deleted_filter":
        users[0]["provider_filter"] = ["radio", "deleted"]
    elif failure == "other_unrestricted":
        users[1]["provider_filter"] = []
    elif failure == "other_shared":
        users[1]["provider_filter"].append("books_one")
    elif failure == "wrong_user":
        users[0]["display_name"] = "Unknown"
    elif failure == "disabled":
        users[0]["enabled"] = False
    elif failure == "unreviewed":
        version = "2.11.0"
    elif failure == "duplicate_user":
        users.append(deepcopy(users[0]))
    elif failure == "extra_progress":
        users[0]["provider_filter"].append("books_two")
    before = deepcopy((house, config, providers, users))
    with pytest.raises(MusicRuntimeError, match="administrator review"):
        books.route(house, config, providers, users, person, version)
    assert (house, config, providers, users) == before


def test_saved_progress_source_stays_scoped_when_provider_disappears():
    assert books.needs_route({"kind": "audiobook", "progress_source": True}, [])
    assert books.needs_route({"kind": "audiobook", "sources": ["audiobookshelf--removed"]}, [])
    assert not books.needs_route({"kind": "podcast_episode", "sources": ["itunes"]}, [])
    with pytest.raises(MusicRuntimeError, match="source is unavailable"):
        books.native_uri({"media_type": "audiobook", "provider_mappings": []}, {"provider_id": "books_one"})


async def test_spotify_sharing_never_adds_or_removes_native_progress_assignments():
    _, _, providers, users = setup()
    original = deepcopy(users)
    assert source_access("House", providers) == ["radio"]
    assert collection_access(providers) == ["radio"]

    async def command(name, **args):
        if name == "auth/users":
            return deepcopy(users)
        assert name == "auth/user/update"
        next(u for u in users if u["user_id"] == args["user_id"])["provider_filter"] = args["provider_filter"]

    await reconcile(command, providers, names=("Example one", "Example two"), share_collections=True)
    assert users == original
