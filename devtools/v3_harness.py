"""Home Starter + fake ingress against disposable Core. Loopback only."""

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
    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    mock = MockSupervisor("ready", core_url="http://127.0.0.1:18123", core_token=credentials["token"], ma_host="127.0.0.1")
    settings = Settings.from_env(
        {
            "SUPERVISOR_TOKEN": TOKEN,
            "HOME_STARTER_SUPERVISOR_URL": "http://127.0.0.1:8181",
            "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
            "HOME_STARTER_DATA_DIR": str(Path("screens/v3-data").resolve()),
        }
    )
    async with aiohttp.ClientSession() as session:
        runners = []
        for app, port in (
            (mock.app(), 8181),
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
