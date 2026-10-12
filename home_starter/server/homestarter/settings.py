"""Runtime settings, read once from the environment.

Inside Home Assistant the defaults are correct; the overrides exist only so the
same code can run against the local development harness in ``devtools/``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Ingress requests always arrive from the Supervisor's address on the internal
# hassio network: https://developers.home-assistant.io/docs/apps/presentation#ingress
INGRESS_PEER = "172.30.32.2"


class Secret:
    """A string that never shows up in repr/str/format output or logs."""

    __slots__ = ("_value",)

    def __init__(self, value: str | None) -> None:
        self._value = value or ""

    def reveal(self) -> str:
        return self._value

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "Secret(****)" if self._value else "Secret(<empty>)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        return repr(self)

    def __reduce__(self):  # pragma: no cover - defensive, never pickle secrets
        raise TypeError("Secret values cannot be pickled")


def _peers_from_env(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return (INGRESS_PEER,)
    return tuple(p.strip() for p in raw.split(",") if p.strip())


@dataclass(frozen=True)
class Settings:
    supervisor_url: str = "http://supervisor"
    core_api_url: str = "http://supervisor/core/api"
    core_ws_url: str = "ws://supervisor/core/websocket"
    token: Secret = field(default_factory=lambda: Secret(None))
    host: str = "0.0.0.0"
    port: int = 8099
    allowed_peers: tuple[str, ...] = (INGRESS_PEER,)
    # Music Assistant's server answers GET /info without auth on this port.
    music_assistant_port: int = 8095
    data_dir: str = "/data"

    @property
    def allow_any_peer(self) -> bool:
        return "*" in self.allowed_peers

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ if env is None else env)
        supervisor_url = env.get("HOME_STARTER_SUPERVISOR_URL", "http://supervisor").rstrip("/")
        default_ws = supervisor_url.replace("https://", "wss://").replace("http://", "ws://")
        return cls(
            supervisor_url=supervisor_url,
            core_api_url=env.get("HOME_STARTER_CORE_API_URL", f"{supervisor_url}/core/api").rstrip("/"),
            core_ws_url=env.get("HOME_STARTER_CORE_WS_URL", f"{default_ws}/core/websocket"),
            token=Secret(env.get("SUPERVISOR_TOKEN")),
            host=env.get("HOME_STARTER_HOST", "0.0.0.0"),
            port=int(env.get("HOME_STARTER_PORT", "8099")),
            allowed_peers=_peers_from_env(env.get("HOME_STARTER_ALLOWED_PEERS")),
            music_assistant_port=int(env.get("HOME_STARTER_MA_PORT", "8095")),
            data_dir=env.get("HOME_STARTER_DATA_DIR", "/data"),
        )
