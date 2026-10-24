"""Verify the normal Supervisor Docker context contains the reviewed UI build."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "home_starter/server/homestarter/static/media-preview"
EXPECTED = "180ba432af1a922f339ef5236caec6d4a7aebda057ad50286a1409a5d6664e41"  # pragma: allowlist secret -- reviewed public manifest


def verify():
    body = (STATIC / "manifest.json").read_bytes()
    assert hashlib.sha256(body).hexdigest() == EXPECTED, "Committed manifest changed without review"
    manifest = json.loads(body)
    built = ROOT / ".runtime/ma-household-upstream/household-release-dist"
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((STATIC / name).read_bytes()).hexdigest() == digest, "Committed asset differs: " + name
        assert hashlib.sha256((built / name).read_bytes()).hexdigest() == digest, "Fresh compiled asset differs: " + name
    for name in ("UPSTREAM-LICENSE", "THIRD-PARTY-NOTICES.txt", "dependency-inventory.json"):
        assert (STATIC / name).is_file(), "Dependency notice missing"
    print("Normal add-on context contains all " + str(len(manifest["files"])) + " exact reviewed and freshly compiled assets.")


if __name__ == "__main__":
    verify()
