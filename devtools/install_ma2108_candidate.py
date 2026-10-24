"""Separate, unapproved native candidate installer. Default is check-only.

Run only inside the explicitly targeted MA container after artifact review and
specific activation approval. No network, restart, account or permission changes.
"""

import argparse
import hashlib
import json
import os
import re
from importlib.metadata import version
from pathlib import Path

ANCHOR = "        self._register_api_commands()\n"
HOOK = ANCHOR + "        from home_starter_ma.ma_release_review import install as install_household_candidate\n        install_household_candidate(self)\n"


def versions():
    return version("music_assistant"), version("music-assistant-models")


def install(target, source, *, check=True):
    target, source = Path(target).resolve(), Path(source).resolve()
    if target.name != "mass.py" or target.parent.name != "music_assistant" or versions() != ("2.10.8", "1.1.205"):
        raise ValueError("Use the explicitly reviewed MA 2.10.8 environment and target. Nothing installed.")
    contract = json.loads((source / "contract.json").read_text())
    if set(contract) != {"id", "version", "models", "source_pins", "files"} or (contract["id"], contract["version"], contract["models"]) != (
        "ma2108-contract-1",
        "2.10.8",
        "1.1.205",
    ):
        raise ValueError("Candidate manifest needs review. Nothing installed.")
    original = target.read_bytes()
    baseline = original.replace(HOOK.encode(), ANCHOR.encode()) if original.count(HOOK.encode()) == 1 else original
    if baseline.count(ANCHOR.encode()) != 1:
        raise ValueError("Unrecognised startup hook. Nothing installed.")
    for name, digest in contract["source_pins"].items():
        path = (target.parent / name).resolve()
        if not path.is_relative_to(target.parent):
            raise ValueError("Source pin escaped target. Nothing installed.")
        body = baseline if path == target else path.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Native source changed. Nothing installed.")
    code = {}
    for name, digest in contract["files"].items():
        if not re.fullmatch(r"[a-z_]+\.py", name):
            raise ValueError("Unexpected candidate module path. Nothing installed.")
        body = (source / name).read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Candidate bytes changed. Nothing installed.")
        compile(body, name, "exec")
        code[name] = body
    if not {"ma_release_review.py", "ma_account_guard.py", "ma_transfer.py", "ma_control_contract.py", "__init__.py"} <= code.keys():
        raise ValueError("Candidate modules incomplete. Nothing installed.")
    backup = target.with_suffix(".home-starter-2108-original")
    if backup.exists() and backup.read_bytes() != baseline:
        raise ValueError("Existing backup differs. Nothing installed.")
    if check:
        return "Candidate source/modules checked; no files changed. Runtime acceptance remains required."
    destination = target.parent.parent / "home_starter_ma"
    if destination.exists():
        extras = {p.name for p in destination.glob("*.py")} - code.keys()
        if extras:
            raise ValueError("Existing adapter contains unrelated modules. Reconcile before install.")
    destination.mkdir(exist_ok=True)
    for name, body in code.items():
        path = destination / name
        temporary = path.with_suffix(".candidate-tmp")
        temporary.write_bytes(body)
        os.replace(temporary, path)
    if not backup.exists():
        backup.write_bytes(baseline)
    patched = baseline.replace(ANCHOR.encode(), HOOK.encode())
    temporary = target.with_suffix(".candidate-tmp")
    temporary.write_bytes(patched)
    os.replace(temporary, target)
    return "Candidate staged. No service restarted; activation still requires the approved MA-only restart."


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(install(args.target, args.source, check=not args.apply))
