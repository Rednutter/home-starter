"""Onboard the disposable localhost:18123 test Core; private credentials stay in screens/."""

import asyncio
import json
import secrets
from pathlib import Path

import aiohttp
from capture_core_fixtures import WS, flow


async def main():
    base = "http://127.0.0.1:18123"
    credentials = {"username": "owner", "password": secrets.token_urlsafe(32)}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            base + "/api/onboarding/users", json={"client_id": base + "/", "name": "Fixture Owner", "language": "en", **credentials}
        ) as resp:
            code = (await resp.json())["auth_code"]
        async with session.post(base + "/auth/token", data={"grant_type": "authorization_code", "code": code, "client_id": base + "/"}) as resp:
            credentials["token"] = (await resp.json())["access_token"]
        headers = {"Authorization": "Bearer " + credentials["token"]}
        for step in ("core_config", "integration", "analytics"):
            async with session.post(base + "/api/onboarding/" + step, headers=headers, json={"client_id": base + "/", "redirect_uri": base + "/"}) as resp:
                await resp.read()
        async with session.ws_connect(base.replace("http", "ws") + "/api/websocket") as raw:
            await raw.receive_json()
            await raw.send_json({"type": "auth", "access_token": credentials["token"]})
            assert (await raw.receive_json())["type"] == "auth_ok"
            ws = WS(raw)
            users = await ws.cmd("config/auth/list")
            credentials["user_id"] = next(u["id"] for u in users if u["is_owner"])
            areas = await ws.cmd("config/area_registry/list")
            kitchen = next(a["area_id"] for a in areas if a["name"] == "Kitchen")
            entries = await ws.cmd("config/entity_registry/list")
            for entry in entries:
                if entry["entity_id"] in (
                    "light.kitchen_light",
                    "sensor.kitchen_temperature",
                    "climate.kitchen_air_conditioning",
                    "sensor.washer_status",
                    "binary_sensor.kitchen_leak",
                ):
                    await ws.cmd("config/entity_registry/update", entity_id=entry["entity_id"], area_id=kitchen)
            await flow(session, base, headers, "local_calendar", {"calendar_name": "Family"})
    output = Path("screens/v3-core-credentials.json")
    output.write_text(json.dumps(credentials), encoding="utf-8")
    Path("screens/v3-core-token.txt").write_text(credentials["token"], encoding="utf-8")
    print("Disposable Core onboarded, fixture controls assigned to Kitchen; credentials kept private.")


if __name__ == "__main__":
    asyncio.run(main())
