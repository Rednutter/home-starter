from contextlib import asynccontextmanager

import pytest
from homestarter.core import CoreClient, CoreError
from homestarter.settings import Secret


@pytest.mark.asyncio
async def test_forecast_is_read_only_scoped_and_cached_without_persisting_secrets():
    client = CoreClient(None, "http://example.invalid/api", "ws://example.invalid/ws", Secret("example-test-token"))
    calls = []

    class Socket:
        async def command(self, command, **kwargs):
            calls.append((command, kwargs))
            return {"response": {"weather.fixture": {"forecast": [{"datetime": "2026-10-19T00:00:00+11:00", "temperature": 20}]}}}

    @asynccontextmanager
    async def socket():
        yield Socket()

    client.websocket = socket
    assert await client.weather_forecast("weather.fixture") == await client.weather_forecast("weather.fixture")
    assert len(calls) == 1
    assert calls[0] == (
        "call_service",
        {
            "domain": "weather",
            "service": "get_forecasts",
            "service_data": {"type": "daily"},
            "target": {"entity_id": "weather.fixture"},
            "return_response": True,
        },
    )
    with pytest.raises(ValueError):
        await client.weather_forecast("light.fixture")


@pytest.mark.asyncio
async def test_failed_forecast_never_becomes_an_invented_high():
    client = CoreClient(None, "http://example.invalid/api", "ws://example.invalid/ws", Secret("example-test-token"))

    @asynccontextmanager
    async def socket():
        raise CoreError("api", "Native source unavailable")
        yield  # pragma: no cover

    client.websocket = socket
    assert await client.weather_forecast("weather.fixture") == []
