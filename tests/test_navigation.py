"""Home Assistant navigation targets (Open Music Assistant and handoffs)."""

from __future__ import annotations

import pytest
from homestarter import navigation as nav


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("2026.10.1", "/app/d5369777_music_assistant"),
        ("2026.2.0", "/app/d5369777_music_assistant"),
        ("2026.11.0.dev202610110", "/app/d5369777_music_assistant"),
        ("2027.1.0b1", "/app/d5369777_music_assistant"),
        ("2026.1.3", "/hassio/ingress/d5369777_music_assistant"),
        ("2025.12.5", "/hassio/ingress/d5369777_music_assistant"),
        (None, "/app/d5369777_music_assistant"),
        ("garbage", "/app/d5369777_music_assistant"),
    ],
)
def test_open_app_route_by_version(version, expected):
    assert nav.app_ui_path("d5369777_music_assistant", version) == expected


def test_my_redirect_paths():
    assert nav.app_info_path("d5369777_music_assistant") == "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant"
    assert nav.app_info_path("d5369777_music_assistant", "https://github.com/music-assistant/home-assistant-addon") == (
        "/_my_redirect/supervisor_addon?addon=d5369777_music_assistant&repository_url=https%3A%2F%2Fgithub.com%2Fmusic-assistant%2Fhome-assistant-addon"
    )
    assert nav.add_repository_path("https://github.com/music-assistant/home-assistant-addon") == (
        "/_my_redirect/supervisor_add_addon_repository?repository_url=https%3A%2F%2Fgithub.com%2Fmusic-assistant%2Fhome-assistant-addon"
    )
    assert nav.config_flow_start_path("music_assistant") == "/_my_redirect/config_flow_start?domain=music_assistant"
    assert nav.integration_path("music_assistant") == "/_my_redirect/integration?domain=music_assistant"
    assert nav.app_store_path() == "/_my_redirect/supervisor_store"


@pytest.mark.parametrize("slug", ["../x", "a/b", "", "x" * 65, "a b", "a?b"])
def test_invalid_slugs_are_rejected(slug):
    with pytest.raises(ValueError):
        nav.app_ui_path(slug, "2026.10.1")


@pytest.mark.parametrize(
    ("path", "safe"),
    [
        ("/app/x", True),
        ("/_my_redirect/supervisor_addon?addon=x&repository_url=https%3A%2F%2Fgithub.com", True),
        ("/config/integrations/dashboard", True),
        ("//evil.example", False),
        ("https://evil.example", False),
        ("javascript:alert(1)", False),
        ("/\\evil", False),
        ("relative/path", False),
        ("/x\nSet-Cookie: a", False),
        ("/javascript:alert(1)", False),
    ],
)
def test_safe_path(path, safe):
    assert nav.is_safe_ha_path(path) is safe
