"""Exercise installed official MA serializers, without starting a server or sockets.

Run with an isolated Python 3.14 environment containing the exact official model
version declared by the reviewed MA releases. This is model-runtime evidence,
not a running-server, provider-enforcement or physical-playback test.
"""

import asyncio
import json
import sys
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))


async def run():
    from homestarter.ma_compatibility import assess_reads, profile_state, provider_contract
    from music_assistant_models.auth import User
    from music_assistant_models.enums import PlayerFeature, PlayerType, ProviderType
    from music_assistant_models.media_items import Artist, ProviderMapping
    from music_assistant_models.player import DeviceInfo, Player

    assert version("music-assistant-models") == "1.1.205"
    assert version("mashumaro") == "3.20" and version("orjson") == "3.11.6"
    user = User("example-user", "example", "user", provider_filter=["example-source"])
    artist = Artist(
        item_id="example-artist",
        provider="library",
        name="Example artist",
        provider_mappings={ProviderMapping(item_id="example-artist", provider_domain="example", provider_instance="example-source")},
    )
    player = Player("example-player", "example", PlayerType.PLAYER, "Example speaker", True, DeviceInfo(), {PlayerFeature.PAUSE})
    # The provider envelope is a synthetic server record using the real enum;
    # User/Artist/Player payloads below come from installed upstream serializers.
    providers = [{"instance_id": "example-source", "domain": "example", "type": ProviderType.MUSIC.value, "available": True}]
    users = [User.from_json(user.to_json()).to_dict()]
    artists = [Artist.from_dict(json.loads(json.dumps(artist.to_dict()))).to_dict()]
    players = [Player.from_dict(json.loads(json.dumps(player.to_dict()))).to_dict()]
    calls = []

    async def command(name, **args):
        calls.append(name)
        return {"providers": providers, "auth/users": users, "players/all": players, "music/artists/library_items": artists}[name]

    for release in ("2.10.6", "2.10.7"):
        endpoint = {"version": release, "server_id": "example-server", "app": "example-app", "schema_version": 1}
        report = await assess_reads(command, endpoint, endpoint, {"example-profile": "example-user"})
        assert report["features"]["profile_filter_contract"]
        assert report["features"]["catalogue_read_contract"]
        assert report["features"]["player_read_contract"]
        assert not report["authorizes_playback"]
        assert not report["features"]["protected_spotify"] and not report["features"]["native_transfer"]
    user.provider_filter.clear()
    assert profile_state(user.to_dict(), provider_contract(providers)) == "source_mapping_missing"
    assert set(calls) == {"providers", "auth/users", "players/all", "music/artists/library_items"}
    return {
        "models_version": version("music-assistant-models"),
        "serializer_versions": {name: version(name) for name in ("mashumaro", "orjson")},
        "python": sys.version.split()[0],
        "official_user_artist_player_roundtrips": True,
        "empty_filter_fails_closed": True,
        "matching_release_model_requirements": ["2.10.6", "2.10.7"],
        "server_runtime_tested": False,
        "network_or_household_connections": False,
        "playback_enforcement_attested": False,
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run())))
