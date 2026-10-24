"""Build a separate ignored native review bundle; never install or activate it."""

import argparse
import ast
import hashlib
import json
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "home_starter/server"))
from homestarter.ma_release_review import PINS  # noqa: E402


def prepare(output):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / ".runtime") or output.exists():
        raise ValueError("Choose a new ignored review-bundle directory.")
    source = ROOT / "home_starter/server/homestarter"
    todo, modules = ["ma_release_review"], {}
    while todo:
        name = todo.pop()
        if name in modules:
            continue
        path = source / (name + ".py")
        body = path.read_bytes().replace(b"\r\n", b"\n")
        modules[name] = body
        for node in ast.walk(ast.parse(body.decode())):
            if isinstance(node, ast.ImportFrom) and node.level == 1:
                for dep in [node.module.split(".")[0]] if node.module else [a.name for a in node.names]:
                    if (source / (dep + ".py")).is_file():
                        todo.append(dep)
    if {"server", "wall_composer", "music_runtime", "household"} & modules.keys():
        raise ValueError("Native bundle unexpectedly pulls household/UI service modules.")
    package = output / "home_starter_ma"
    package.mkdir(parents=True)
    files = {"__init__.py": b"", **{name + ".py": body for name, body in modules.items()}}
    for name, body in files.items():
        (package / name).write_bytes(body)
    manifest = {
        "id": "ma2108-contract-1",
        "version": "2.10.8",
        "models": "1.1.205",
        "source_pins": PINS,
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()},
    }
    (package / "contract.json").write_text(json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8", newline="\n")
    installer = (ROOT / "devtools/install_ma2108_candidate.py").read_bytes().replace(b"\r\n", b"\n")
    (output / "install_ma2108_candidate.py").write_bytes(installer)
    archive = output / "ma2108-review-candidate.tar"
    with tarfile.open(archive, "w") as stream:
        for path in sorted(output.rglob("*")):
            if path.is_file() and path != archive:
                info = stream.gettarinfo(str(path), str(path.relative_to(output)))
                info.mtime, info.uid, info.gid, info.uname, info.gname = 0, 0, 0, "", ""
                info.mode = 0o644
                with path.open("rb") as body:
                    stream.addfile(info, body)
    return {"modules": len(files), "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "installed": False, "runtime_accepted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output")
    print(json.dumps(prepare(parser.parse_args().output)))
