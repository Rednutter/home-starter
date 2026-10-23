"""Prepare an ignored release context with pinned household audio assets.

No upload, install, service change, credential read or deployment is performed.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = "dc3caf60f124301a32e21bcb053523d2451a6bfa"  # pragma: allowlist secret -- public reviewed upstream commit
PREVIEW_FILES = {
    "server/homestarter/server.py",
    "server/homestarter/household_lan.py",
    "server/homestarter/music_runtime.py",
    "server/homestarter/media_preview.py",
    "server/homestarter/catalogue_preview.py",
    "server/homestarter/metadata_projection.py",
    "server/homestarter/media_discovery.py",
    "server/homestarter/playlist_visibility.py",
}
CONTROLS = {
    "server/homestarter/listening.py",
    "server/homestarter/static/media-app.js",
    "server/homestarter/static/media-app.css",
    "server/homestarter/static/media.html",
}


def package(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / ".runtime") or output.exists():
        raise ValueError("Choose a new ignored .runtime release directory.")
    source = ROOT / ".runtime/ma-household-upstream/household-release-dist"
    if not (source / "index.html").is_file():
        raise ValueError("Build household-release mode first.")
    pin = json.loads((ROOT / ".runtime/ma-frontend-readonly/source-pin.json").read_text())
    if pin["commit"] != PIN:
        raise ValueError("The upstream source pin changed.")
    git = shutil.which("git")
    if not git:
        raise ValueError("Git is required to identify source-only release files.")
    paths = (
        subprocess.check_output(  # noqa: S603 -- resolved Git, fixed arguments, no shell
            [git, "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", "home_starter"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    for name in filter(None, paths):
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output([git, "show", "HEAD:" + name], cwd=ROOT))  # noqa: S603 -- fixed Git blob read
    for relative in sorted(PREVIEW_FILES):
        name = "home_starter/" + relative
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    destination = output / "home_starter/server/homestarter/static/media-preview"
    destination.mkdir(parents=True)
    files = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix == ".map":
            continue
        relative = path.relative_to(source)
        if relative.parts[0] != "assets" and str(relative) != "index.html":
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        files[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    shutil.copyfile(ROOT / ".runtime/ma-household-upstream/LICENSE", destination / "UPSTREAM-LICENSE")
    dependencies = ROOT / ".runtime/ma-household-upstream/node_modules/.pnpm"
    packages = sorted({*dependencies.glob("*/node_modules/*/package.json"), *dependencies.glob("*/node_modules/@*/*/package.json")})
    notices, seen, inventory = [], set(), []
    for package_path in packages:
        info = json.loads(package_path.read_text(encoding="utf-8"))
        key = (info.get("name"), info.get("version"))
        if key in seen:
            continue
        seen.add(key)
        inventory.append({"name": key[0], "version": key[1], "license": info.get("license")})
        notices.append(str(key[0]) + " " + str(key[1]) + "\nLicense: " + str(info.get("license")))
        for license_path in sorted(package_path.parent.iterdir()):
            if (
                license_path.is_file()
                and license_path.name.lower().startswith(("license", "licence", "notice", "copying"))
                and license_path.stat().st_size < 512000
            ):
                notices.append(license_path.name + "\n" + license_path.read_text(encoding="utf-8", errors="replace"))
    (destination / "THIRD-PARTY-NOTICES.txt").write_text("\n\n".join(notices), encoding="utf-8")
    (destination / "dependency-inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    manifest = {"version": 1, "upstream_commit": PIN, "upstream_version": "2.17.297.post1", "mode": "production-household", "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2))
    baseline = subprocess.check_output([git, "rev-parse", "HEAD"], cwd=ROOT).decode().strip()  # noqa: S603 -- fixed Git read
    preserved = {name: hashlib.sha256((output / "home_starter" / name).read_bytes()).hexdigest() for name in sorted(CONTROLS)}
    (output / "CANDIDATE.json").write_text(
        json.dumps(
            {
                "candidate": output.name,
                "baseline_commit": baseline,
                "preserved_controls": preserved,
                "production_version_unchanged": "0.8.42",
                "manifest_sha256": hashlib.sha256((destination / "manifest.json").read_bytes()).hexdigest(),
                "asset_count": len(files),
            },
            indent=2,
        )
    )
    return len(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    print("Prepared release context with " + str(package(parser.parse_args().output)) + " verified assets; nothing deployed.")
