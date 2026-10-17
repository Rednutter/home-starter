"""Inspect tracked/index content without printing sensitive values. Manual review is still required."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

RUNTIME = {
    "media-catalogue.json",
    "media-catalogue.tmp",
    "home-starter-radio.json",
    "home-starter-radio.tmp",
    "home-starter-spotify-leases.json",
    "home-starter-spotify-leases.tmp",
    "home-starter-spotify-checks.json",
    "home-starter-spotify-checks.tmp",
    "home-starter-spotify-identities.json",
    "home-starter-spotify-identities.tmp",
    "music-identity-auth.json",
    "music-identity-auth.tmp",
    "calendar-access.json",
    "calendar-access.tmp",
    "household-services.json",
    "household-services.tmp",
    "endpoint-connections.json",
    "endpoint-connections.tmp",
    "household.json",
    "activity.json",
    "publications.json",
    "installation.json",
    "inventory-history.json",
    "reset-history.json",
    "readiness.json",
    "commissioning.json",
    "house-confirmations.json",
    "house-confirmations.tmp",
    "screen-commissioning.json",
    "waste-collection.json",
    "waste-collection.tmp",
    "screen-commissioning.tmp",
    "music-connection.json",
    "music-connection.tmp",
    "music-listeners.json",
    "music-listeners.tmp",
    "music-playback.json",
    "music-playback.tmp",
}
CONTACT = re.compile(r"[\w.+-]+@([\w.-]+\.[A-Za-z]{2,})")
KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}")


def inspect_text(path: str, text: str) -> list[str]:
    issues = []
    for line_no, line in enumerate(text.splitlines(), 1):
        contacts = CONTACT.findall(line)
        if path == "devtools/kitchen_wall/install-voice-firewall.sh" and line == "Before=user@" + "1000.service":
            contacts = []  # systemd user-manager unit, not a contact address.
        if any(not (d in ("example.com", "example.org", "example.net", "example.invalid") or d.endswith(".example")) for d in contacts):
            issues.append(f"{path}:{line_no}: non-example contact address")
        if KEY.search(line):
            issues.append(f"{path}:{line_no}: credential material")
    if path.startswith("tests/fixtures/") and path.endswith(".json"):
        try:

            def check(value):
                if isinstance(value, dict):
                    if any(value.get(k) not in (None, 0, 0.0) for k in ("latitude", "longitude")):
                        issues.append(f"{path}: non-neutral coordinates")
                    entity = value.get("entity_id", "")
                    attrs = value.get("attributes") or {}
                    if (
                        entity.startswith("person.")
                        and attrs.get("friendly_name")
                        and not attrs["friendly_name"].startswith(("Fixture", "Test", "Adult", "Child", "Example"))
                    ):
                        issues.append(f"{path}: person fixture needs a synthetic identity")
                    for child in value.values():
                        check(child)
                elif isinstance(value, list):
                    for child in value:
                        check(child)

            check(json.loads(text))
        except (ValueError, TypeError, AttributeError):
            issues.append(f"{path}: invalid fixture structure")
    return issues


def secret_findings(path: str, text: str, allowed: set[tuple[str, str, str]]) -> list[str]:
    # Scan exact index contents, with the scanner's normal file/context filters.
    with TemporaryDirectory(prefix="home-starter-privacy-") as directory:
        target = Path(directory) / Path(path).name
        target.write_text(text, encoding="utf-8")
        collection = SecretsCollection()
        collection.scan_file(str(target))
        return [
            f"{path}:{s['line_number']}: unreviewed {s['type']}"
            for rows in collection.json().values()
            for s in rows
            if (path, s["type"], s["hashed_secret"]) not in allowed
        ]


def forbidden_path(path: str) -> bool:
    p = Path(path)
    return (
        p.name in RUNTIME
        or path.startswith(("screens/", "data/", ".runtime/"))
        or p.name.startswith(".env")
        and p.name != ".env.example"
        or p.suffix in (".db", ".sqlite", ".sqlite3", ".har", ".log", ".key", ".pem")
        or p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        and path
        not in (
            "home_starter/icon.png",
            "home_starter/logo.png",
            "home_starter/server/homestarter/static/wall-morning.jpg",
            *(f"home_starter/server/homestarter/static/panel-{kind}.jpg" for kind in ("room", "today", "call", "cameras", "media")),
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="Inspect the exact index content rather than working files.")
    args = parser.parse_args()
    git = shutil.which("git")
    if not git:
        raise SystemExit("Git is required for privacy inspection.")
    if args.staged:
        baseline_text = subprocess.check_output([git, "show", ":.secrets.baseline"]).decode()  # noqa: S603 -- fixed index lookup
    else:
        baseline_text = Path(".secrets.baseline").read_text(encoding="utf-8")
    baseline = json.loads(baseline_text)
    allowed = {
        (path.replace("\\", "/"), s["type"], s["hashed_secret"]) for path, rows in baseline["results"].items() for s in rows if s.get("is_secret") is False
    }
    listing = [git, "ls-files", "-z"]
    if not args.staged:
        listing += ["--cached", "--others", "--exclude-standard"]
    paths = sorted(set(subprocess.check_output(listing).decode().split("\0")))  # noqa: S603 -- fixed Git command, no shell
    issues = []
    with default_settings():
        for path in filter(None, paths):
            if path == ".secrets.baseline":
                continue  # Reviewed one-way hashes, not source values; inspect baseline changes manually.
            if forbidden_path(path):
                issues.append(f"{path}: runtime/private artifact must not be tracked")
                continue
            body = subprocess.check_output([git, "show", ":" + path]) if args.staged else Path(path).read_bytes()  # noqa: S603 -- index path as one argument
            if b"\0" not in body:
                text = body.decode("utf-8", errors="replace")
                issues.extend(inspect_text(path, text))
                issues.extend(secret_findings(path, text, allowed))
    for issue in sorted(set(issues)):
        print(issue)
    print(f"Privacy check: {'FAILED' if issues else 'OK'} ({len(list(filter(None, paths)))} source files; values withheld).")
    return bool(issues)


if __name__ == "__main__":
    raise SystemExit(main())
