"""Fail image builds if the committed household UI was omitted or changed."""

import hashlib
import json
from pathlib import Path

EXPECTED = "8ab3d73fad1636dec971038d921ddeb3d6851875f452accbee9ce0fec28c0afb"  # pragma: allowlist secret -- public build manifest


def verify(root=None):
    root = root or Path(__file__).parent / "static/media-preview"
    body = (root / "manifest.json").read_bytes()
    if hashlib.sha256(body).hexdigest() != EXPECTED:
        raise ValueError("Reviewed household UI manifest missing or changed.")
    files = json.loads(body)["files"]
    for name, digest in files.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Reviewed household UI asset missing or changed.")
    for name in ("UPSTREAM-LICENSE", "THIRD-PARTY-NOTICES.txt", "dependency-inventory.json"):
        if not (root / name).is_file():
            raise ValueError("Household UI dependency notices missing.")
    print("Image contains " + str(len(files)) + " verified household UI assets and notices.")


if __name__ == "__main__":
    verify()
