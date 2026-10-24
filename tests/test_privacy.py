"""Synthetic probes for privacy boundaries; never use a real credential in a test."""

import fnmatch
import json
import logging
import shutil
import subprocess
from pathlib import Path

import pytest
from detect_secrets.settings import default_settings
from homestarter.household import HouseholdStore
from homestarter.privacy import PrivacyFilter, redact
from privacy_check import forbidden_path, inspect_text, reviewed_media


def test_runtime_store_refuses_tracked_product_directories():
    root = Path(__file__).resolve().parent.parent
    for path in (root, root / "home_starter", root / "tests", root / "home_starter/server/homestarter/runtime"):
        with pytest.raises(ValueError, match="source"):
            HouseholdStore(str(path))


def test_generated_release_exception_requires_exact_reviewed_manifest():
    root = Path("home_starter/server/homestarter/static/media-preview")
    body = (root / "manifest.json").read_bytes()
    reviewed = reviewed_media(body)
    assert len(reviewed) == 485
    assert str(root / "private-household.png").replace("\\", "/") not in reviewed
    with pytest.raises(ValueError, match="privacy review"):
        reviewed_media(body + b" ")
    import hashlib

    name = str(root / "index.html").replace("\\", "/")
    assert hashlib.sha256((root / "index.html").read_bytes() + b"changed").hexdigest() != reviewed[name]


def test_normal_docker_context_admits_only_exact_reviewed_media_files():
    from homestarter.release_assets import verify

    # Execute the same verifier Docker runs, not only the host manifest check.
    verify()
    patterns = Path("home_starter/.dockerignore").read_text().splitlines()
    prefix = "server/homestarter/static/media-preview/"
    files = json.loads(Path("home_starter", prefix, "manifest.json").read_bytes())["files"]
    assert all("!" + prefix + name in patterns for name in files)
    assert not any("*" in p for p in patterns if prefix in p)
    assert "python3 -m homestarter.release_assets" in Path("home_starter/Dockerfile").read_text()


def test_ignored_runtime_paths_and_source_visibility():
    paths = [
        "data/household.json",
        ".runtime/installation.json",
        ".env",
        ".env.local",
        "screens/capture.json",
        "screens/runtime.db",
        "screens/private.png",
        "local-credentials.json",
        "local-token.txt",
        "music-connection.json",
        "music-connection.tmp",
        "music-playback.json",
        "house-confirmations.json",
        "house-confirmations.tmp",
    ]
    git = shutil.which("git")
    result = subprocess.check_output([git, "check-ignore", "--no-index", *paths], text=True).splitlines()  # noqa: S603 -- synthetic literal paths
    assert set(result) == set(paths)
    assert subprocess.run([git, "check-ignore", "--no-index", "home_starter/server/homestarter/reconcile.py"], capture_output=True).returncode == 1  # noqa: S603


def test_packaging_uses_deny_by_default_source_allowlist():
    patterns = [p for p in Path("home_starter/.dockerignore").read_text().splitlines() if p and not p.startswith("#")]
    assert patterns[0] == "**"

    def included(path):
        result = True
        for rule in patterns:
            if fnmatch.fnmatchcase(path, rule.lstrip("!")):
                result = rule.startswith("!")
        return result

    assert included("server/homestarter/household.py")
    assert included("server/homestarter/static/wall-morning.jpg")
    assert included("server/homestarter/static/wall-imagery.json")
    assert included("server/homestarter/static/wallpapers.json")
    for name in ("saucer", "owl", "atlas"):
        path = "home_starter/server/homestarter/static/decor-" + name + ".webp"
        assert included(path.removeprefix("home_starter/"))
        assert not forbidden_path(path)
    assert forbidden_path("home_starter/server/homestarter/static/decor-private.webp")
    assert included("server/homestarter/static/wallpapers/night-moonlit-valley.webp")
    for row in json.loads(Path("home_starter/server/homestarter/static/wallpapers.json").read_text())["images"]:
        assert included("server/homestarter/static/wallpapers/" + row["file"])
    assert not included("server/homestarter/static/wallpapers/private-wall-capture.webp")
    assert not included("server/homestarter/static/household-photo.jpg")
    for path in ("data/household.json", "server/homestarter/household.json", ".env", "screens/capture.png", "runtime.db", "server/homestarter/private.key"):
        assert not included(path)


def test_private_runtime_paths_cannot_be_forced_into_a_release():
    for path in (
        "data/household.json",
        "readiness.json",
        "commissioning.json",
        "music-connection.json",
        "music-playback.json",
        "house-confirmations.json",
        "house-confirmations.tmp",
        "screens/capture.png",
        ".env",
        "dump.db",
        "secret.pem",
    ):
        assert forbidden_path(path)
    assert not forbidden_path("home_starter/icon.png")
    assert not forbidden_path("tests/test_privacy.py")


def test_contacts_and_non_neutral_fixture_coordinates_are_rejected_without_values():
    contact = "member@" + "private.invalid"
    with default_settings():
        issues = inspect_text("tests/fixtures/example.json", '{"email":"' + contact + '","latitude":1.5}')
    assert any("contact address" in i for i in issues) and any("coordinates" in i for i in issues)
    assert contact not in str(issues)


def test_reviewed_wall_asset_and_systemd_unit_do_not_admit_private_artifacts():
    assert not forbidden_path("home_starter/server/homestarter/static/wall-morning.jpg")
    assert not forbidden_path("home_starter/server/homestarter/static/wallpapers/night-moonlit-valley.webp")
    assert forbidden_path("home_starter/server/homestarter/static/wallpapers/private-wall-capture.webp")
    assert forbidden_path("home_starter/server/homestarter/static/household-photo.jpg")
    script = "devtools/kitchen_wall/install-voice-firewall.sh"
    assert not inspect_text(script, "Before=user@" + "1000.service")
    assert inspect_text("other.sh", "Before=user@" + "1000.service")
    assert inspect_text(script, "Contact=person@" + "private.invalid")


def test_nested_known_secrets_and_log_arguments_are_redacted():
    sentinel = "fixture-" + "private-value"
    value = {"password": sentinel, "nested": {"access_token": sentinel}, "message": sentinel}
    assert sentinel not in str(redact(value, (sentinel,)))
    record = logging.LogRecord("fixture", logging.INFO, __file__, 1, "Diagnostic %s", (value,), None)
    assert PrivacyFilter((sentinel,)).filter(record)
    assert sentinel not in record.getMessage()
    assert "[redacted]" in record.getMessage()
