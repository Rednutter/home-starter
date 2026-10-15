"""Actual HA calendar → app preview → reviewed wall publication → restart.

Only fictional data on disposable localhost:18123. Never points at the Green.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiohttp
from aiohttp.test_utils import TestClient, TestServer
from mock_supervisor import TOKEN, MockSupervisor


async def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "home_starter/server"))
    from homestarter import context, context_runtime, readiness
    from homestarter.household import HouseholdStore
    from homestarter.inventory import collect_inventory
    from homestarter.server import K_STATE, create_app
    from homestarter.settings import Settings

    credentials = json.loads(Path("screens/v3-core-credentials.json").read_text())
    base = "http://127.0.0.1:18123"
    headers = {"Authorization": "Bearer " + credentials["token"]}
    async with aiohttp.ClientSession() as session:
        async with session.get(base + "/api/states", headers=headers) as response:
            states = await response.json()
        calendars = [s["entity_id"] for s in states if s["entity_id"].startswith("calendar.")]
        assert calendars, "Disposable Core needs its fixture local calendar"
        source = calendars[0]
        when = datetime.now(UTC) + timedelta(hours=2)
        async with session.post(
            base + "/api/services/calendar/create_event",
            headers=headers,
            json={
                "entity_id": source,
                "summary": "Example context acceptance",
                "start_date_time": when.isoformat(),
                "end_date_time": (when + timedelta(hours=1)).isoformat(),
            },
        ) as response:
            assert response.status == 200, "Could not create the fictional fixture event"
        mock = MockSupervisor("ready", core_url=base, core_token=credentials["token"], ma_host="127.0.0.1")
        async with TestServer(mock.app()) as supervisor:
            settings = Settings.from_env(
                {
                    "SUPERVISOR_TOKEN": TOKEN,
                    "HOME_STARTER_SUPERVISOR_URL": str(supervisor.make_url("")),
                    "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
                    "HOME_STARTER_DATA_DIR": str(Path(".runtime/context-native-acceptance").resolve()),
                }
            )
            store = HouseholdStore(settings.data_dir)
            house = store.load()
            if not house["surfaces"]:
                house["surfaces"] = [
                    {
                        "id": "context_acceptance",
                        "name": "Context acceptance fixture",
                        "profile": "wall",
                        "person_id": None,
                        "area_id": None,
                        "audience": "everyone",
                    }
                ]
                house = store.save(house)
            before = json.dumps(house, sort_keys=True)
            app = create_app(settings)
            async with TestClient(TestServer(app)) as client:
                core = app[K_STATE].core
                inventory = await collect_inventory(core)
                saved = readiness.load(store, house)
                saved["choices"]["calendars"] = {"intent": "wanted", "sources": [source], "screens": ["context_acceptance"], "answers": {}, "permissions": {}}
                saved = await readiness.verify(core, saved, "calendars", inventory, await core.states())
                store.write(store.readiness_path, saved)
                ingress_headers = {"X-Remote-User-Id": credentials["user_id"]}
                response = await client.get("/api/surfaces/context_acceptance/preview", headers=ingress_headers)
                assert response.status == 200
                preview = await response.json()
                assert "Example context acceptance" in str(preview["context_preview"])
                response = await client.post(
                    "/api/surfaces/context_acceptance/publish", headers=ingress_headers, json={"preview_token": preview["preview_token"], "confirm": True}
                )
                assert response.status == 200
                assert (await response.json())["context"] == 1
                sink = context.entity_id("context_acceptance")
                observed = next(s for s in await core.states() if s["entity_id"] == sink)
                assert "Example context acceptance" in str(observed["attributes"])
                # Native template evaluation proves the state adapter feeds actual HA cards.
                card = context.wall_cards("context_acceptance")[0]
                async with session.post(base + "/api/template", headers=headers, json={"template": card["content"]}) as rendered:
                    assert rendered.status == 200 and "Example context acceptance" in await rendered.text()
                observed["attributes"]["checked_at"] = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
                await core.context_state(sink, {"state": observed["state"], "attributes": observed["attributes"]})
                async with session.post(base + "/api/template", headers=headers, json={"template": card["content"]}) as rendered:
                    assert await rendered.text() == "Calendar context unavailable"
            async with TestClient(TestServer(create_app(settings))) as restarted:
                # Startup may also refresh; an explicit read makes the check deterministic.
                state = restarted.app[K_STATE]
                await context_runtime.update(state.core, store)
                observed = next(s for s in await state.core.states() if s["entity_id"] == sink)
                assert "Example context acceptance" in str(observed["attributes"])
                assert json.dumps(store.load(), sort_keys=True) == before
                assert "Example context acceptance" not in store.readiness_path.read_text()
    print("Native calendar verification, context preview, explicit publication/readback, template refresh/expiry and app restart: PASS")


if __name__ == "__main__":
    asyncio.run(main())
