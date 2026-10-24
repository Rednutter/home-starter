"""Synthetic filesystem transaction tests; never run against an installed MA."""

import hashlib
import json

import install_ma2108_candidate as installer
import pytest


@pytest.fixture
def candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "versions", lambda: ("2.10.8", "1.1.205"))
    target = tmp_path / "music_assistant/mass.py"
    target.parent.mkdir()
    original = b"class Example:\n    def start(self):\n" + installer.ANCHOR.encode()
    target.write_bytes(original)
    source = tmp_path / "candidate"
    source.mkdir()
    files = {
        name: b'"""Synthetic candidate module."""\n'
        for name in ("__init__.py", "ma_release_review.py", "ma_account_guard.py", "ma_transfer.py", "ma_control_contract.py")
    }
    for name, body in files.items():
        (source / name).write_bytes(body)
    manifest = {
        "id": "ma2108-contract-1",
        "version": "2.10.8",
        "models": "1.1.205",
        "source_pins": {"mass.py": hashlib.sha256(original).hexdigest()},
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    }
    (source / "contract.json").write_text(json.dumps(manifest))
    return target, source, original, manifest


def test_default_check_writes_nothing_then_explicit_apply_preserves_backup(candidate):
    target, source, original, _ = candidate
    assert "no files changed" in installer.install(target, source)
    assert target.read_bytes() == original and not target.with_suffix(".home-starter-2108-original").exists()
    assert "No service restarted" in installer.install(target, source, check=False)
    assert target.read_bytes().count(installer.HOOK.encode()) == 1
    assert target.with_suffix(".home-starter-2108-original").read_bytes() == original
    installer.install(target, source, check=False)
    assert target.read_bytes().count(installer.HOOK.encode()) == 1


@pytest.mark.parametrize("fault", ["source", "module", "traversal", "backup", "unrelated", "version"])
def test_faults_preserve_target_and_do_not_install(candidate, fault, monkeypatch):
    target, source, original, manifest = candidate
    if fault == "source":
        target.write_bytes(original + b"# unexpected native edit\n")
    elif fault == "module":
        (source / "ma_transfer.py").write_bytes(b"changed candidate")
    elif fault == "traversal":
        manifest["files"]["../escape.py"] = "unused"
        (source / "contract.json").write_text(json.dumps(manifest))
    elif fault == "backup":
        target.with_suffix(".home-starter-2108-original").write_bytes(b"unrelated backup")
    elif fault == "unrelated":
        dest = target.parent.parent / "home_starter_ma"
        dest.mkdir()
        (dest / "keep.py").write_bytes(b"unrelated module")
    else:
        monkeypatch.setattr(installer, "versions", lambda: ("2.10.9", "1.1.205"))
    before = target.read_bytes()
    with pytest.raises(ValueError):
        installer.install(target, source, check=False)
    assert target.read_bytes() == before
