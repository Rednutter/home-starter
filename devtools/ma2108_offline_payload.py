"""Validate public-source copies and prepare an offline payload, never start MA."""

import argparse
import hashlib
import json
import runpy
import tarfile
from pathlib import Path

ARCHIVE_SHA256 = "a6323a20a15a4efcff1ca8cb87898be02e3940825bddb1079d29771acfad8598"  # pragma: allowlist secret -- reviewed public source archive
# No installed Supervisor update lifecycle has yet been reviewed. Do not replace
# this with an operator checkbox or infer approval from a stopped container.
SUPERVISOR_REVIEWS = {}


def receipt_check(receipt, backup_sha, rollback_image):
    expected = {"schema", "ma_version", "hs_version", "backup_sha256", "rollback_image", "scopes", "stopped_consistent", "recovery_key_available"}
    if (
        not isinstance(receipt, dict)
        or set(receipt) != expected
        or type(receipt["schema"]) is not int
        or receipt["schema"] != 1
        or receipt["ma_version"] != "2.10.7"
        or receipt["hs_version"] != "0.8.47"
        or receipt["backup_sha256"] != backup_sha
        or receipt["rollback_image"] != rollback_image
        or not isinstance(receipt["scopes"], list)
        or len(receipt["scopes"]) != 2
        or any(not isinstance(value, str) for value in receipt["scopes"])
        or set(receipt["scopes"]) != {"d5369777_music_assistant", "6726420e_home_starter"}
        or receipt["stopped_consistent"] is not True
        or receipt["recovery_key_available"] is not True
    ):
        raise ValueError("Matching backup/recovery receipt required")


def supervisor_gate(version):
    if version not in SUPERVISOR_REVIEWS:
        raise ValueError("Supervisor stopped-update behavior is unreviewed; activation refused")


def prepare(work, *, apply=False):
    work = Path(work).resolve()
    archive = work / "candidate.tar"
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Candidate archive identity changed")
    destination = work / "unpacked"
    if destination.exists():
        raise ValueError("Existing staging requires reconciliation; use a new work directory")
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            path = Path(member.name)
            if member.issym() or member.islnk() or not member.isfile() or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe archive member")
            if member.name != "install_ma2108_candidate.py" and not (len(path.parts) == 2 and path.parts[0] == "home_starter_ma"):
                raise ValueError("Unexpected archive member")
        stream.extractall(destination, filter="data")
    installer = runpy.run_path(str(destination / "install_ma2108_candidate.py"))
    target = work / "original/music_assistant/mass.py"
    result = installer["install"](target, destination / "home_starter_ma", check=not apply)
    print(result)
    # Baseline byte copies remain available even after preparing the patched
    # output. This is a source backup, not an MA database/version rollback.
    if apply:
        original = target.with_suffix(".home-starter-2108-original")
        contract = json.loads((destination / "home_starter_ma/contract.json").read_text())
        assert hashlib.sha256(original.read_bytes()).hexdigest() == contract["source_pins"]["mass.py"]
        assert target.read_bytes().count(installer["HOOK"].encode()) == 1


def verify_copy(work):
    work = Path(work).resolve()
    unpacked = work / "unpacked"
    contract = json.loads((unpacked / "home_starter_ma/contract.json").read_text())
    package = work / "readback/home_starter_ma"
    if {p.name for p in package.glob("*.py")} != set(contract["files"]):
        raise ValueError("Copied module inventory differs")
    for name, digest in contract["files"].items():
        if hashlib.sha256((package / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Copied module bytes differ")
    installer = runpy.run_path(str(unpacked / "install_ma2108_candidate.py"))
    target = work / "readback/music_assistant/mass.py"
    if target.read_bytes() != (work / "original/music_assistant/mass.py").read_bytes():
        raise ValueError("Copied startup differs")
    original = target.with_suffix(".home-starter-2108-original")
    if hashlib.sha256(original.read_bytes()).hexdigest() != contract["source_pins"]["mass.py"]:
        raise ValueError("Copied baseline backup differs")
    installer["install"](target, unpacked / "home_starter_ma", check=True)
    print("All copied modules, source pins, startup and source backup verified; service not started")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("check", "prepare", "verify", "receipt", "gate"))
    parser.add_argument("--work", default="/work")
    parser.add_argument("--backup-sha")
    parser.add_argument("--rollback-image")
    parser.add_argument("--supervisor-version")
    args = parser.parse_args()
    if args.mode == "gate":
        supervisor_gate(args.supervisor_version)
    elif args.mode == "receipt":
        receipt_check(json.loads((Path(args.work) / "receipt.json").read_text()), args.backup_sha, args.rollback_image)
        print("Backup/recovery receipt matches; restore itself is not tested here")
    elif args.mode == "verify":
        verify_copy(args.work)
    else:
        prepare(args.work, apply=args.mode == "prepare")
