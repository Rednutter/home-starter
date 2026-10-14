"""Synthetic MA 2.10.6 read API contract; no household captures or credentials."""

import copy
import time

from aiohttp import web

TOKEN = "synthetic-ma-fixture-only"


class MockMusicRuntime:
    def __init__(self):
        self.calls = []
        self.progress = True
        self.fresh_static = False
        self.timestamp = time.time()
        self.started = time.monotonic()
        self.providers = [
            {"instance_id": "fixture_radio", "domain": "radiobrowser", "name": "Fixture radio", "type": "music", "available": True},
            {"instance_id": "fixture_urls", "domain": "builtin", "name": "Built-in", "type": "music", "available": True},
            {"instance_id": "fixture_connect", "domain": "spotify_connect", "name": "Spotify Connect", "type": "plugin", "available": True},
        ]
        self.configured = [
            {"instance_id": "fixture_radio", "domain": "radiobrowser", "name": "Fixture radio", "type": "music", "enabled": True},
            {"instance_id": "fixture_disabled", "domain": "spotify", "name": "Fixture disabled account", "type": "music", "enabled": False},
        ]
        self.player = {
            "player_id": "fixture_speaker",
            "name": "Fixture speaker",
            "provider": "fixture_player",
            "type": "player",
            "available": True,
            "playback_state": "playing",
            "active_source": "fixture_speaker",
            "current_media": {"queue_item_id": "fixture_item"},
            "group_members": [],
        }
        self.queue = {
            "queue_id": "fixture_speaker",
            "active": True,
            "state": "playing",
            "current_item": {"queue_item_id": "fixture_item", "streamdetails": {"provider": "fixture_radio"}},
        }
        self.config_status = 200

    async def api(self, request):
        if request.headers.get("Authorization") != "Bearer " + TOKEN:
            return web.Response(status=401)
        body = await request.json()
        command, args = body.get("command"), body.get("args", {})
        self.calls.append((command, args))
        if command == "providers":
            return web.json_response(self.providers)
        if command == "config/providers":
            assert args == {"provider_type": "music", "include_values": False}
            return web.json_response(self.configured, status=self.config_status)
        if command == "players/all":
            return web.json_response([self.player])
        if command == "players/get":
            player = copy.deepcopy(self.player)
            player["elapsed_time"] = 10 + (time.monotonic() - self.started if self.progress else 0)
            player["elapsed_time_last_updated"] = time.time() if self.progress or self.fresh_static else self.timestamp
            return web.json_response(player)
        if command == "player_queues/get_active_queue":
            return web.json_response(self.queue)
        return web.Response(status=400)
