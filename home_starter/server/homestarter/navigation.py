"""Home Assistant frontend paths that Home Starter hands the user to.

All paths are same-origin paths inside the HA frontend. They are derived from
runtime data (app slugs, HA version) rather than hard-coded URLs, and use the
frontend's own ``/_my_redirect/<name>`` router where one exists, because that
router maps a stable name onto whatever the current frontend's route is
(see frontend src/panels/my/ha-panel-my.ts).
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

_SLUG = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DOMAIN = re.compile(r"^[a-z0-9_]{1,64}$")
_VERSION = re.compile(r"^(\d{4})\.(\d{1,2})")

# HA 2026.2 removed the Supervisor panel and introduced the generic
# ``/app/<slug>`` ingress panel (homeassistant/components/hassio/__init__.py
# registers the built-in "app" panel). Older frontends use
# ``/hassio/ingress/<slug>``.
APP_PANEL_SINCE = (2026, 2)


def parse_ha_version(version: str | None) -> tuple[int, int] | None:
    if not version:
        return None
    match = _VERSION.match(str(version))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def has_app_panel(ha_version: str | None) -> bool:
    parsed = parse_ha_version(ha_version)
    # Unknown version: assume a current frontend.
    return parsed is None or parsed >= APP_PANEL_SINCE


def _slug(slug: str) -> str:
    if not _SLUG.match(slug or ""):
        raise ValueError(f"invalid app slug: {slug!r}")
    return slug


def _domain(domain: str) -> str:
    if not _DOMAIN.match(domain or ""):
        raise ValueError(f"invalid integration domain: {domain!r}")
    return domain


def _my(name: str, **params: str) -> str:
    query = urlencode({k: v for k, v in params.items() if v})
    return f"/_my_redirect/{name}" + (f"?{query}" if query else "")


def app_ui_path(slug: str, ha_version: str | None) -> str:
    """Path that opens an app's ingress web UI inside Home Assistant."""
    slug = _slug(slug)
    if has_app_panel(ha_version):
        return f"/app/{slug}"
    return f"/hassio/ingress/{slug}"


def app_info_path(slug: str, repository_url: str | None = None) -> str:
    """The app's page in the App Store (offers Install / Start / Open)."""
    # ``supervisor_addon`` with ``addon=`` is understood by both old and new
    # frontends; new ones map it to /config/app/<slug>/info and add the
    # repository first when ``repository_url`` is given and missing.
    return _my("supervisor_addon", addon=_slug(slug), repository_url=repository_url or "")


def add_repository_path(repository_url: str) -> str:
    return _my("supervisor_add_addon_repository", repository_url=repository_url)


def app_store_path() -> str:
    return _my("supervisor_store")


def integration_path(domain: str) -> str:
    return _my("integration", domain=_domain(domain))


def config_flow_start_path(domain: str) -> str:
    return _my("config_flow_start", domain=_domain(domain))


def integrations_dashboard_path() -> str:
    # Discovered (not yet confirmed) integrations are listed here.
    return "/config/integrations/dashboard"


def is_safe_ha_path(path: str) -> bool:
    """Only same-origin absolute paths; no scheme, no protocol-relative URLs."""
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return False
    if "\\" in path or any(ord(c) < 0x20 for c in path):
        return False
    return ":" not in path.split("?", 1)[0]
