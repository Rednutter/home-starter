"""Copy only our isolated entry into an already verified, pinned upstream tree."""

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Public, verified upstream Git commit; not a credential.
PIN = "dc3caf60f124301a32e21bcb053523d2451a6bfa"  # pragma: allowlist secret
source = ROOT / ".runtime/ma-household-upstream"
assert json.loads((ROOT / ".runtime/ma-frontend-readonly/source-pin.json").read_text())["commit"] == PIN
assert (source / "node_modules/vite/bin/vite.js").is_file()
destination = source / "household-preview"
destination.mkdir(exist_ok=True)
for path in Path(__file__).parent.iterdir():
    if path.suffix in {".ts", ".vue", ".html", ".css"}:
        shutil.copyfile(path, destination / path.name)
print("Prepared isolated household-preview entry; upstream src remains unchanged.")
