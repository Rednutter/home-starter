"""Capture registry contracts from a disposable Core with fixture_inventory installed.

Never run this against a household: it onboards and creates a test config entry.
Copy devtools/fixture_inventory into the disposable container's
/config/custom_components directory and restart it before running this script.
"""

import asyncio
import json
from pathlib import Path

import aiohttp
from capture_core_fixtures import WS, flow, onboard

ROOT = Path(__file__).resolve().parent.parent


async def main():
    (ROOT / "screens").mkdir(exist_ok=True)
    base = "http://127.0.0.1:18123"
    async with aiohttp.ClientSession() as session:
        token_file = ROOT / "screens/core-test-token.txt"
        token = token_file.read_text() if token_file.exists() else await onboard(session, base)
        async with session.ws_connect(base.replace("http", "ws") + "/api/websocket") as raw:
            await raw.receive_json()
            await raw.send_json({"type": "auth", "access_token": token})
            assert (await raw.receive_json())["type"] == "auth_ok"
            ws = WS(raw)
            entries = await ws.cmd("config_entries/get")
            if not any(e["domain"] == "fixture_inventory" for e in entries):
                await flow(session, base, {"Authorization": f"Bearer {token}"}, "fixture_inventory", {})
            await asyncio.sleep(2)
            for filename, command in (
                ("captured_device_registry_list.json", "config/device_registry/list"),
                ("captured_floor_registry_list.json", "config/floor_registry/list"),
            ):
                payload = await ws.cmd(command)
                text = json.dumps(payload, indent=2, sort_keys=True)
                assert token not in text
                output = ROOT / "screens/fixture-captures/core"
                output.mkdir(parents=True, exist_ok=True)
                (output / filename).write_text(text + "\n")
                print(filename, len(payload))
        # Ignored private runtime file for further disposable-Core acceptance.
        (ROOT / "screens/core-test-token.txt").write_text(token)


if __name__ == "__main__":
    asyncio.run(main())
