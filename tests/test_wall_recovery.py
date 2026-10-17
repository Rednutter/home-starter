from kitchen_wall.display import OFFLINE, recovery_target


def test_connection_fallback_needs_two_failed_reads_and_restores_only_the_owned_board():
    board, fallback = "https://example.com/home-starter-example/home?kiosk", "file:///example/offline.html"
    assert recovery_target(False, False, 0, board, fallback) == (None, 1)
    assert recovery_target(False, False, 1, board, fallback) == (fallback, 2)
    assert recovery_target(False, True, 2, board, fallback) == (None, 3)
    assert recovery_target(True, True, 3, board, fallback) == (board, 0)
    assert recovery_target(True, False, 0, board, fallback) == (None, 0)
    assert "Waiting for Home Assistant" in OFFLINE
    assert "fetch(" not in OFFLINE and "localStorage" not in OFFLINE
