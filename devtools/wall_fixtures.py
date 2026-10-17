"""Write the twelve fictional wall-composer scenarios for native browser/dev rendering."""

import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "home_starter/server"))
sys.path.insert(0, str(ROOT / "tests"))
from wall_scenarios import SCENARIOS, scenario  # noqa: E402


def main():
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".runtime/wall-adaptive-fixtures")
    output.mkdir(parents=True, exist_ok=True)
    for name in SCENARIOS:
        case = scenario(name)
        value = {"fictional": True, "name": name, "clock": case["now"].isoformat(), "model": case["model"]}
        (output / (name + ".json")).write_text(json.dumps(value, indent=2), encoding="utf-8")
        static = ROOT / "home_starter/server/homestarter/static"
        source = (static / "wall-content.js").read_text().replace("const now = new Date();", "const now = new Date(" + json.dumps(value["clock"]) + ");")
        cfg = {"title": "Fictional wall fixture", "surface_id": "example_wall", "epoch": 0, "context": "sensor.fixture"}
        attrs = {
            "home_starter_context": {"surface": "example_wall", "epoch": 0},
            "checked_at": value["clock"],
            "valid_until": case["model"]["valid_until"],
            "wall": case["model"],
        }
        hass = {
            "connected": True,
            "states": {"sensor.fixture": {"attributes": attrs}},
            "config": {"time_zone": "Australia/Sydney"},
            "locale": {"language": "en-AU"},
        }
        css = (static / "wall-layout.css").read_text()
        image = base64.b64encode((static / "wall-morning.jpg").read_bytes()).decode()
        script = (
            "const render = new Function('hass','variables','html','window'," + json.dumps(source) + ");\n"
            "document.body.innerHTML=render("
            + json.dumps(hass)
            + ","
            + json.dumps({"wall_json": json.dumps(cfg)})
            + ",(_,body)=>body,{innerHeight:window.innerHeight,location:{search:'?kiosk'}});"
        )
        page = (
            "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Fictional "
            + name
            + "</title><style>body{margin:0;container-type:inline-size;--wall-landscape:url(data:image/jpeg;base64,"
            + image
            + ");}"
            + css
            + "</style><body><script>"
            + script.replace("</", "<\\/")
            + "</script></body></html>"
        )
        (output / (name + ".html")).write_text(page, encoding="utf-8")
    print(f"Wrote {len(SCENARIOS)} fictional wall scenarios to {output}")


if __name__ == "__main__":
    main()
