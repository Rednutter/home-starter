"""Install the pinned MA guard from a reviewed source bundle; no network or secrets.

Run with MA's Python inside the existing container, then restart MA. Its /data,
providers, users and configuration are untouched. Re-running is idempotent.
An upstream image replacement removes this hook; Home Starter then fails closed
for Spotify and reports account protection incomplete until reviewed/reinstalled.
"""

import argparse
import hashlib
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

BASELINE = "8c9baf664fa86cf1584635fc5a4879333c01a9981be3460cbfcdcf142c92a40e"
ANCHOR = "        self._register_api_commands()\n"
HOOK = ANCHOR + "        from home_starter_ma.ma_account_guard import install as install_household_guard\n        install_household_guard(self)\n"
MODULES = ("household_music.py", "spotify_leases.py", "ma_account_guard.py", "ma_media.py", "media_discovery.py", "media_hygiene.py", "ma_radio.py")
SUPPORTED_VERSIONS = {"2.10.6", "2.10.7"}


def installed_version():
    try:
        return version("music_assistant")
    except PackageNotFoundError:
        raise ValueError("Run the installer inside the reviewed Music Assistant environment. Nothing was installed.") from None


def install(target, source, *, check=False):
    if installed_version() not in SUPPORTED_VERSIONS:
        raise ValueError("This MA version has not been reviewed. Nothing was installed.")
    target, source = Path(target), Path(source)
    original = target.read_text(encoding="utf-8")
    baseline = original.replace(HOOK, ANCHOR)
    if baseline.count(ANCHOR) != 1 or hashlib.sha256(baseline.encode()).hexdigest() != BASELINE:
        raise ValueError("MA source does not match the reviewed 2.10.6/2.10.7 baseline. Nothing was installed.")
    code = {name: (source / name).read_text(encoding="utf-8") for name in MODULES}
    for name, text in code.items():
        compile(text, name, "exec")
    patched = baseline.replace(ANCHOR, HOOK)
    compile(patched, str(target), "exec")
    if check:
        return "Compatible baseline and guard sources verified; no files changed."
    destination = target.parent.parent / "home_starter_ma"
    destination.mkdir(exist_ok=True)
    for name, text in {"__init__.py": "", **code}.items():
        path = destination / name
        temporary = path.with_suffix(".install-tmp")
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    if original != patched:
        backup = target.with_suffix(".home-starter-original")
        if not backup.exists():
            backup.write_text(baseline, encoding="utf-8", newline="\n")
        temporary = target.with_suffix(".install-tmp")
        temporary.write_text(patched, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    return "Guard installed; restart MA to activate. Existing accounts and data preserved."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, help="Explicit installed music_assistant/mass.py")
    parser.add_argument("--source", required=True, help="Directory containing the reviewed account and media adapter modules")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(install(args.target, args.source, check=args.check))
