from pathlib import Path

import pytest
from check_ma_release_contracts import RELEASES, inspect_release
from homestarter.ma_compatibility import READ_PROBES

ROOT = Path(__file__).resolve().parents[1] / ".runtime/ma-release-sources"


@pytest.mark.parametrize("version", list(RELEASES))
def test_actual_official_release_read_parameters_and_native_pin_boundaries(version):
    if not (ROOT / version / "manifest.json").is_file():
        pytest.skip("Official release source fixture is absent; source contracts are unrun")
    report = inspect_release(ROOT, version)
    for name, args in READ_PROBES:
        record = report["artist_library"] if name == "music/artists/library_items" else report["public"][name]
        assert record and set(args) <= set(record["params"])
    assert report["public"]["auth/users"]["scope"] == "Scope.USERS_READ"
    assert report["public"]["players/all"]["scope"] == "Scope.PLAYERS_READ"
    assert all(report["guard_signature_shapes"].values())
    if version == "2.10.7":
        assert all(report["transfer_source_pins"].values())
    else:
        assert not all(report["transfer_source_pins"].values())
    assert not report["running_server_tested"] and not report["playback_enforcement_attested"]
