"""Synthetic probes for privacy boundaries; never use a real credential in a test."""

import fnmatch
import logging
import shutil
import subprocess
from pathlib import Path

import pytest
from detect_secrets.settings import default_settings
from homestarter.household import HouseholdStore
from homestarter.privacy import PrivacyFilter, redact
from privacy_check import forbidden_path, inspect_text


def test_runtime_store_refuses_tracked_product_directories():
    root = Path(__file__).resolve().parent.parent
    for path in (root, root / "home_starter", root / "tests", root / "home_starter/server/homestarter/runtime"):
        with pytest.raises(ValueError, match="source"):
            HouseholdStore(str(path))


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
    for path in ("data/household.json", "server/homestarter/household.json", ".env", "screens/capture.png", "runtime.db", "server/homestarter/private.key"):
        assert not included(path)


def test_private_runtime_paths_cannot_be_forced_into_a_release():
    for path in ("data/household.json", "readiness.json", "screens/capture.png", ".env", "dump.db", "secret.pem"):
        assert forbidden_path(path)
    assert not forbidden_path("home_starter/icon.png")
    assert not forbidden_path("tests/test_privacy.py")


def test_contacts_and_non_neutral_fixture_coordinates_are_rejected_without_values():
    contact = "member@" + "private.invalid"
    with default_settings():
        issues = inspect_text("tests/fixtures/example.json", '{"email":"' + contact + '","latitude":1.5}')
    assert any("contact address" in i for i in issues) and any("coordinates" in i for i in issues)
    assert contact not in str(issues)


def test_nested_known_secrets_and_log_arguments_are_redacted():
    sentinel = "fixture-" + "private-value"
    value = {"password": sentinel, "nested": {"access_token": sentinel}, "message": sentinel}
    assert sentinel not in str(redact(value, (sentinel,)))
    record = logging.LogRecord("fixture", logging.INFO, __file__, 1, "Diagnostic %s", (value,), None)
    assert PrivacyFilter((sentinel,)).filter(record)
    assert sentinel not in record.getMessage()
    assert "[redacted]" in record.getMessage()
