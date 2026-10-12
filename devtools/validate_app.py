"""Validate the App package the way Home Assistant tooling does.

1. The official app linter's JSON schema (frenck/action-addon-linter, used by
   home-assistant/apps-example CI), including its "uses a default value" rule.
2. Optionally, the Supervisor's own voluptuous schemas
   (supervisor.apps.validate.SCHEMA_APP_CONFIG and
   supervisor.store.validate.SCHEMA_REPOSITORY_CONFIG), given a Supervisor
   checkout whose requirements are installed in the current interpreter.

    python devtools/validate_app.py --linter-src ../action-addon-linter \
        [--supervisor-src ../supervisor]

Exits non-zero on any problem.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, ValidationError, validators

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "home_starter"


def _default_checking(validator_class):
    validate_properties = validator_class.VALIDATORS["properties"]

    def is_default(validator, properties, instance, schema):
        for prop, subschema in properties.items():
            if "default" in subschema and instance.get(prop) == subschema["default"]:
                yield ValidationError(f"'{prop}' should be removed, it uses a default value")
        yield from validate_properties(validator, properties, instance, schema)

    return validators.extend(validator_class, {"properties": is_default})


def lint(linter_src: Path) -> list[str]:
    schema = json.loads((linter_src / "src" / "config.schema.json").read_text())
    config = yaml.safe_load((APP / "config.yaml").read_text())
    problems = [e.message for e in _default_checking(Draft7Validator)(schema).iter_errors(config)]
    if (APP / "build.yaml").exists() or (APP / "build.json").exists():
        problems.append("build.yaml is no longer used; set the base image in the Dockerfile")
    for name in ("Dockerfile", "icon.png", "logo.png", "README.md", "DOCS.md", "CHANGELOG.md"):
        if not (APP / name).exists():
            problems.append(f"missing {name}")
    return problems


def supervisor_schema(supervisor_src: Path) -> list[str]:
    sys.path.insert(0, str(supervisor_src))
    try:
        from supervisor.apps.validate import SCHEMA_APP_CONFIG  # type: ignore[import-not-found]
        from supervisor.store.validate import SCHEMA_REPOSITORY_CONFIG  # type: ignore[import-not-found]
    except ImportError as err:
        return [f"cannot import Supervisor schemas ({err}); install its requirements.txt"]
    problems = []
    try:
        SCHEMA_APP_CONFIG(yaml.safe_load((APP / "config.yaml").read_text()))
    except Exception as err:  # noqa: BLE001 - report any schema failure
        problems.append(f"config.yaml rejected by Supervisor schema: {err}")
    try:
        SCHEMA_REPOSITORY_CONFIG(yaml.safe_load((ROOT / "repository.yaml").read_text()))
    except Exception as err:  # noqa: BLE001
        problems.append(f"repository.yaml rejected by Supervisor schema: {err}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--linter-src", type=Path, required=True)
    parser.add_argument("--supervisor-src", type=Path)
    args = parser.parse_args()
    problems = lint(args.linter_src)
    print("app linter:", "OK" if not problems else "FAILED")
    if args.supervisor_src:
        sup = supervisor_schema(args.supervisor_src)
        print("supervisor schema:", "OK" if not sup else "FAILED")
        problems += sup
    for p in problems:
        print(" -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
