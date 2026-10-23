"""Fail image builds if the committed household UI was omitted or changed."""

import hashlib
import json
from pathlib import Path

EXPECTED = "fd26d680c1824eaf0f012e8e5860010a51ea41774f1c1be6d66352c838a2027f"  # pragma: allowlist secret -- public build manifest


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
