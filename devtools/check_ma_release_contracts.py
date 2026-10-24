"""Verify immutable official release source contracts without executing MA.

Python 3.14 whole-module syntax is deliberately not rewritten for Python 3.12.
Only isolated declarations and registrations are parsed; process/behaviour tests
remain a separate requirement. Fixtures live outside tracked source.
"""

import argparse
import ast
import hashlib
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "home_starter/server"))
from homestarter.ma_transfer import PINS  # noqa: E402

RELEASES = {"2.10.6": "c24866405bd2068c25a60e1014e5ef8c3f6445bb", "2.10.7": "76ad754a68abdd0bfd179b13a2807d44771ddf90"}  # pragma: allowlist secret


def declarations(source):
    lines = source.splitlines()
    result = []
    for start, line in enumerate(lines):
        if not re.match(r"\s*(async\s+)?def\s+", line):
            continue
        end = start
        while end < min(start + 40, len(lines)) and not lines[end].split("#", 1)[0].rstrip().endswith(":"):
            end += 1
        if end >= min(start + 40, len(lines)):
            continue
        first = start
        for index in range(start - 1, max(-1, start - 16), -1):
            if re.match(r"\s*@api_command\(", lines[index]):
                first = index
                break
            if re.match(r"\s*(async\s+)?def\s+|\s*class\s+", lines[index]):
                break
        snippet = textwrap.dedent("\n".join(lines[first : end + 1])) + "\n    pass\n"
        try:
            node = next(n for n in ast.parse(snippet).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
        except (SyntaxError, StopIteration):
            continue
        params = [a.arg for a in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]]
        commands = []
        for item in node.decorator_list:
            if (
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Name)
                and item.func.id == "api_command"
                and item.args
                and isinstance(item.args[0], ast.Constant)
            ):
                commands.append(
                    {"command": item.args[0].value, "scope": next((ast.unparse(k.value) for k in item.keywords if k.arg == "required_scope"), None)}
                )
        result.append({"name": node.name, "line": start + 1, "params": params, "commands": commands})
    return result


def inspect_release(root, version):
    folder = Path(root) / version
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["version"] != version or manifest["commit"] != RELEASES[version]:
        raise ValueError("Official release fixture identity mismatch")
    contents = {}
    for name, digest in manifest["files"].items():
        target = (folder / name).resolve()
        if not target.is_relative_to(folder.resolve()):
            raise ValueError("Fixture source escaped its root")
        body = target.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError("Official release fixture bytes changed")
        if name.endswith(".py"):
            contents[name] = body.decode("utf-8")
    functions, commands = {}, {}
    for name, source in contents.items():
        for item in declarations(source):
            functions.setdefault(item["name"], []).append({"file": name, **item})
            for command in item["commands"]:
                commands[command["command"]] = {"file": name, "params": item["params"], "scope": command["scope"]}
    public = {key: commands.get(key) for key in ["providers", "auth/users", "players/all", "players/cmd/set_members", "player_queues/transfer"]}
    artist = next(r for r in functions["library_items"] if r["file"].endswith("music/media/artists.py"))
    private = {}
    for name, required in {
        "get_stream_details": {"queue_item", "excluded_provider_instances"},
        "get_audio_buffer": {"queue_item", "allow_provider_match"},
        "_get_mapping_providers": {"mapping"},
        "_discover_alternative_provider_mappings": {"queue_item", "busy_instances", "remaining"},
        "get_media_stream": {"streamdetails"},
        "_acquire_run": {"spotify_uri", "seek_position", "streamdetails", "continuation"},
    }.items():
        private[name] = any(required <= set(item["params"]) for item in functions.get(name, []))
    pins = {
        name: hashlib.sha256((folder / "music_assistant/controllers/player_queues" / name).read_bytes()).hexdigest() == digest for name, digest in PINS.items()
    }
    return {
        "version": version,
        "commit": manifest["commit"],
        "verified_files": len(manifest["files"]),
        "public": public,
        "artist_library": artist,
        "guard_signature_shapes": private,
        "transfer_source_pins": pins,
        "running_server_tested": False,
        "playback_enforcement_attested": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    print(json.dumps([inspect_release(args.root, version) for version in RELEASES], indent=2))
