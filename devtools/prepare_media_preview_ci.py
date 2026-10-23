"""Fetch only the reviewed public MA source archive for reproducible CI builds."""

import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PIN = "dc3caf60f124301a32e21bcb053523d2451a6bfa"  # pragma: allowlist secret -- public upstream commit
ARCHIVE_SHA = "3f13ca9cb443e877f0c29f170cb52a74cf10ee9081b532d895649c64efafcfef"  # pragma: allowlist secret -- public archive SHA256


def prepare():
    runtime = ROOT / ".runtime"
    target = runtime / "ma-household-upstream"
    stage = runtime / "ma-frontend-ci-source"
    if target.exists() or stage.exists():
        raise ValueError("Use a clean CI checkout; existing source directories are preserved.")
    runtime.mkdir(exist_ok=True)
    request = Request("https://codeload.github.com/music-assistant/frontend/tar.gz/" + PIN, headers={"User-Agent": "HomeStarter-CI"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 -- fixed reviewed HTTPS source, no client URL
        blob = response.read(32 * 1024 * 1024 + 1)
    if len(blob) > 32 * 1024 * 1024 or hashlib.sha256(blob).hexdigest() != ARCHIVE_SHA:
        raise ValueError("The reviewed upstream archive hash did not match.")
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        archive.extractall(stage, filter="data")  # noqa: S202 -- verified archive plus safe data filter
    extracted = stage / ("frontend-" + PIN)
    if extracted.resolve().parent != stage.resolve() or target.resolve().parent != runtime.resolve():
        raise ValueError("Unexpected source directory.")
    extracted.rename(target)
    pin = runtime / "ma-frontend-readonly/source-pin.json"
    pin.parent.mkdir(exist_ok=True)
    pin.write_text(json.dumps({"tag": "2.17.297.post1", "commit": PIN, "archive_sha256": ARCHIVE_SHA}), newline="\n")
    print("Verified reviewed public upstream archive; dependencies not installed by this helper.")


if __name__ == "__main__":
    prepare()
