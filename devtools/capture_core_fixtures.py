"""Capture real Home Assistant Core API payloads as test fixtures.

Runs against a *throwaway* local Home Assistant Core (never a household
instance): it onboards it, adds two areas and two config entries, then saves
the exact responses Home Starter reads into tests/fixtures/core/.

    python devtools/capture_core_fixtures.py http://127.0.0.1:8123

Tokens are never written to the fixtures.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import sys
from pathlib import Path

import aiohttp

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "core"
CLIENT_ID = "http://127.0.0.1:8123/"


def public_fixture(data):
    """Remove location coordinates before saving public test data."""
    if isinstance(data, dict):
        return {k: 0.0 if k in ("latitude", "longitude") else public_fixture(v) for k, v in data.items()}
    if isinstance(data, list):
        return [public_fixture(v) for v in data]
    return data


async def onboard(session: aiohttp.ClientSession, base: str) -> str:
    async with session.get(f"{base}/api/onboarding") as resp:
        steps = await resp.json()
    if not any(s["step"] == "user" and not s["done"] for s in steps):
        raise SystemExit("Instance already onboarded; start from an empty config dir.")
    async with session.post(
        f"{base}/api/onboarding/users",
        json={"client_id": CLIENT_ID, "name": "Fixture Owner", "username": "owner", "password": secrets.token_urlsafe(32), "language": "en"},
    ) as resp:
        code = (await resp.json())["auth_code"]
    async with session.post(f"{base}/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": CLIENT_ID}) as resp:
        return (await resp.json())["access_token"]


class WS:
    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws = ws
        self.n = 0

    async def cmd(self, msg_type: str, **kw):
        self.n += 1
        await self.ws.send_json({"id": self.n, "type": msg_type, **kw})
        while True:
            msg = await self.ws.receive_json()
            if msg.get("id") == self.n and msg.get("type") == "result":
                if not msg["success"]:
                    raise RuntimeError(f"{msg_type}: {msg['error']}")
                return msg["result"]


async def flow(session, base, headers, handler, user_input):
    async with session.post(f"{base}/api/config/config_entries/flow", json={"handler": handler}, headers=headers) as resp:
        result = await resp.json()
    if result.get("type") == "form" and user_input is not None:
        async with session.post(f"{base}/api/config/config_entries/flow/{result['flow_id']}", json=user_input, headers=headers) as resp:
            result = await resp.json()
    return result


async def main(base: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    async with aiohttp.ClientSession() as session:
        token = await onboard(session, base)
        headers = {"Authorization": f"Bearer {token}"}
        async with session.ws_connect(f"{base.replace('http', 'ws', 1)}/api/websocket") as raw:
            await raw.receive_json()
            await raw.send_json({"type": "auth", "access_token": token})
            assert (await raw.receive_json())["type"] == "auth_ok"
            ws = WS(raw)
            # Onboarding already creates Living Room / Kitchen / Bedroom.
            for name in ("Garage", "Study"):
                await ws.cmd("config/area_registry/create", name=name)
            # sun loads offline; met needs api.met.no, which is unreachable in a
            # sandbox, so it ends in setup_retry: a realistic unhealthy entry.
            print("sun:", (await flow(session, base, headers, "sun", {}))["type"])
            print("met:", (await flow(session, base, headers, "met", {"name": "Home", "latitude": 0.0, "longitude": 0.0, "elevation": 0}))["type"])
            await asyncio.sleep(8)

            captures = {
                "config_entries_get.json": await ws.cmd("config_entries/get"),
                "area_registry_list.json": await ws.cmd("config/area_registry/list"),
                "entity_registry_list.json": await ws.cmd("config/entity_registry/list"),
                "flow_progress.json": await ws.cmd("config_entries/flow/progress"),
                "repairs_list_issues.json": await ws.cmd("repairs/list_issues"),
            }
        async with session.get(f"{base}/api/config", headers=headers) as resp:
            captures["api_config.json"] = await resp.json()
        async with session.get(f"{base}/api/states", headers=headers) as resp:
            captures["api_states.json"] = await resp.json()

    for name, data in captures.items():
        text = json.dumps(public_fixture(data), indent=2, sort_keys=True)
        assert token not in text
        (OUT / name).write_text(text + "\n")
        print("wrote", name)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"))
