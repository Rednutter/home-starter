"""Operator safety prerequisites, without a Docker daemon or household inputs."""

import pytest
from ma2108_offline_payload import receipt_check, supervisor_gate


def receipt():
    return {
        "schema": 1,
        "ma_version": "2.10.7",
        "hs_version": "0.8.47",
        "backup_sha256": "synthetic-backup-checksum",
        "rollback_image": "synthetic-immutable-image",
        "scopes": ["d5369777_music_assistant", "6726420e_home_starter"],
        "stopped_consistent": True,
        "recovery_key_available": True,
    }


def test_matching_backup_receipt_is_an_explicit_prerequisite():
    receipt_check(receipt(), "synthetic-backup-checksum", "synthetic-immutable-image")


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", 2),
        ("ma_version", "2.10.8"),
        ("hs_version", "unknown"),
        ("scopes", []),
        ("stopped_consistent", False),
        ("recovery_key_available", False),
        ("backup_sha256", "changed"),
        ("rollback_image", "changed"),
    ],
)
def test_missing_or_changed_rollback_prerequisite_is_refused(key, value):
    row = receipt()
    row[key] = value
    with pytest.raises(ValueError, match="receipt"):
        receipt_check(row, "synthetic-backup-checksum", "synthetic-immutable-image")


@pytest.mark.parametrize("version", [None, "", "2026.10.3", "ci", "operator-approved"])
def test_no_unreviewed_supervisor_can_enable_target_writes(version):
    with pytest.raises(ValueError, match="unreviewed"):
        supervisor_gate(version)
