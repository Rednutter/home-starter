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


def test_review_archive_is_reproducible_across_creation_permissions(tmp_path, monkeypatch):
    import os
    import tarfile

    import prepare_ma2108_candidate as builder

    source = tmp_path / "home_starter/server/homestarter"
    source.mkdir(parents=True)
    (source / "ma_release_review.py").write_bytes(b"from .helper import Example\n")
    (source / "helper.py").write_bytes(b"class Example: pass\r\n")
    installer = tmp_path / "devtools/install_ma2108_candidate.py"
    installer.parent.mkdir()
    installer.write_bytes(b"# Synthetic installer fixture\n")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    old = os.umask(0o077)
    try:
        first = builder.prepare(tmp_path / ".runtime/first")
        (source / "helper.py").write_bytes(b"class Example: pass\n")
        os.umask(0o022)
        second = builder.prepare(tmp_path / ".runtime/second")
    finally:
        os.umask(old)
    assert first["archive_sha256"] == second["archive_sha256"]
    with tarfile.open(tmp_path / ".runtime/second/ma2108-review-candidate.tar") as archive:
        assert all(member.mode == 0o644 for member in archive)
        assert b"\r\n" not in archive.extractfile("home_starter_ma/contract.json").read()
