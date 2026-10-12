"""Thin client for the Home Assistant Supervisor REST API (v1 paths).

Endpoint shapes follow supervisor/api/{root,apps,store,jobs}.py. Responses are
wrapped as ``{"result": "ok", "data": ...}``; errors as
``{"result": "error", "message": ...}`` except role/permission failures, which
the security middleware raises as a bare HTTP 403.

The token is only ever placed in the Authorization header of requests to the
Supervisor. It is never logged and never included in exceptions.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .settings import Secret

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)


class SupervisorError(Exception):
    """A Supervisor call failed.

    ``kind`` is one of: ``unreachable``, ``forbidden``, ``not_found``, ``api``.
    """

    def __init__(self, kind: str, message: str, *, status: int | None = None, path: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.path = path

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "status": self.status}


class SupervisorClient:
    def __init__(self, session: aiohttp.ClientSession, base_url: str, token: Secret) -> None:
        self._session = session
        self._base = base_url.rstrip("/")
        self._token = token

    def __repr__(self) -> str:
        return f"SupervisorClient({self._base!r})"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        timeout: aiohttp.ClientTimeout = DEFAULT_TIMEOUT,
    ) -> Any:
        if not self._token:
            raise SupervisorError("unreachable", "No Supervisor token is available to this app.", path=path)
        headers = {"Authorization": f"Bearer {self._token.reveal()}"}
        url = f"{self._base}{path}"
        try:
            async with self._session.request(method, url, json=json, headers=headers, timeout=timeout) as resp:
                status = resp.status
                body: Any = None
                text = await resp.text()
                if text:
                    try:
                        body = await resp.json(content_type=None)
                    except ValueError:
                        body = None
        except (TimeoutError, aiohttp.ClientError, OSError) as err:
            raise SupervisorError("unreachable", f"Supervisor not reachable ({type(err).__name__}).", path=path) from None

        if 200 <= status < 300 and isinstance(body, dict) and body.get("result") == "ok":
            return body.get("data")

        message = ""
        if isinstance(body, dict):
            message = str(body.get("message") or "")
            message = message.replace(self._token.reveal(), "[redacted]")
        if status == 403 or status == 401:
            raise SupervisorError(
                "forbidden",
                message or "Home Starter is not permitted to make this Supervisor call.",
                status=status,
                path=path,
            )
        if status == 404:
            raise SupervisorError("not_found", message or "Not found.", status=status, path=path)
        raise SupervisorError("api", message or f"Supervisor returned HTTP {status}.", status=status, path=path)

    # ---- read-only -------------------------------------------------------
    async def info(self) -> dict[str, Any]:
        return await self.request("GET", "/info")

    async def core_info(self) -> dict[str, Any]:
        return await self.request("GET", "/core/info")

    async def host_info(self) -> dict[str, Any]:
        return await self.request("GET", "/host/info")

    async def os_info(self) -> dict[str, Any]:
        return await self.request("GET", "/os/info")

    async def resolution_info(self) -> dict[str, Any]:
        return await self.request("GET", "/resolution/info")

    async def self_info(self) -> dict[str, Any]:
        return await self.request("GET", "/addons/self/info")

    async def installed_apps(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/addons")
        return list((data or {}).get("addons") or [])

    async def app_info(self, slug: str) -> dict[str, Any]:
        return await self.request("GET", f"/addons/{slug}/info")

    async def store_apps(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/store/addons")
        return list((data or {}).get("addons") or [])

    async def store_repositories(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/store/repositories")
        return list(data or [])

    async def store_app_availability(self, slug: str) -> None:
        """Raises SupervisorError(kind='api') with the reason if not installable."""
        await self.request("GET", f"/store/addons/{slug}/availability")

    async def job(self, job_id: str) -> dict[str, Any]:
        return await self.request("GET", f"/jobs/{job_id}")

    # ---- writes (only ever called from an explicit user action) ----------
    async def add_repository(self, url: str) -> None:
        await self.request("POST", "/store/repositories", json={"repository": url})

    async def reload_store(self) -> None:
        await self.request("POST", "/store/reload", timeout=aiohttp.ClientTimeout(total=120))

    async def install_app(self, slug: str) -> str | None:
        """Start an install in the background; returns the Supervisor job id."""
        data = await self.request(
            "POST",
            f"/store/addons/{slug}/install",
            json={"background": True},
            timeout=aiohttp.ClientTimeout(total=120),
        )
        if isinstance(data, dict):
            return data.get("job_id")
        return None

    async def start_app(self, slug: str) -> None:
        await self.request("POST", f"/addons/{slug}/start", timeout=aiohttp.ClientTimeout(total=300))
