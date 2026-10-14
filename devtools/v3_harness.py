"""Home Starter + fake ingress against disposable Core. Loopback only."""

import argparse
import asyncio
import json
from pathlib import Path

import aiohttp
from aiohttp import web
from homestarter.server import create_app
from homestarter.settings import Settings
from ingress_proxy import build_app
from mock_supervisor import TOKEN, MockSupervisor


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", action="store_true", help="Use contract fixtures instead of disposable Core; never claims native rendering.")
    args = parser.parse_args()
    credentials = {"user_id": "a1b2c3d4e5f6"} if args.fixtures else json.loads(Path("screens/v3-core-credentials.json").read_text())
    mock = MockSupervisor(
        "absent" if args.fixtures else "ready",
        core_url=None if args.fixtures else "http://127.0.0.1:18123",
        core_token=credentials.get("token"),
        ma_host="127.0.0.1",
    )
    mock.ma_port = 8195
    if args.fixtures:
        # Representative synthetic touch sources, separate from captured API fixtures.
        sources = {
            "climate.fixture_system": (
                "heat",
                {
                    "friendly_name": "Fixture climate",
                    "hvac_modes": ["off", "heat", "cool"],
                    "fan_modes": ["auto", "high"],
                    "fan_mode": "auto",
                    "supported_features": 393,
                    "temperature": 22,
                    "current_temperature": 21,
                },
            ),
            "light.fixture_room": ("off", {"friendly_name": "Fixture room light", "supported_features": 0}),
            "calendar.fixture_family": ("off", {"friendly_name": "Fixture family", "message": "Fixture event"}),
        }
        for entity, (state, attributes) in sources.items():
            mock.activity_states[entity] = {"entity_id": entity, "state": state, "attributes": attributes}
            mock.entity_registry.append(
                {
                    "entity_id": entity,
                    "area_id": "kitchen" if not entity.startswith("calendar.") else None,
                    "platform": "generic_thermostat" if entity.startswith("climate.") else "template",
                }
            )
    settings = Settings.from_env(
        {
            "SUPERVISOR_TOKEN": TOKEN,
            "HOME_STARTER_SUPERVISOR_URL": "http://127.0.0.1:8181",
            "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
            "HOME_STARTER_DATA_DIR": str(Path("screens/v4-fixture-data" if args.fixtures else "screens/v3-data").resolve()),
            "HOME_STARTER_MA_PORT": "8195",
        }
    )
    async with aiohttp.ClientSession() as session:
        runners = []
        for app, port in (
            (mock.app(), 8181),
            (mock.ma_app(), 8195),
            (create_app(settings, session), 8099),
            (build_app("http://127.0.0.1:8099", user_id=credentials["user_id"]), 8124),
        ):
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "127.0.0.1", port).start()
            runners.append(runner)
        print("V3 test harness listening on loopback only.", flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            for runner in reversed(runners):
                await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
