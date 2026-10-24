"""Inspect tracked/index content without printing sensitive values. Manual review is still required."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from detect_secrets import SecretsCollection
from detect_secrets.settings import default_settings

RUNTIME = {
    "music-read-bindings.json",
    "music-read-bindings.tmp",
    "playlist-visibility.json",
    "playlist-visibility.tmp",
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

MEDIA_BUNDLE = "home_starter/server/homestarter/static/media-preview/"
# Exact reviewed public build artifacts, not a directory-wide privacy exception.
# Every asset is bound to the previously tested CI manifest; changed/new content
# requires a fresh build review. Household runtime files never enter this map.
MEDIA_MANIFEST_SHA = "180ba432af1a922f339ef5236caec6d4a7aebda057ad50286a1409a5d6664e41"  # pragma: allowlist secret
MEDIA_NOTICES = {
    "UPSTREAM-LICENSE": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",  # pragma: allowlist secret
    "THIRD-PARTY-NOTICES.txt": "79564c427e669427badb683e786de60b11df462398fcefce2ebe3e92d9822810",  # pragma: allowlist secret
    "dependency-inventory.json": "b2d8bce5948830160e5fb2807b88c532872f4f00e9ab52d7ee850498c505a137",  # pragma: allowlist secret
}


def reviewed_media(manifest: bytes) -> dict[str, str]:
    if hashlib.sha256(manifest).hexdigest() != MEDIA_MANIFEST_SHA:
        raise ValueError("Generated media manifest needs an exact-artifact privacy review.")
    files = json.loads(manifest)["files"]
    return {MEDIA_BUNDLE + name: value for name, value in {**files, **MEDIA_NOTICES, "manifest.json": MEDIA_MANIFEST_SHA}.items()}


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
            "home_starter/server/homestarter/static/decor-saucer.webp",
            "home_starter/server/homestarter/static/decor-owl.webp",
            "home_starter/server/homestarter/static/bin-general.webp",
            "home_starter/server/homestarter/static/bin-recycling.webp",
            "home_starter/server/homestarter/static/bin-organics.webp",
            "home_starter/server/homestarter/static/decor-atlas.webp",
            *(
                f"home_starter/server/homestarter/static/wallpapers/{period}-{name}.webp"
                for period, names in {
                    "morning": ("blue-hour", "river-mist", "granite-sunrise", "coastal-dawn"),
                    "day": ("alpine-lake", "river-gums", "high-country", "coastal-bay"),
                    "afternoon": ("valley-light", "riverbank", "granite-country", "coastal-grass"),
                    "evening": ("golden-hills", "river-sunset", "coastal-dusk", "alpine-dusk"),
                    "night": ("moonlit-valley", "river-stars", "alpine-stars", "coastal-moon"),
                }.items()
                for name in names
            ),
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
    reviewed = {}
    manifest_path = MEDIA_BUNDLE + "manifest.json"
    if manifest_path in paths:
        manifest = subprocess.check_output([git, "show", ":" + manifest_path]) if args.staged else Path(manifest_path).read_bytes()  # noqa: S603
        try:
            reviewed = reviewed_media(manifest)
            issues.extend(f"{name}: reviewed release artifact missing" for name in reviewed if name not in paths)
        except (ValueError, KeyError):
            issues.append("Generated media manifest needs an exact-artifact privacy review.")
    with default_settings():
        for path in filter(None, paths):
            if path == ".secrets.baseline":
                continue  # Reviewed one-way hashes, not source values; inspect baseline changes manually.
            if path.startswith(MEDIA_BUNDLE):
                body = subprocess.check_output([git, "show", ":" + path]) if args.staged else Path(path).read_bytes()  # noqa: S603
                if reviewed.get(path) != hashlib.sha256(body).hexdigest():
                    issues.append(f"{path}: generated content differs from reviewed public artifact")
                continue
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
