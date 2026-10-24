"""GitHub-only disposable copy integration; never use a household container."""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def command(*args, ok=True):
    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603 -- fixed Docker/sh commands and scoped test inputs
    if ok and result.returncode:
        print(result.stdout)
        print(result.stderr)
        raise RuntimeError("Isolated offline-copy command failed")
    return result


def run():
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.name != "posix":
        raise RuntimeError("This integration driver requires the isolated GitHub Linux job")
    image, rollback = os.environ["MA_IMAGE"], os.environ["MA_ROLLBACK_IMAGE"]
    root = Path(__file__).resolve().parents[1]
    target = "hs-ma2108-ci-target-" + str(os.getpid())
    command(
        "docker",
        "create",
        "--name",
        target,
        "--network",
        "none",
        "--user",
        "65534:65534",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "2g",
        "--cpus",
        "2",
        "--tmpfs",
        "/data:rw,mode=1777",
        "--tmpfs",
        "/tmp:rw,mode=1777",  # noqa: S108 -- private tmpfs inside the disposable container
        "--entrypoint",
        "/app/venv/bin/python",
        image,
        "/app/check.py",
        "--candidate",
    )
    try:
        with tempfile.TemporaryDirectory(prefix="hs-ma2108-offline-ci-") as directory:
            base = Path(directory)
            backup = base / "synthetic-backup"
            backup.write_bytes(b"Synthetic backup fixture, not household data or restore acceptance")
            receipt = base / "receipt.json"
            receipt.write_text(
                json.dumps(
                    {
                        "schema": 1,
                        "ma_version": "2.10.7",
                        "hs_version": "0.8.47",
                        "backup_sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
                        "rollback_image": rollback,
                        "scopes": ["d5369777_music_assistant", "6726420e_home_starter"],
                        "stopped_consistent": True,
                        "recovery_key_available": True,
                    }
                )
            )
            common = [target, image, str(root / ".runtime/ma2108-ci/ma2108-review-candidate.tar")]
            tail = [str(backup), str(receipt), rollback, "2026.10.3"]
            script = str(root / "devtools/stage_ma2108_offline.sh")
            command("sh", "-n", script)
            command("sh", script, *common, str(base / "check"), *tail)
            command("sh", script, "--prepare", *common, str(base / "prepare"), *tail)
            rejected = command("sh", script, "--apply", *common, str(base / "refused"), *tail, ok=False)
            assert rejected.returncode and "unreviewed" in rejected.stderr
            package_root = (base / "prepare/package-root.txt").read_text().strip()
            original = base / "baseline-mass.py"
            command("docker", "cp", f"{target}:{package_root}/mass.py", str(original))
            assert original.read_bytes() == (base / "check/original/music_assistant/mass.py").read_bytes()
            assert command("docker", "inspect", "--format", "{{.State.Status}} {{.State.StartedAt}}", target).stdout.strip() == "created 0001-01-01T00:00:00Z"
            print("PASS operator default/prepare do not write or start target; unknown Supervisor apply refused", flush=True)

            # Exercise Docker's actual stopped-container copy semantics directly
            # on this newly created, network-none fixture. This does NOT bypass
            # the production operator's Supervisor gate for a household target.
            prepared = base / "prepare/original"
            command("docker", "cp", str(prepared / "home_starter_ma"), f"{target}:{Path(package_root).parent}/home_starter_ma")
            command(
                "docker", "cp", str(prepared / "music_assistant/mass.home-starter-2108-original"), f"{target}:{package_root}/mass.home-starter-2108-original"
            )
            command("docker", "cp", str(prepared / "music_assistant/mass.py"), f"{target}:{package_root}/mass.py")
            readback = base / "readback-mass.py"
            command("docker", "cp", f"{target}:{package_root}/mass.py", str(readback))
            assert readback.read_bytes() == (prepared / "music_assistant/mass.py").read_bytes()
            work = base / "prepare"
            contract = json.loads((work / "unpacked/home_starter_ma/contract.json").read_text())
            for source in contract["source_pins"]:
                destination = work / "readback/music_assistant" / source
                destination.parent.mkdir(parents=True, exist_ok=True)
                command("docker", "cp", f"{target}:{package_root}/{source}", str(destination))
            command(
                "docker",
                "cp",
                f"{target}:{package_root}/mass.home-starter-2108-original",
                str(work / "readback/music_assistant/mass.home-starter-2108-original"),
            )
            command("docker", "cp", f"{target}:{Path(package_root).parent}/home_starter_ma", str(work / "readback/home_starter_ma"))
            command(
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                f"{os.getuid()}:{os.getgid()}",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--mount",
                f"type=bind,src={work},dst=/work",
                "--entrypoint",
                "/app/venv/bin/python",
                image,
                "/work/payload.py",
                "verify",
            )
            assert command("docker", "inspect", "--format", "{{.State.Status}} {{.State.StartedAt}}", target).stdout.strip() == "created 0001-01-01T00:00:00Z"
            for source, destination in (("check_ma2108_runtime.py", "check.py"), ("check_ma2108_runtime_cases.py", "check_ma2108_runtime_cases.py")):
                command("docker", "cp", str(root / "devtools" / source), f"{target}:/app/{destination}")
            result = command("docker", "start", "--attach", target)
            assert command("docker", "inspect", "--format", "{{.State.ExitCode}}", target).stdout.strip() == "0"
            assert "PASS real native transfer body" in result.stdout
            print("PASS stopped-container offline copies/readback and first guarded startup/controller checks", flush=True)
    finally:
        command("docker", "rm", "--force", target)


if __name__ == "__main__":
    run()
