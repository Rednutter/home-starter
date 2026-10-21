"""Client for the Home Assistant Core API, via the Supervisor proxy.

REST:      http://supervisor/core/api/...      (homeassistant_api: true)
WebSocket: ws://supervisor/core/websocket      (same token as access_token)

Reads plus explicitly confirmed device area assignment are used. The proxy rejects the
``supervisor/`` and ``hassio/`` command families for apps.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import re
from time import monotonic
from typing import Any

import aiohttp

from .settings import Secret

_LOGGER = logging.getLogger(__name__)

REST_TIMEOUT = aiohttp.ClientTimeout(total=20)
WS_TIMEOUT = 15


class CoreError(Exception):
    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind  # unreachable | auth | api
        self.message = message


class CoreClient:
    def __init__(self, session: aiohttp.ClientSession, api_url: str, ws_url: str, token: Secret) -> None:
        self._session = session
        self._api = api_url.rstrip("/")
        self._ws_url = ws_url
        self._token = token
        self._forecasts = {}
        self._forecast_lock = asyncio.Lock()

    def __repr__(self) -> str:
        return f"CoreClient({self._api!r})"

    async def rest_get(self, path: str) -> Any:
        if not self._token:
            raise CoreError("unreachable", "No API token is available to this app.")
        headers = {"Authorization": f"Bearer {self._token.reveal()}"}
        try:
            async with self._session.get(f"{self._api}{path}", headers=headers, timeout=REST_TIMEOUT) as resp:
                if resp.status in (401, 403):
                    raise CoreError("auth", "Home Assistant rejected the API request.")
                if resp.status >= 400:
                    raise CoreError("api", f"Home Assistant returned HTTP {resp.status}.")
                return await resp.json(content_type=None)
        except CoreError:
            raise
        except (TimeoutError, aiohttp.ClientError, OSError, ValueError) as err:
            raise CoreError("unreachable", f"Home Assistant API not reachable ({type(err).__name__}).") from None

    async def config(self) -> dict[str, Any]:
        return await self.rest_get("/config")

    async def weather_forecast(self, entity_id: str) -> list[dict]:
        """Read the selected native daily forecast; cache only in process memory."""
        if not re.fullmatch(r"weather\.[a-z0-9_]+", entity_id):
            raise ValueError("Choose a native weather source.")
        async with self._forecast_lock:
            cached = self._forecasts.get(entity_id)
            if cached and monotonic() < cached[0]:
                return cached[1]
            try:
                async with self.websocket() as ws:
                    result = await ws.command(
                        "call_service",
                        domain="weather",
                        service="get_forecasts",
                        service_data={"type": "daily"},
                        target={"entity_id": entity_id},
                        return_response=True,
                    )
                rows = result.get("response", {}).get(entity_id, {}).get("forecast", [])
                rows = [r for r in rows[:10] if isinstance(r, dict)] if isinstance(rows, list) else []
            except (CoreError, ValueError, TypeError, AttributeError):
                rows = []
            self._forecasts[entity_id] = (monotonic() + (600 if rows else 60), rows)
            return rows

    async def check_camera(self, entity_id: str) -> None:
        """Read a bounded native snapshot to verify a selected source; retain no pixels/token."""
        import re

        if not re.fullmatch(r"camera\.[a-z0-9_]+", entity_id):
            raise ValueError("Choose a native camera entity.")
        try:
            async with self._session.get(
                self._api + "/camera_proxy/" + entity_id,
                headers={"Authorization": "Bearer " + self._token.reveal()},
                timeout=REST_TIMEOUT,
                allow_redirects=False,
            ) as response:
                head = await response.content.read(32)
                if (
                    response.status != 200
                    or not response.headers.get("Content-Type", "").startswith("image/")
                    or not head.startswith((b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF"))
                ):
                    raise CoreError("api", "The selected camera did not return a native picture.")
        except (TimeoutError, aiohttp.ClientError, OSError):
            raise CoreError("unreachable", "The selected camera picture is unavailable.") from None

    async def activity_state(self, entity_id: str, payload: dict) -> None:
        """Publish only Home Starter's explicitly configured virtual activity sensors."""
        import re

        if not re.fullmatch(r"sensor\.home_starter_activity_[a-f0-9]{12}", entity_id):
            raise ValueError("Activity sensor namespace required.")
        try:
            async with self._session.post(
                f"{self._api}/states/{entity_id}",
                json=payload,
                headers={"Authorization": f"Bearer {self._token.reveal()}"},
                timeout=REST_TIMEOUT,
            ) as response:
                if response.status not in (200, 201):
                    raise CoreError("api", "Could not publish appliance activity to Home Assistant.")
                saved = await response.json()
                if saved.get("state") != payload["state"] or saved.get("attributes") != payload["attributes"]:
                    raise CoreError("api", "Activity state could not be verified.")
        except (TimeoutError, aiohttp.ClientError, OSError, ValueError) as err:
            raise CoreError("unreachable", f"Activity state write failed ({type(err).__name__}).") from None

    async def states(self) -> list[dict[str, Any]]:
        return list(await self.rest_get("/states") or [])

    async def context_state(self, entity_id: str, payload: dict) -> None:
        """Only owned household context projections; never hardware service calls."""
        import re

        if not re.fullmatch(r"sensor\.home_starter_(?:context|endpoint)_[a-f0-9]{12}", entity_id) and entity_id != "sensor.home_starter_bin_source":
            raise ValueError("Context sensor namespace required.")
        try:
            async with self._session.post(
                f"{self._api}/states/{entity_id}",
                json=payload,
                headers={"Authorization": f"Bearer {self._token.reveal()}"},
                timeout=REST_TIMEOUT,
            ) as response:
                if response.status not in (200, 201):
                    raise CoreError("api", "Context state could not be published.")
                saved = await response.json()
                if saved.get("state") != payload["state"] or saved.get("attributes") != payload["attributes"]:
                    raise CoreError("api", "Context state readback did not match.")
        except (TimeoutError, aiohttp.ClientError, OSError, ValueError) as err:
            raise CoreError("unreachable", f"Context state write failed ({type(err).__name__}).") from None

    async def template_flow(self, body: dict, flow_id: str | None = None) -> dict:
        """Supported config flow endpoint, bounded to native Template helper setup."""
        import re

        if flow_id is not None and not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", flow_id):
            raise ValueError("Invalid native flow identity.")
        if flow_id is None and body != {"handler": "template", "show_advanced_options": True}:
            raise ValueError("Native Template helper flow required.")
        path = "/config/config_entries/flow" + ("/" + flow_id if flow_id else "")
        try:
            async with self._session.post(
                self._api + path, json=body, headers={"Authorization": "Bearer " + self._token.reveal()}, timeout=REST_TIMEOUT
            ) as response:
                if response.status != 200:
                    raise CoreError("api", "Native Template helper configuration failed.")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError, OSError):
            raise CoreError("unreachable", "Native Template helper result is uncertain; inspect helpers before retrying.") from None

    async def local_calendar_flow(self, body: dict, flow_id: str | None = None) -> dict:
        """Supported config flow endpoint, bounded to owned Local Calendar setup."""
        import re

        if flow_id is not None and not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", flow_id):
            raise ValueError("Invalid native flow identity.")
        if flow_id is None:
            if body != {}:
                raise ValueError("Native Local Calendar start required.")
            body = {"handler": "local_calendar"}
        elif body != {"calendar_name": "Home Starter Bins"}:
            raise ValueError("Owned bin calendar name required.")
        path = "/config/config_entries/flow" + ("/" + flow_id if flow_id else "")
        try:
            async with self._session.post(
                self._api + path, json=body, headers={"Authorization": "Bearer " + self._token.reveal()}, timeout=REST_TIMEOUT
            ) as response:
                if response.status != 200:
                    raise CoreError("api", "Native Local Calendar configuration failed.")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError, ValueError, OSError):
            raise CoreError("unreachable", "Native Local Calendar result is uncertain; inspect helpers before retrying.") from None

    def websocket(self) -> CoreWebSocket:
        return CoreWebSocket(self._session, self._ws_url, self._token)

    async def is_admin(self, user_id: str) -> bool:
        """Check the ingress identity against Core, never browser-supplied roles."""
        async with self.websocket() as ws:
            users = await ws.command("config/auth/list")
        return any(
            u.get("id") == user_id
            and u.get("is_active") is True
            and not u.get("system_generated")
            and (u.get("is_owner") is True or "system-admin" in (u.get("group_ids") or []))
            for u in users or []
        )


class CoreWebSocket:
    """One authenticated websocket session; use as ``async with``."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: Secret) -> None:
        self._session = session
        self._url = url
        self._token = token
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> CoreWebSocket:
        if not self._token:
            raise CoreError("unreachable", "No API token is available to this app.")
        try:
            self._ws = await self._session.ws_connect(self._url, timeout=aiohttp.ClientWSTimeout(ws_close=5), max_msg_size=64 * 1024 * 1024)
            hello = await self._ws.receive_json(timeout=WS_TIMEOUT)
            if hello.get("type") != "auth_required":
                raise CoreError("api", "Unexpected websocket greeting from Home Assistant.")
            await self._ws.send_json({"type": "auth", "access_token": self._token.reveal()})
            result = await self._ws.receive_json(timeout=WS_TIMEOUT)
        except CoreError:
            await self._close()
            raise
        except (TimeoutError, aiohttp.ClientError, OSError, ValueError, TypeError) as err:
            await self._close()
            raise CoreError("unreachable", f"Home Assistant websocket not reachable ({type(err).__name__}).") from None
        if result.get("type") != "auth_ok":
            await self._close()
            raise CoreError("auth", "Home Assistant rejected the websocket login.")
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._close()

    async def _close(self) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
        self._ws = None

    async def command(self, msg_type: str, **payload: Any) -> Any:
        if self._ws is None:
            raise CoreError("unreachable", "Websocket is not connected.")
        async with self._lock:
            msg_id = next(self._ids)
            try:
                await self._ws.send_json({"id": msg_id, "type": msg_type, **payload})
                while True:
                    msg = await self._ws.receive_json(timeout=WS_TIMEOUT)
                    if msg.get("id") == msg_id and msg.get("type") == "result":
                        break
            except (TimeoutError, aiohttp.ClientError, OSError, ValueError, TypeError) as err:
                raise CoreError("unreachable", f"Websocket command failed ({type(err).__name__}).") from None
        if not msg.get("success"):
            error = msg.get("error") or {}
            message = f"{msg_type}: {error.get('message') or error.get('code') or 'failed'}"
            raise CoreError("api", message.replace(self._token.reveal(), "[redacted]"))
        return msg.get("result")
