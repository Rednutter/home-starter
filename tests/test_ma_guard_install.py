"""Pinned startup hook installation is reviewed, idempotent and source-only."""

import hashlib

import install_ma_guard as installer
import pytest


def test_installer_checks_baseline_before_writes_and_reconciles_idempotently(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "installed_version", lambda: "2.10.7")
    package = tmp_path / "music_assistant"
    package.mkdir()
    target = package / "mass.py"
    baseline = "class Example:\n    def start(self):\n" + installer.ANCHOR
    target.write_text(baseline, encoding="utf-8")
    monkeypatch.setattr(installer, "BASELINE", hashlib.sha256(baseline.encode()).hexdigest())
    source = tmp_path / "reviewed"
    source.mkdir()
    for name in installer.MODULES:
        (source / name).write_text('"""Synthetic guard module."""\n', encoding="utf-8")
    assert "no files changed" in installer.install(target, source, check=True)
    assert not (tmp_path / "home_starter_ma").exists()
    installer.install(target, source)
    assert target.read_text().count("install_household_guard(self)") == 1
    assert target.with_suffix(".home-starter-original").read_text() == baseline
    installed = target.read_bytes()
    installer.install(target, source)
    assert target.read_bytes() == installed
    target.write_text(baseline + "# upstream change\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Nothing was installed"):
        installer.install(target, source)
    assert "# upstream change" in target.read_text()


def test_installer_rejects_unreviewed_version_before_reading_or_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(installer, "installed_version", lambda: "2.10.8")
    with pytest.raises(ValueError, match="version has not been reviewed"):
        installer.install(tmp_path / "mass.py", tmp_path / "source")
    assert not list(tmp_path.iterdir())
