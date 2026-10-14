from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from homestarter.core import CoreClient
from homestarter.settings import Secret, Settings
from homestarter.supervisor import SupervisorClient
from mock_supervisor import TOKEN, MockSupervisor

FIX = Path(__file__).parent / "fixtures"


def sup_fixture(name: str) -> Any:
    """`data` of a Supervisor wire-format fixture."""
    return json.loads((FIX / "supervisor" / name).read_text())["data"]


def core_fixture(name: str) -> Any:
    return json.loads((FIX / "core" / name).read_text())


def ma_fixture(name: str) -> Any:
    return json.loads((FIX / "music_assistant" / name).read_text())


@dataclass
class Env:
    mock: MockSupervisor
    session: aiohttp.ClientSession
    supervisor: SupervisorClient
    core: CoreClient
    settings: Settings
    ma_port: int


@pytest.fixture
async def make_env(tmp_path) -> AsyncIterator:
    servers: list[TestServer] = []
    sessions: list[aiohttp.ClientSession] = []

    async def factory(scenario: str = "absent", **kw) -> Env:
        fresh = kw.pop("fresh", False)
        mock = MockSupervisor(scenario, ma_host="127.0.0.1", **kw)
        sup_server = TestServer(mock.app())
        ma_server = TestServer(mock.ma_app())
        await sup_server.start_server()
        await ma_server.start_server()
        # The MA stand-in is reached at the app's ip_address (127.0.0.1 here).
        mock.ma_host = "127.0.0.1"
        mock.ma_port = ma_server.port
        servers.extend([sup_server, ma_server])
        base = str(sup_server.make_url("")).rstrip("/")
        settings = Settings.from_env(
            {
                "SUPERVISOR_TOKEN": TOKEN,
                "HOME_STARTER_SUPERVISOR_URL": base,
                "HOME_STARTER_ALLOWED_PEERS": "127.0.0.1",
                "HOME_STARTER_MA_PORT": str(ma_server.port),
                "HOME_STARTER_DATA_DIR": str(tmp_path / f"runtime-{len(servers)}"),
            }
        )
        session = aiohttp.ClientSession()
        sessions.append(session)
        if not fresh:
            # Existing API contract tests exercise maintenance, not pre-Go commissioning.
            from homestarter.household import HouseholdStore, empty_household

            HouseholdStore(settings.data_dir).save(empty_household())
        return Env(
            mock=mock,
            session=session,
            supervisor=SupervisorClient(session, settings.supervisor_url, Secret(TOKEN)),
            core=CoreClient(session, settings.core_api_url, settings.core_ws_url, Secret(TOKEN)),
            settings=settings,
            ma_port=ma_server.port,
        )

    yield factory
    for s in sessions:
        await s.close()
    for srv in servers:
        await srv.close()
