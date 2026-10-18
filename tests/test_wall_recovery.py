from kitchen_wall.display import OFFLINE, recovery_target
from kitchen_wall.install_cursor import environment, transparent_cursor


def test_connection_fallback_needs_two_failed_reads_and_restores_only_the_owned_board():
    board, fallback = "https://example.com/home-starter-example/home?kiosk", "file:///example/offline.html"
    assert recovery_target(False, False, 0, board, fallback) == (None, 1)
    assert recovery_target(False, False, 1, board, fallback) == (fallback, 2)
    assert recovery_target(False, True, 2, board, fallback) == (None, 3)
    assert recovery_target(True, True, 3, board, fallback) == (board, 0)
    assert recovery_target(True, False, 0, board, fallback) == (None, 0)
    assert "Waiting for Home Assistant" in OFFLINE
    assert "fetch(" not in OFFLINE and "localStorage" not in OFFLINE


def test_cursor_fallback_and_wayland_theme_are_permanent_and_idempotent():
    assert "html,body,#root,#app,*{cursor:none!important}" in OFFLINE
    original = "XKB_DEFAULT_LAYOUT=us\nXCURSOR_THEME=old\nXCURSOR_SIZE=32\n"  # pragma: allowlist secret -- synthetic cursor environment, no credentials
    updated = environment(original)
    assert updated == environment(updated)
    assert "XKB_DEFAULT_LAYOUT=us" in updated and "XCURSOR_THEME=old" not in updated
    assert updated.count("XCURSOR_THEME=") == 1 and "XCURSOR_SIZE=24" in updated
    cursor = transparent_cursor()
    assert cursor[:4] == b"Xcur" and len(cursor) == 68
    assert cursor[-4:] == b"\0\0\0\0"
